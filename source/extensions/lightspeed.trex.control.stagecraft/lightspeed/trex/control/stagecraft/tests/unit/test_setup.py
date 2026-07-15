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

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import omni.kit.test
import omni.usd
from lightspeed.layer_manager.core import LayerType as _LayerType
import lightspeed.trex.control.stagecraft.setup as _setup_module
from lightspeed.trex.control.stagecraft.setup import Setup


class TestSetup(omni.kit.test.AsyncTestCase):
    async def test_on_undo_shows_dialog_when_next_undo_is_capture_swap(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._stage_core_setup = MagicMock()
        setup._capture_swap_undo_dialog_open = False

        history = {
            1: SimpleNamespace(name="SwitchCaptureCommand"),
        }

        # Act
        with (
            patch("lightspeed.trex.control.stagecraft.setup.omni.kit.undo.can_undo", return_value=True),
            patch(
                "lightspeed.trex.control.stagecraft.setup.omni.kit.undo.get_undo_stack", return_value=history.values()
            ),
            patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog") as mock_dialog,
        ):
            setup._on_undo()

        # Assert
        setup._stage_core_setup.undo.assert_not_called()
        dialog_kwargs = mock_dialog.call_args.kwargs
        self.assertEqual(
            "Undoing this action will change the loaded capture.\n\nDo you want to load the previous capture?",
            dialog_kwargs["message"],
        )
        self.assertEqual("Undo Capture Change", dialog_kwargs["title"])
        self.assertEqual("Load Capture", dialog_kwargs["ok_label"])
        self.assertEqual("Cancel", dialog_kwargs["cancel_label"])
        self.assertTrue(setup._capture_swap_undo_dialog_open)

    async def test_on_undo_runs_stage_undo_when_capture_swap_is_not_next(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._stage_core_setup = MagicMock()
        setup._capture_swap_undo_dialog_open = False

        history = {1: SimpleNamespace(name="TransformPrimCommand")}

        # Act
        with (
            patch("lightspeed.trex.control.stagecraft.setup.omni.kit.undo.can_undo", return_value=True),
            patch(
                "lightspeed.trex.control.stagecraft.setup.omni.kit.undo.get_undo_stack", return_value=history.values()
            ),
            patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog") as mock_dialog,
        ):
            setup._on_undo()

        # Assert
        setup._stage_core_setup.undo.assert_called_once_with()
        mock_dialog.assert_not_called()
        self.assertFalse(setup._capture_swap_undo_dialog_open)

    async def test_dialog_ok_handler_runs_stage_undo(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._stage_core_setup = MagicMock()
        setup._capture_swap_undo_dialog_open = False

        with patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog") as mock_dialog:
            setup._show_capture_swap_undo_dialog()

        ok_handler = mock_dialog.call_args.kwargs["ok_handler"]
        ok_handler()

        setup._stage_core_setup.undo.assert_called_once_with()
        self.assertFalse(setup._capture_swap_undo_dialog_open)

    async def test_dialog_cancel_handler_keeps_stage_unchanged(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._stage_core_setup = MagicMock()
        setup._capture_swap_undo_dialog_open = False

        with patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog") as mock_dialog:
            setup._show_capture_swap_undo_dialog()

        cancel_handler = mock_dialog.call_args.kwargs["cancel_handler"]
        cancel_handler()

        setup._stage_core_setup.undo.assert_not_called()
        self.assertFalse(setup._capture_swap_undo_dialog_open)

    async def test_capture_swap_with_existing_capture_executes_single_command(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = ""
        setup._capture_core_setup = MagicMock()
        setup._replacement_core_setup = MagicMock()
        setup._update_modding_button_state = MagicMock()
        setup._capture_core_setup.get_layer.return_value = SimpleNamespace(identifier="/captures/capture_a.usda")

        with (
            patch(
                "lightspeed.trex.control.stagecraft.setup.omni.client.normalize_url",
                return_value="/captures/capture_b.usda",
            ),
            patch("lightspeed.trex.control.stagecraft.setup.omni.kit.commands.execute") as mock_execute,
        ):
            # Act
            setup._on_import_layer(_LayerType.capture, "/captures/capture_b.usda")

        # Assert
        mock_execute.assert_called_once_with(
            "SwitchCaptureCommand",
            new_capture_path="/captures/capture_b.usda",
            context_name=setup._context_name,
        )
        setup._capture_core_setup.import_capture_layer.assert_not_called()
        setup._update_modding_button_state.assert_called_once_with()

    async def test_capture_swap_same_capture_short_circuits(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = ""
        setup._capture_core_setup = MagicMock()
        setup._replacement_core_setup = MagicMock()
        setup._update_modding_button_state = MagicMock()
        setup._capture_core_setup.get_layer.return_value = SimpleNamespace(identifier="/captures/capture_a.usda")

        with (
            patch(
                "lightspeed.trex.control.stagecraft.setup.omni.client.normalize_url",
                return_value="/captures/capture_a.usda",
            ),
            patch("lightspeed.trex.control.stagecraft.setup.omni.kit.commands.execute") as mock_execute,
        ):
            # Act
            setup._on_import_layer(_LayerType.capture, "/captures/capture_a.usda")

        # Assert
        mock_execute.assert_not_called()
        setup._capture_core_setup.import_capture_layer.assert_not_called()
        setup._update_modding_button_state.assert_called_once_with()

    async def test_capture_import_without_existing_capture_bypasses_command_and_undo(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._capture_core_setup = MagicMock()
        setup._replacement_core_setup = MagicMock()
        setup._update_modding_button_state = MagicMock()
        setup._capture_core_setup.get_layer.return_value = None

        with patch("lightspeed.trex.control.stagecraft.setup.omni.kit.commands.execute") as mock_execute:
            # Act
            setup._on_import_layer(_LayerType.capture, "/captures/capture_a.usda")

        # Assert
        mock_execute.assert_not_called()
        setup._capture_core_setup.import_capture_layer.assert_called_once_with(
            "/captures/capture_a.usda", do_undo=False
        )
        setup._update_modding_button_state.assert_called_once_with()

    async def test_replacement_import_keeps_existing_behavior(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._capture_core_setup = MagicMock()
        setup._replacement_core_setup = MagicMock()
        setup._update_modding_button_state = MagicMock()

        with patch("lightspeed.trex.control.stagecraft.setup.omni.kit.commands.execute") as mock_execute:
            # Act
            setup._on_import_layer(_LayerType.replacement, "/mods/mod.usda", existing_file=True)

        # Assert
        mock_execute.assert_not_called()
        setup._replacement_core_setup.import_replacement_layer.assert_called_once_with(
            "/mods/mod.usda", use_existing_layer=True
        )
        setup._update_modding_button_state.assert_called_once_with()

    async def test_stage_open_event_checks_capture_and_clears_lighting_undo_suppression(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = "stagecraft"
        setup._update_modding_button_state = MagicMock()
        setup._check_capture_on_open = MagicMock()
        next_update_async = AsyncMock()
        Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = True

        # Act
        with patch("lightspeed.trex.control.stagecraft.setup.omni.kit.app.get_app") as mock_get_app:
            mock_get_app.return_value.next_update_async = next_update_async
            await setup._update_modding_button_state_deferred(int(omni.usd.StageEventType.OPENED))

        # Assert
        next_update_async.assert_awaited_once()
        setup._update_modding_button_state.assert_called_once_with()
        setup._check_capture_on_open.assert_called_once_with()
        self.assertFalse(Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO)

    async def test_non_open_stage_event_does_not_check_capture(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = "stagecraft"
        setup._update_modding_button_state = MagicMock()
        setup._check_capture_on_open = MagicMock()
        next_update_async = AsyncMock()
        Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = True

        # Act
        with patch("lightspeed.trex.control.stagecraft.setup.omni.kit.app.get_app") as mock_get_app:
            mock_get_app.return_value.next_update_async = next_update_async
            await setup._update_modding_button_state_deferred(int(omni.usd.StageEventType.CLOSING))

        # Assert
        next_update_async.assert_awaited_once()
        setup._update_modding_button_state.assert_called_once_with()
        setup._check_capture_on_open.assert_not_called()
        self.assertTrue(Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO)

    async def test_open_stage_loads_workspace_and_suppresses_stage_open_lighting_undo(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = "stagecraft"
        Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = False

        # Act
        with (
            patch(
                "lightspeed.trex.control.stagecraft.setup._ProjectWizardSchema.is_project_file_valid", return_value=True
            ),
            patch(
                "lightspeed.trex.control.stagecraft.setup._ProjectWizardSchema.are_project_symlinks_valid",
                return_value=True,
            ),
            patch("lightspeed.trex.control.stagecraft.setup.omni.kit.window.file.open_stage") as mock_open_stage,
            patch("lightspeed.trex.control.stagecraft.setup.load_layout") as mock_load_layout,
            patch("lightspeed.trex.control.stagecraft.setup._get_quicklayout_config", return_value="layout"),
        ):
            setup._Setup__open_stage_and_load_layout("C:/project/mod.usda")

        # Assert
        mock_open_stage.assert_called_once_with("C:/project/mod.usda")
        mock_load_layout.assert_called_once_with("layout")
        self.assertTrue(Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO)

    async def test_installed_closure_survives_uninstall_resetting_class_attr(self):
        # Regression: omni.kit.viewport.menubar.lighting subscribes to the
        # stage-open event and holds a strong reference to whatever closure was
        # bound to ``_MenuContainer__on_stage_open`` AT SUBSCRIPTION TIME. If
        # ``__uninstall_stage_open_lighting_undo_patch`` later runs (or the
        # extension is hot-reloaded) the class attribute
        # ``_LIGHTING_STAGE_OPEN_ORIGINAL`` is reset to ``None``. An in-flight
        # event firing after that reset would dereference None and raise
        # ``TypeError: 'NoneType' object is not callable``, which has been
        # observed to cascade into a GPU crash during HL2 stage open. The fix
        # is to capture the original as a closure-local — pin that contract.
        original_disable_lighting_undo = Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO
        original_class_attr = Setup._LIGHTING_STAGE_OPEN_ORIGINAL
        original_on_stage_open = MagicMock(name="original_on_stage_open", return_value="sentinel")
        Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = False
        Setup._LIGHTING_STAGE_OPEN_ORIGINAL = None
        try:
            with patch(
                "lightspeed.trex.control.stagecraft.setup._ViewportLightingMenuContainer._MenuContainer__on_stage_open",
                new=original_on_stage_open,
            ):
                # Install captures the original, replaces the attribute with a closure.
                Setup._Setup__install_stage_open_lighting_undo_patch()
                installed_closure = _setup_module._ViewportLightingMenuContainer._MenuContainer__on_stage_open
                self.assertIsNot(installed_closure, original_on_stage_open)

                # Uninstall restores the original AND sets the class attr to None.
                Setup._Setup__uninstall_stage_open_lighting_undo_patch()
                self.assertIsNone(Setup._LIGHTING_STAGE_OPEN_ORIGINAL)

                # The closure is what a late event subscription would still hold.
                # Calling it after uninstall must NOT crash — it should call the
                # local-captured original, not deref the (now-None) class attr.
                result = installed_closure(
                    MagicMock(name="menu_container"),
                    MagicMock(name="menu_context"),
                    "stagecraft",
                    MagicMock(name="usd_context"),
                    MagicMock(name="prev_mode"),
                )
                self.assertEqual(
                    result, "sentinel", "post-uninstall closure call must delegate to the captured original"
                )
                original_on_stage_open.assert_called_once()
        finally:
            Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = original_disable_lighting_undo
            Setup._LIGHTING_STAGE_OPEN_ORIGINAL = original_class_attr

    async def test_destroy_restores_stage_open_lighting_patch(self):
        # Arrange
        setup = Setup.__new__(Setup)
        setup._context_name = "stagecraft"
        original_on_stage_open = object()
        original_disable_lighting_undo = Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO
        Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = True

        # Act
        with (
            patch.object(Setup, "_LIGHTING_STAGE_OPEN_ORIGINAL", original_on_stage_open),
            patch(
                "lightspeed.trex.control.stagecraft.setup._ViewportLightingMenuContainer._MenuContainer__on_stage_open",
                new=MagicMock(),
            ),
            patch("lightspeed.trex.control.stagecraft.setup._reset_default_attrs") as mock_reset_default_attrs,
        ):
            setup.destroy()

            # Assert
            self.assertIs(
                original_on_stage_open,
                _setup_module._ViewportLightingMenuContainer._MenuContainer__on_stage_open,
            )
            self.assertIsNone(Setup._LIGHTING_STAGE_OPEN_ORIGINAL)
            self.assertFalse(Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO)
            mock_reset_default_attrs.assert_called_once_with(setup)

        Setup._DISABLE_STAGE_OPEN_LIGHTING_UNDO = original_disable_lighting_undo

    # --- Capture GPU device-loss / hang safe mode ------------------------------------------------

    async def test_open_stage_applies_capture_safe_mode_before_open_stage(self):
        # Regression: the earlier gate disabled Opacity Micromaps on the stage-OPENED event, i.e.
        # AFTER the capture was already realized and could fault/hang the GPU. The override MUST run
        # before ``open_stage``. This pins that ordering.
        setup = Setup.__new__(Setup)
        calls = []
        setup._apply_capture_safe_mode = MagicMock(side_effect=lambda project_path: calls.append("safe_mode"))

        with (
            patch("lightspeed.trex.control.stagecraft.setup._ProjectWizardSchema") as mock_schema,
            patch("lightspeed.trex.control.stagecraft.setup._should_confirm_link_path_replacement", return_value=False),
            patch(
                "lightspeed.trex.control.stagecraft.setup.omni.kit.window.file.open_stage",
                side_effect=lambda path: calls.append("open_stage"),
            ),
            patch("lightspeed.trex.control.stagecraft.setup.load_layout"),
            patch("lightspeed.trex.control.stagecraft.setup._get_quicklayout_config"),
            patch.object(Setup, "_Setup__set_stage_open_lighting_undo_disabled"),
        ):
            mock_schema.is_project_file_valid.return_value = True
            mock_schema.is_deps_directory_valid.return_value = True
            mock_schema.are_project_symlinks_valid.return_value = True
            setup._Setup__open_stage_and_load_layout("C:/proj/TRLRTX.usda")

        # Assert: safe mode applied first, then the stage is opened.
        self.assertEqual(calls, ["safe_mode", "open_stage"])
        setup._apply_capture_safe_mode.assert_called_once()

    async def test_apply_capture_safe_mode_arms_when_enabled(self):
        # With the toggle on, opening any capture project disables OMM (push), remembers the source,
        # and starts the periodic re-assert watchdog.
        setup = Setup.__new__(Setup)
        setup._safe_mode_capture_path = None
        setup._push_stability_configvars = MagicMock()
        setup._start_reassert_watchdog = MagicMock()

        mock_settings = MagicMock()
        mock_settings.get.return_value = True  # autoDisableOpacityMicromaps enabled

        from pathlib import Path as _Path  # noqa: PLC0415

        with patch("lightspeed.trex.control.stagecraft.setup.carb.settings.get_settings", return_value=mock_settings):
            setup._apply_capture_safe_mode(_Path("C:/proj/TRLRTX.usda"))

        setup._push_stability_configvars.assert_called_once_with()
        setup._start_reassert_watchdog.assert_called_once_with()
        self.assertEqual(setup._safe_mode_capture_path, "c:/proj/trlrtx.usda")

    async def test_apply_capture_safe_mode_disabled_when_toggle_off(self):
        # With the toggle off, nothing is pushed and any prior watchdog is torn down.
        setup = Setup.__new__(Setup)
        setup._safe_mode_capture_path = "c:/old/trlrtx.usda"
        setup._stop_reassert_watchdog = MagicMock()
        setup._push_stability_configvars = MagicMock()

        mock_settings = MagicMock()
        mock_settings.get.return_value = False

        from pathlib import Path as _Path  # noqa: PLC0415

        with patch("lightspeed.trex.control.stagecraft.setup.carb.settings.get_settings", return_value=mock_settings):
            setup._apply_capture_safe_mode(_Path("C:/proj/TRLRTX.usda"))

        setup._stop_reassert_watchdog.assert_called_once_with()
        setup._push_stability_configvars.assert_not_called()
        self.assertIsNone(setup._safe_mode_capture_path)

    async def test_apply_capture_safe_mode_on_switch_reasserts_when_armed(self):
        # Switching capture while safe mode is already armed just re-asserts the override.
        setup = Setup.__new__(Setup)
        setup._safe_mode_capture_path = "c:/proj/trlrtx.usda"
        setup._reassert_overrides_if_active = MagicMock()
        setup._arm_safe_mode = MagicMock()

        mock_settings = MagicMock()
        mock_settings.get.return_value = True

        with patch("lightspeed.trex.control.stagecraft.setup.carb.settings.get_settings", return_value=mock_settings):
            setup._apply_capture_safe_mode_on_switch("c:/proj/deps/captures/england__5.usd")

        setup._reassert_overrides_if_active.assert_called_once_with()
        setup._arm_safe_mode.assert_not_called()

    async def test_apply_capture_safe_mode_on_switch_arms_when_not_armed(self):
        # Switching capture when safe mode is not yet armed arms it for the switched-to capture.
        setup = Setup.__new__(Setup)
        setup._safe_mode_capture_path = None
        setup._arm_safe_mode = MagicMock()

        mock_settings = MagicMock()
        mock_settings.get.return_value = True

        with patch("lightspeed.trex.control.stagecraft.setup.carb.settings.get_settings", return_value=mock_settings):
            setup._apply_capture_safe_mode_on_switch("c:/proj/deps/captures/england__5.usd")

        setup._arm_safe_mode.assert_called_once_with("c:/proj/deps/captures/england__5.usd")

    async def test_reassert_watch_loop_reasserts_configvars(self):
        # The pre-open push only covers initial realization; dxvk-remix re-applies the capture's own
        # preset a few seconds later (re-enabling OMM / NRC) WITHOUT touching the /rtx/* carb nodes,
        # so the periodic watchdog is what corrects the drift -- it must re-push every tick while a
        # capture stays loaded.
        setup = Setup.__new__(Setup)
        setup._safe_mode_capture_path = "c:/proj/deps/captures/bolivia__2.usd"

        ticks = {"count": 0}

        def _push_and_eventually_close():
            ticks["count"] += 1
            if ticks["count"] >= 2:
                setup._safe_mode_capture_path = None  # simulate the project closing after two re-asserts

        setup._push_stability_configvars = MagicMock(side_effect=_push_and_eventually_close)

        with patch("lightspeed.trex.control.stagecraft.setup.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await setup._reassert_watch_loop(5.0)

        self.assertEqual(setup._push_stability_configvars.call_count, 2)
        mock_sleep.assert_awaited_with(5.0)
        self.assertIsNone(setup._safe_mode_capture_path)

    async def test_reassert_watch_loop_noop_when_safe_mode_inactive(self):
        # Safe mode not armed -> the loop exits immediately without sleeping or pushing.
        setup = Setup.__new__(Setup)
        setup._safe_mode_capture_path = None
        setup._push_stability_configvars = MagicMock()

        with patch("lightspeed.trex.control.stagecraft.setup.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await setup._reassert_watch_loop(5.0)

        mock_sleep.assert_not_awaited()
        setup._push_stability_configvars.assert_not_called()

    async def test_reassert_watch_loop_survives_push_failure(self):
        # A transient runtime hiccup during a re-assert must not kill the loop; it should log and
        # keep protecting the session until the project closes.
        setup = Setup.__new__(Setup)
        setup._safe_mode_capture_path = "c:/proj/deps/captures/bolivia__2.usd"

        ticks = {"count": 0}

        def _flaky_push():
            ticks["count"] += 1
            if ticks["count"] == 1:
                raise RuntimeError("HdRemix not ready")
            setup._safe_mode_capture_path = None

        setup._push_stability_configvars = MagicMock(side_effect=_flaky_push)

        with (
            patch("lightspeed.trex.control.stagecraft.setup.asyncio.sleep", new=AsyncMock()),
            patch("lightspeed.trex.control.stagecraft.setup.carb.log_warn") as mock_log_warn,
        ):
            await setup._reassert_watch_loop(5.0)

        self.assertEqual(setup._push_stability_configvars.call_count, 2)
        mock_log_warn.assert_called_once()

    async def test_start_reassert_watchdog_disabled_when_interval_non_positive(self):
        # Interval <= 0 disables the periodic re-assert entirely.
        setup = Setup.__new__(Setup)
        setup._reassert_watch_task = None
        mock_settings = MagicMock()
        mock_settings.get.return_value = 0

        with (
            patch("lightspeed.trex.control.stagecraft.setup.carb.settings.get_settings", return_value=mock_settings),
            patch("lightspeed.trex.control.stagecraft.setup.ensure_future") as mock_ensure_future,
        ):
            setup._start_reassert_watchdog()

        mock_ensure_future.assert_not_called()
        self.assertIsNone(setup._reassert_watch_task)

    async def test_start_reassert_watchdog_creates_task(self):
        # A positive interval schedules the watch loop exactly once.
        setup = Setup.__new__(Setup)
        setup._reassert_watch_task = None
        mock_settings = MagicMock()
        mock_settings.get.return_value = 5.0
        sentinel_task = MagicMock()
        sentinel_task.done.return_value = False

        with (
            patch("lightspeed.trex.control.stagecraft.setup.carb.settings.get_settings", return_value=mock_settings),
            patch("lightspeed.trex.control.stagecraft.setup.ensure_future", return_value=sentinel_task) as mock_ef,
            # Avoid building a real coroutine (and its "never awaited" warning) since ensure_future is mocked.
            patch.object(Setup, "_reassert_watch_loop", return_value=MagicMock()),
        ):
            setup._start_reassert_watchdog()

        mock_ef.assert_called_once()
        self.assertIs(setup._reassert_watch_task, sentinel_task)

    async def test_stop_reassert_watchdog_cancels_task(self):
        setup = Setup.__new__(Setup)
        task = MagicMock()
        task.done.return_value = False
        setup._reassert_watch_task = task

        setup._stop_reassert_watchdog()

        task.cancel.assert_called_once_with()
        self.assertIsNone(setup._reassert_watch_task)
