"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import io
from collections import namedtuple
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import omni.kit.test

from lightspeed.trex.app.setup.extension import TrexSetupExtension
from lightspeed.trex.app.setup import setup_ui as _setup_ui
from lightspeed.trex.app.setup.setup_ui import MenubarIgnore, MenuLayout, SetupUI

MenuItem = namedtuple("MenuItem", ["name", "sub_menu"])


def _make_setup_ui(default_layout: str = "stagecraft", hide_menu: bool = False) -> SetupUI:
    setup_ui = SetupUI.__new__(SetupUI)
    settings = MagicMock()
    settings.get.side_effect = lambda path: default_layout if path == _setup_ui._DEFAULT_LAYOUT else None
    setup_ui._SetupUI__settings = settings
    setup_ui._SetupUI__sub_app_ready = MagicMock()
    setup_ui._SetupUI__app_ready_task = None
    setup_ui._SetupUI__hide_menu = hide_menu
    setup_ui._SetupUI__preferences_menu_hook = MagicMock()
    setup_ui._SetupUI__preferences_menu_hook_registered = False
    return setup_ui


class TestSetupUI(omni.kit.test.AsyncTestCase):
    """Test application-ready UI setup and lifecycle ownership."""

    async def test_init_registers_preferences_menu_hook(self):
        settings = MagicMock()
        settings.get.return_value = False
        startup_event_stream = MagicMock()
        app = MagicMock()
        app.is_app_ready.return_value = False
        app.get_startup_event_stream.return_value = startup_event_stream

        with (
            patch("lightspeed.trex.app.setup.setup_ui.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.trex.app.setup.setup_ui.omni.kit.menu.utils.add_hook") as add_hook_mock,
            patch("lightspeed.trex.app.setup.setup_ui.omni.kit.app.get_app", return_value=app),
        ):
            setup_ui = SetupUI()

        add_hook_mock.assert_called_once_with(setup_ui._SetupUI__preferences_menu_hook)
        self.assertTrue(setup_ui._SetupUI__preferences_menu_hook_registered)

    async def test_init_defers_app_ready_setup_until_app_ready(self):
        settings = MagicMock()
        settings.get.return_value = True
        startup_event_stream = MagicMock()
        startup_event_stream.create_subscription_to_pop_by_type.return_value = "subscription"
        app = MagicMock()
        app.is_app_ready.return_value = False
        app.get_startup_event_stream.return_value = startup_event_stream

        with (
            patch("lightspeed.trex.app.setup.setup_ui.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.trex.app.setup.setup_ui.omni.kit.menu.utils.add_hook"),
            patch("lightspeed.trex.app.setup.setup_ui.omni.kit.app.get_app", return_value=app),
        ):
            setup_ui = SetupUI()

        startup_event_stream.create_subscription_to_pop_by_type.assert_called_once_with(
            omni.kit.app.EVENT_APP_READY,
            setup_ui._on_app_ready,
            name="Lightspeed App Ready Setup",
        )
        self.assertEqual(setup_ui._SetupUI__sub_app_ready, "subscription")

    async def test_stagecraft_ready_orders_home_splash_update_and_user_ready(self):
        # Arrange
        setup_ui = _make_setup_ui(hide_menu=True)
        app = MagicMock()
        order = []
        app.next_update_async = AsyncMock(side_effect=lambda: order.append("update"))
        menubar_ignore = MagicMock()
        menubar_ignore.get_menubar_layout.return_value = ["layout"]
        scheduled_coroutines = []

        def capture_coroutine(coroutine):
            scheduled_coroutines.append(coroutine)
            return MagicMock()

        with (
            patch("lightspeed.trex.app.setup.setup_ui.omni.kit.app.get_app", return_value=app),
            patch("lightspeed.trex.app.setup.setup_ui.asyncio.ensure_future", side_effect=capture_coroutine),
            patch(
                "lightspeed.trex.app.setup.setup_ui._wait_for_home_interactive",
                new=AsyncMock(side_effect=lambda: order.append("home")),
            ),
            patch("lightspeed.trex.app.setup.setup_ui._publish_user_ready", side_effect=lambda: order.append("ready")),
            patch("lightspeed.trex.app.setup.setup_ui.MenubarIgnore", return_value=menubar_ignore),
            patch("lightspeed.trex.app.setup.setup_ui.omni.kit.menu.utils.add_layout") as add_layout_mock,
            patch.object(
                SetupUI, "_SetupUI__close_splash_screen", side_effect=lambda: order.append("splash")
            ) as close_splash_mock,
            patch("lightspeed.trex.app.setup.setup_ui._apply_windows_dark_titlebar") as apply_titlebar_mock,
        ):
            # Act
            setup_ui._on_app_ready()
            await scheduled_coroutines[0]

        # Assert
        self.assertIsNone(setup_ui._SetupUI__sub_app_ready)
        self.assertEqual(order, ["home", "splash", "update", "ready"])
        self.assertEqual(app.next_update_async.await_count, 1)
        add_layout_mock.assert_called_once_with(["layout"])
        close_splash_mock.assert_called_once_with()
        apply_titlebar_mock.assert_called_once_with()

    async def test_non_home_layout_keeps_three_update_fallback_without_user_ready(self):
        # Arrange
        setup_ui = _make_setup_ui(default_layout="ingestcraft")
        app = MagicMock()
        app.next_update_async = AsyncMock()

        with (
            patch("lightspeed.trex.app.setup.setup_ui.omni.kit.app.get_app", return_value=app),
            patch("lightspeed.trex.app.setup.setup_ui._wait_for_home_interactive", new=AsyncMock()) as wait_mock,
            patch("lightspeed.trex.app.setup.setup_ui._publish_user_ready") as publish_mock,
            patch.object(SetupUI, "_SetupUI__close_splash_screen") as close_splash_mock,
            patch("lightspeed.trex.app.setup.setup_ui._apply_windows_dark_titlebar"),
        ):
            # Act
            await setup_ui._SetupUI__deferred_app_ready_setup()

        # Assert
        self.assertEqual(app.next_update_async.await_count, 3)
        wait_mock.assert_not_awaited()
        close_splash_mock.assert_called_once_with()
        publish_mock.assert_not_called()

    async def test_home_ready_timeout_closes_splash_without_publishing(self):
        # Arrange
        setup_ui = _make_setup_ui()

        with (
            patch("lightspeed.trex.app.setup.setup_ui.asyncio.wait_for", new=AsyncMock(side_effect=TimeoutError)),
            patch(
                "lightspeed.trex.app.setup.setup_ui._wait_for_home_interactive",
                new=MagicMock(return_value=MagicMock()),
            ),
            patch.object(SetupUI, "_SetupUI__close_splash_screen") as close_splash_mock,
            patch("lightspeed.trex.app.setup.setup_ui._publish_user_ready") as publish_mock,
            patch("lightspeed.trex.app.setup.setup_ui.carb.log_error") as log_error_mock,
        ):
            # Act
            await setup_ui._SetupUI__deferred_app_ready_setup()

        # Assert
        close_splash_mock.assert_called_once_with()
        publish_mock.assert_not_called()
        log_error_mock.assert_called_once_with(
            "[lightspeed.trex.app.setup] Home did not become interactive within 30 seconds"
        )

    async def test_duplicate_app_ready_does_not_replace_pending_task(self):
        """Reuse the pending setup task when app-ready is delivered more than once."""
        # Arrange
        setup_ui = _make_setup_ui()
        pending_task = MagicMock()
        deferred_setup = MagicMock()

        with (
            patch.object(
                SetupUI,
                "_SetupUI__deferred_app_ready_setup",
                new=MagicMock(return_value=deferred_setup),
            ),
            patch("lightspeed.trex.app.setup.setup_ui.asyncio.ensure_future", return_value=pending_task) as ensure_mock,
        ):
            # Act
            setup_ui._on_app_ready()
            setup_ui._on_app_ready()

        # Assert
        ensure_mock.assert_called_once_with(deferred_setup)
        self.assertIs(setup_ui._SetupUI__app_ready_task, pending_task)

    async def test_apply_windows_dark_titlebar_skips_non_windows(self):
        with (
            patch("lightspeed.trex.app.setup.setup_ui.sys.platform", "linux"),
            patch("lightspeed.trex.app.setup.setup_ui.omni.appwindow.get_default_app_window") as get_app_window_mock,
        ):
            _setup_ui._apply_windows_dark_titlebar()

        get_app_window_mock.assert_not_called()

    async def test_apply_windows_dark_titlebar_uses_native_app_window_handle(self):
        settings = MagicMock()
        settings.get.return_value = True
        app_window = MagicMock()
        app_window.get_window.return_value = "carb_window"
        windowing = MagicMock()
        windowing.get_native_window.return_value = "native_capsule"

        with (
            patch("lightspeed.trex.app.setup.setup_ui.sys.platform", "win32"),
            patch("lightspeed.trex.app.setup.setup_ui.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.trex.app.setup.setup_ui.omni.appwindow.get_default_app_window", return_value=app_window),
            patch(
                "lightspeed.trex.app.setup.setup_ui.carb.windowing.acquire_windowing_interface",
                return_value=windowing,
            ),
            patch("lightspeed.trex.app.setup.setup_ui._get_capsule_pointer", return_value=1234),
            patch("lightspeed.trex.app.setup.setup_ui._set_windows_titlebar_dark", return_value=True) as set_dark_mock,
        ):
            _setup_ui._apply_windows_dark_titlebar()

        windowing.get_native_window.assert_called_once_with("carb_window")
        set_dark_mock.assert_called_once_with(1234)

    async def test_set_windows_titlebar_dark_falls_back_to_older_dark_mode_attribute(self):
        calls: list[tuple[int, int]] = []

        def set_window_attribute(hwnd, attribute, _value, _value_size):
            calls.append((hwnd.value, attribute.value))
            return 1 if len(calls) == 1 else 0

        windll = SimpleNamespace(dwmapi=SimpleNamespace(DwmSetWindowAttribute=set_window_attribute))
        with patch("lightspeed.trex.app.setup.setup_ui.ctypes.windll", windll, create=True):
            self.assertTrue(_setup_ui._set_windows_titlebar_dark(4321))

        self.assertEqual(
            calls,
            [
                (4321, _setup_ui._DARK_TITLEBAR_ATTRIBUTES[0]),
                (4321, _setup_ui._DARK_TITLEBAR_ATTRIBUTES[1]),
            ],
        )

    async def test_clear_preferences_menu_tick_keeps_preferences_unticked(self):
        preferences_item = SimpleNamespace(
            name="Preferences",
            ticked=True,
            ticked_value=True,
            ticked_fn=lambda: True,
        )
        undo_item = SimpleNamespace(name="Undo", ticked=True, ticked_value=True, ticked_fn=lambda: True)
        merged_menu = {"Edit": [undo_item, preferences_item]}

        SetupUI._SetupUI__clear_preferences_menu_tick(merged_menu)

        self.assertFalse(preferences_item.ticked)
        self.assertIsNone(preferences_item.ticked_value)
        self.assertIsNone(preferences_item.ticked_fn)
        self.assertTrue(undo_item.ticked)
        self.assertTrue(undo_item.ticked_value)
        self.assertIsNotNone(undo_item.ticked_fn)

    async def test_destroy_removes_preferences_menu_hook_when_registered(self):
        setup_ui = SetupUI.__new__(SetupUI)
        app_ready_task = MagicMock()
        setup_ui._SetupUI__sub_app_ready = MagicMock()
        setup_ui._SetupUI__app_ready_task = app_ready_task
        setup_ui._SetupUI__preferences_menu_hook = MagicMock()
        setup_ui._SetupUI__preferences_menu_hook_registered = True

        with patch("lightspeed.trex.app.setup.setup_ui.omni.kit.menu.utils.remove_hook") as remove_hook_mock:
            setup_ui.destroy()

        remove_hook_mock.assert_called_once_with(setup_ui._SetupUI__preferences_menu_hook)
        app_ready_task.cancel.assert_called_once_with()
        self.assertFalse(setup_ui._SetupUI__preferences_menu_hook_registered)
        self.assertIsNone(setup_ui._SetupUI__sub_app_ready)
        self.assertIsNone(setup_ui._SetupUI__app_ready_task)


class TestMenubarIgnore(omni.kit.test.AsyncTestCase):
    async def test_is_ignored_uses_exclusions_and_inclusions(self):
        with TemporaryDirectory() as temp_dir:
            ignore_file = Path(temp_dir) / "menubar_ignore"
            ignore_file.write_text(
                "Edit/\n!Edit/Preferences\nWindow/Debug",
                encoding="utf-8",
            )

            with patch(
                "lightspeed.trex.app.setup.setup_ui._get_menubar_ignore_file",
                return_value=ignore_file,
            ):
                menubar_ignore = MenubarIgnore()

        self.assertTrue(menubar_ignore.is_ignored("Edit/Undo"))
        self.assertFalse(menubar_ignore.is_ignored("Edit/Preferences"))
        self.assertTrue(menubar_ignore.is_ignored("Window/Debug"))
        self.assertFalse(menubar_ignore.is_ignored("Window/Profiler"))
        self.assertFalse(menubar_ignore.is_ignored("Profiler/Start"))
        self.assertFalse(menubar_ignore.is_ignored("File/Open"))

    async def test_get_menubar_layout_removes_ignored_items_and_keeps_visible_menus(self):
        menubar_ignore = MenubarIgnore.__new__(MenubarIgnore)
        menubar_ignore._MenubarIgnore__rules = {
            "inclusions": {"Edit/Preferences"},
            "exclusions": {"Edit/*", "Window/Debug"},
        }
        merged_menus = {
            "File": {"items": [MenuItem("Open", None)]},
            "Edit": {
                "items": [
                    MenuItem("Undo", None),
                    MenuItem("Preferences", None),
                    MenuItem("Advanced", "Edit/Advanced"),
                ]
            },
            "Edit/Advanced": {
                "sub_menu": True,
                "items": [
                    MenuItem("Hidden", None),
                    MenuItem("AlsoHidden", None),
                ],
            },
            "Window": {"items": [MenuItem("Debug", None), MenuItem("Profiler", None), MenuItem("Viewport", None)]},
            "Profiler": {"items": [MenuItem("Start", None), MenuItem("Stop", None)]},
        }

        with patch(
            "lightspeed.trex.app.setup.setup_ui.omni.kit.menu.utils.get_merged_menus", return_value=merged_menus
        ):
            layouts = menubar_ignore.get_menubar_layout()

        file_layout = next(layout for layout in layouts if layout.name == "File")
        edit_layout = next(layout for layout in layouts if layout.name == "Edit")
        window_layout = next(layout for layout in layouts if layout.name == "Window")
        profiler_layout = next(layout for layout in layouts if layout.name == "Profiler")

        self.assertFalse(file_layout.remove)
        self.assertFalse(edit_layout.remove)
        self.assertFalse(window_layout.remove)
        self.assertFalse(profiler_layout.remove)
        self.assertEqual([item.name for item in edit_layout.items], ["Undo", "Advanced"])
        self.assertTrue(edit_layout.items[0].remove)
        self.assertTrue(edit_layout.items[1].remove)
        self.assertEqual([item.name for item in window_layout.items], ["Debug"])
        self.assertTrue(window_layout.items[0].remove)

    async def test_missing_ignore_file_logs_warning_and_keeps_everything_visible(self):
        with (
            patch("lightspeed.trex.app.setup.setup_ui._get_menubar_ignore_file", return_value=None),
            patch("lightspeed.trex.app.setup.setup_ui.carb.log_warn") as log_warn_mock,
        ):
            menubar_ignore = MenubarIgnore()

        log_warn_mock.assert_called_once_with("No menubar ignore file found!")
        self.assertFalse(menubar_ignore.is_ignored("Edit/Preferences"))

    async def test_print_menus_prints_nested_layout_paths(self):
        menubar_ignore = MenubarIgnore.__new__(MenubarIgnore)
        menu_layouts = [
            MenuLayout.Menu(
                "Edit",
                [
                    MenuLayout.SubMenu("Advanced", [MenuLayout.Item("Hidden")]),
                    MenuLayout.Item("Undo"),
                ],
            )
        ]
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            menubar_ignore.print_menus(menu_layouts)

        self.assertEqual(
            stdout.getvalue().splitlines(), ["/Edit/", "/Edit/Advanced/", "/Edit/Advanced/Hidden", "/Edit/Undo"]
        )


class TestTrexSetupExtension(omni.kit.test.AsyncTestCase):
    async def test_startup_creates_setup_ui(self):
        extension = TrexSetupExtension()

        with patch("lightspeed.trex.app.setup.extension.SetupUI") as setup_ui_mock:
            extension.on_startup("ext_id")

        setup_ui_mock.assert_called_once_with()
        self.assertEqual(extension._setup_ui, setup_ui_mock.return_value)

    async def test_shutdown_destroys_setup_ui(self):
        extension = TrexSetupExtension()
        setup_ui = MagicMock()
        extension._setup_ui = setup_ui

        extension.on_shutdown()

        setup_ui.destroy.assert_called_once_with()
        self.assertIsNone(extension._setup_ui)
