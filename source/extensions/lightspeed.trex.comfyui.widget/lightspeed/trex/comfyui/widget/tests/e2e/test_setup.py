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

from unittest.mock import AsyncMock, MagicMock, call, patch

import omni.kit.app
import omni.kit.clipboard
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardInput
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from lightspeed.trex.comfyui.core.enums import ComfyUIEventType, ComfyUIProtocol, ComfyUIState
from lightspeed.trex.comfyui.widget.setup.widget import ComfySetupAdvancedWidget
from omni import ui
from omni.kit.test_suite.helpers import arrange_windows

_TEST_WINDOW_WIDTH = ui.Pixel(800)
_TEST_WINDOW_HEIGHT = ui.Pixel(300)


class TestComfySetupAdvancedWidgetE2E(AsyncTestCase):
    """Test advanced setup behavior against real omni.ui models."""

    async def setUp(self):
        """Arrange a clean window workspace for each UI test."""
        await arrange_windows()

    @staticmethod
    async def _destroy_widget(window: ui.Window, widget: ComfySetupAdvancedWidget) -> None:
        """Destroy one test widget and settle its window before the next test.

        Args:
            window: Test window that owns the setup widget.
            widget: Setup widget rendered in the test window.
        """
        widget.destroy()
        window.destroy()
        await omni.kit.app.get_app().next_update_async()

    async def _create_widget(self, window_name: str, width=_TEST_WINDOW_WIDTH):
        """Build an advanced setup widget and advance one Kit frame.

        Args:
            window_name: Unique title for the test window.
            width: Width of the test window.

        Returns:
            The window, setup widget, and mocked core used by the test.
        """
        core = MagicMock()
        core.state = ComfyUIState.READY
        core.is_connected = False
        core.status_message = ""
        core.last_connection_error = ""
        core.connect = AsyncMock()
        core.shutdown = AsyncMock()
        core.settings.protocol = ComfyUIProtocol.HTTP
        core.settings.host = "127.0.0.1"
        core.settings.port = 8188
        core.settings.set_protocol.side_effect = lambda value: setattr(core.settings, "protocol", value)
        core.settings.set_host.side_effect = lambda value: setattr(core.settings, "host", value)
        core.settings.set_port.side_effect = lambda value: setattr(core.settings, "port", value)
        window = ui.Window(window_name, width=width, height=_TEST_WINDOW_HEIGHT)
        with (
            patch(
                "lightspeed.trex.comfyui.widget.setup.widget.get_comfyui_core_instance",
                return_value=core,
            ),
            patch(
                "lightspeed.trex.comfyui.widget.setup.widget.subscribe_comfyui_event",
                side_effect=lambda _context_name, callback: setattr(core, "event_callback", callback) or MagicMock(),
            ),
        ):
            with window.frame:
                widget = ComfySetupAdvancedWidget(context_name="test-context")
        window.focus()
        await ui_test.human_delay()
        return window, widget, core

    async def test_real_ui_builds_from_core_settings(self):
        """The real UI initializes its models from persisted core settings."""
        window, widget, core = await self._create_widget("comfy_setup_advanced_build")
        try:
            # Query the live endpoint controls created from the core's persisted settings.
            host = ui_test.find("comfy_setup_advanced_build//Frame/**/StringField[*].identifier=='ComfySetupHost'")
            port = ui_test.find("comfy_setup_advanced_build//Frame/**/IntField[*].identifier=='ComfySetupPort'")
            banner = ui_test.find(
                "comfy_setup_advanced_build//Frame/**/Rectangle[*].identifier=='ComfySetupStatusBanner'"
            )
            status_title = ui_test.find("comfy_setup_advanced_build//Frame/**/Label[*].name=='ComfyUIStatusTitle'")
            detail = ui_test.find("comfy_setup_advanced_build//Frame/**/Label[*].name=='ComfyUIStatusDetail'")
            connect = ui_test.find("comfy_setup_advanced_build//Frame/**/Button[*].identifier=='ComfySetupConnect'")

            # Models, banner state, and the primary action all reflect the disconnected endpoint.
            self.assertEqual(host.widget.model.as_string, "127.0.0.1")
            self.assertEqual(port.widget.model.as_int, 8188)
            self.assertEqual(banner.widget.name, "ComfyUIStatusDisconnected")
            self.assertIsNotNone(status_title)
            self.assertEqual(status_title.widget.text, "Disconnected")
            title_style = ui.Style.get_instance().default.get("Label::ComfyUIStatusTitle", {})
            detail_style = ui.Style.get_instance().default.get("Label::ComfyUIStatusDetail", {})
            self.assertTrue(title_style.get("font", "").endswith("NVIDIASans_A_Bd.ttf"))
            self.assertEqual(title_style.get("font_size"), 16)
            self.assertNotIn("font", detail_style)
            self.assertNotIn("font_size", detail_style)
            self.assertTrue(detail.widget.visible)
            self.assertEqual(
                detail.widget.text, "ComfyUI is disconnected. Enter the server address, then select Connect."
            )
            self.assertEqual(connect.widget.text, "Connect")
            self.assertTrue(connect.widget.enabled)
        finally:
            await self._destroy_widget(window, widget)

    async def test_real_ui_renders_setup_tabs_and_backgrounds(self):
        """The setup UI shows Managed as unavailable and External as the active mode."""
        window, widget, _core = await self._create_widget("comfy_setup_tabs")
        try:
            # Locate both setup modes, their backgrounds, and the external endpoint controls.
            managed = ui_test.find("comfy_setup_tabs//Frame/**/Label[*].text=='Managed'")
            external = ui_test.find("comfy_setup_tabs//Frame/**/Label[*].text=='External'")
            banner = ui_test.find("comfy_setup_tabs//Frame/**/Rectangle[*].identifier=='ComfySetupStatusBanner'")
            managed_background = ui_test.find(
                "comfy_setup_tabs//Frame/**/Rectangle[*].identifier=='ComfySetupManagedTab'"
            )
            external_background = ui_test.find(
                "comfy_setup_tabs//Frame/**/Rectangle[*].identifier=='ComfySetupExternalTab'"
            )
            content_background = ui_test.find("comfy_setup_tabs//Frame/**/Rectangle[*].identifier=='ComfySetupContent'")
            # Managed is visibly unavailable while External owns the active content background.
            self.assertIsNotNone(managed)
            self.assertEqual(managed.widget.name, "PropertiesWidgetLabelDisabled")
            self.assertIsNotNone(external)
            self.assertEqual(external.widget.name, "PropertiesWidgetLabel")
            self.assertEqual(banner.widget.name, "ComfyUIStatusDisconnected")
            self.assertIsNotNone(managed_background)
            self.assertEqual(managed_background.widget.name, "TransparentBackground")
            self.assertIsNotNone(external_background)
            self.assertEqual(external_background.widget.name, "WorkspaceBackground")
            self.assertIsNotNone(content_background)
            self.assertEqual(content_background.widget.name, "WorkspaceBackground")
            self.assertEqual(
                len(ui_test.find_all("comfy_setup_tabs//Frame/**/Rectangle[*].name=='TabBackground'")),
                1,
            )
            self.assertIsNotNone(
                ui_test.find("comfy_setup_tabs//Frame/**/ComboBox[*].identifier=='ComfySetupProtocol'")
            )
            self.assertIsNotNone(ui_test.find("comfy_setup_tabs//Frame/**/StringField[*].identifier=='ComfySetupHost'"))
            self.assertIsNotNone(ui_test.find("comfy_setup_tabs//Frame/**/IntField[*].identifier=='ComfySetupPort'"))
            self.assertIsNotNone(ui_test.find("comfy_setup_tabs//Frame/**/Button[*].identifier=='ComfySetupConnect'"))
        finally:
            await self._destroy_widget(window, widget)

    async def test_full_url_updates_protocol_once_and_uses_standard_port(self):
        """Editing the real host field with HTTPS updates all endpoint controls."""
        window, widget, core = await self._create_widget("comfy_setup_advanced_url")
        try:
            core.settings.set_protocol.reset_mock()
            core.settings.set_host.reset_mock()
            core.settings.set_port.reset_mock()
            host = ui_test.find("comfy_setup_advanced_url//Frame/**/StringField[*].identifier=='ComfySetupHost'")
            protocol = ui_test.find("comfy_setup_advanced_url//Frame/**/ComboBox[*].identifier=='ComfySetupProtocol'")
            port = ui_test.find("comfy_setup_advanced_url//Frame/**/IntField[*].identifier=='ComfySetupPort'")

            # Enter a complete HTTPS URL into the host field like a user would.
            await host.click()
            await ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
            await host.input("https://comfy.example.com", end_key=KeyboardInput.ENTER)
            await ui_test.human_delay()

            # URL parsing updates each persisted endpoint component once and renders the standard HTTPS port.
            core.settings.set_protocol.assert_called_once_with(ComfyUIProtocol.HTTPS)
            core.settings.set_host.assert_called_once_with("comfy.example.com")
            core.settings.set_port.assert_called_once_with(443)
            self.assertEqual(protocol.widget.model.get_item_value_model().as_int, 1)
            self.assertEqual(host.widget.model.as_string, "comfy.example.com")
            self.assertEqual(port.widget.model.as_int, 443)
        finally:
            await self._destroy_widget(window, widget)

    @patch(
        "lightspeed.trex.comfyui.widget.setup.widget.get_connected_endpoint",
        return_value=("https", "comfy.example.com", 443),
    )
    async def test_connection_events_and_actions_update_real_controls(self, endpoint_mock):
        """Server events and user clicks keep the rendered connection controls synchronized."""
        window, widget, core = await self._create_widget("comfy_setup_connection_states")
        try:
            connect = ui_test.find("comfy_setup_connection_states//Frame/**/Button[*].identifier=='ComfySetupConnect'")
            protocol = ui_test.find(
                "comfy_setup_connection_states//Frame/**/ComboBox[*].identifier=='ComfySetupProtocol'"
            )
            host = ui_test.find("comfy_setup_connection_states//Frame/**/StringField[*].identifier=='ComfySetupHost'")
            port = ui_test.find("comfy_setup_connection_states//Frame/**/IntField[*].identifier=='ComfySetupPort'")
            standard_port = ui_test.find(
                "comfy_setup_connection_states//Frame/**/Image[*].identifier=='ComfySetupStandardPort'"
            )

            def find_status():
                return (
                    ui_test.find(
                        "comfy_setup_connection_states//Frame/**/Rectangle[*].identifier=='ComfySetupStatusBanner'"
                    ),
                    ui_test.find("comfy_setup_connection_states//Frame/**/Label[*].name=='ComfyUIStatusTitle'"),
                    ui_test.find("comfy_setup_connection_states//Frame/**/Label[*].name=='ComfyUIStatusDetail'"),
                )

            def find_actions(identifier):
                return ui_test.find_all(f"comfy_setup_connection_states//Frame/**/Button[*].identifier=='{identifier}'")

            banner, status_title, detail = find_status()
            self.assertEqual(banner.widget.name, "ComfyUIStatusDisconnected")
            self.assertTrue(detail.widget.visible)
            self.assertEqual([], find_actions("ComfySetupOpenBrowser"))
            self.assertEqual([], find_actions("ComfySetupShowLogs"))

            # Connect from the rendered button, then deliver the real state transitions consumed by the widget.
            await connect.click()
            await ui_test.human_delay()
            core.connect.assert_awaited_once_with()

            notify = core.event_callback
            core.state = ComfyUIState.STARTING
            notify(MagicMock(event_type=ComfyUIEventType.STATE_CHANGED))
            await ui_test.human_delay()
            banner, status_title, detail = find_status()
            self.assertEqual(connect.widget.text, "Connecting...")
            self.assertFalse(connect.widget.enabled)
            self.assertFalse(protocol.widget.enabled)
            self.assertFalse(host.widget.enabled)
            self.assertFalse(port.widget.enabled)
            self.assertFalse(standard_port.widget.enabled)
            self.assertEqual(banner.widget.name, "ComfyUIStatusConnecting")
            self.assertEqual(status_title.widget.text, "Connecting")
            self.assertTrue(detail.widget.visible)
            self.assertEqual(detail.widget.text, "Connecting to the configured ComfyUI server.")
            self.assertEqual([], find_actions("ComfySetupOpenBrowser"))
            self.assertEqual([], find_actions("ComfySetupShowLogs"))

            # A running event replaces the busy state with connected controls and a Disconnect action.
            core.state = ComfyUIState.RUNNING
            core.is_connected = True
            notify(MagicMock(event_type=ComfyUIEventType.STATE_CHANGED))
            await ui_test.human_delay()
            banner, status_title, detail = find_status()
            self.assertEqual(banner.widget.name, "ComfyUIStatusConnected")
            self.assertEqual(status_title.widget.text, "Connected")
            self.assertTrue(detail.widget.visible)
            self.assertEqual(detail.widget.text, "https://comfy.example.com:443")
            self.assertEqual(connect.widget.text, "Disconnect")
            self.assertTrue(connect.widget.enabled)
            open_button = ui_test.find(
                "comfy_setup_connection_states//Frame/**/Button[*].identifier=='ComfySetupOpenBrowser'"
            )
            self.assertIsNotNone(open_button)
            self.assertTrue(open_button.widget.enabled)
            self.assertEqual([], find_actions("ComfySetupShowLogs"))

            # A stale RUNNING state without a verified endpoint cannot offer a browser action.
            endpoint_mock.return_value = None
            notify(MagicMock(event_type=ComfyUIEventType.STATE_CHANGED))
            await ui_test.human_delay()
            banner, status_title, detail = find_status()
            self.assertEqual(banner.widget.name, "ComfyUIStatusDisconnected")
            self.assertEqual(status_title.widget.text, "Connection Unavailable")
            self.assertEqual(
                detail.widget.text,
                "The verified ComfyUI endpoint is unavailable. Disconnect and reconnect to restore the connection.",
            )
            self.assertEqual(connect.widget.text, "Disconnect")
            self.assertTrue(connect.widget.enabled)
            self.assertEqual([], find_actions("ComfySetupOpenBrowser"))
            self.assertEqual([], find_actions("ComfySetupShowLogs"))

            # Disconnect through the same primary action, then surface a later connection failure.
            await connect.click()
            await ui_test.human_delay()
            core.shutdown.assert_awaited_once_with()

            core.state = ComfyUIState.ERROR
            core.is_connected = False
            core.status_message = "The server did not respond."
            notify(MagicMock(event_type=ComfyUIEventType.STATE_CHANGED))
            await ui_test.human_delay()
            banner, status_title, detail = find_status()
            # Failure restores editable endpoint controls and presents a user-facing retry state.
            self.assertEqual(banner.widget.name, "ComfyUIStatusError")
            self.assertEqual(status_title.widget.text, "Connection Failed")
            self.assertTrue(detail.widget.visible)
            self.assertEqual(detail.widget.text, "The server did not respond.")
            self.assertEqual(connect.widget.text, "Retry")
            self.assertTrue(protocol.widget.enabled)
            self.assertTrue(host.widget.enabled)
            self.assertTrue(port.widget.enabled)
            self.assertTrue(standard_port.widget.enabled)
            self.assertEqual([], find_actions("ComfySetupOpenBrowser"))
            show_logs_button = ui_test.find(
                "comfy_setup_connection_states//Frame/**/Button[*].identifier=='ComfySetupShowLogs'"
            )
            self.assertIsNotNone(show_logs_button)
            self.assertTrue(show_logs_button.widget.enabled)
        finally:
            await self._destroy_widget(window, widget)

    @patch(
        "lightspeed.trex.comfyui.widget.setup.widget.get_connected_endpoint",
        return_value=("https", "a-very-long-comfyui-server-name.example.com", 443),
    )
    async def test_status_banner_wraps_every_state_at_narrow_width(self, endpoint_mock):
        """Every banner state remains readable and contained in a narrow window."""
        window_name = "comfy_setup_narrow_status_banner"
        window, widget, core = await self._create_widget(window_name, width=ui.Pixel(320))
        try:

            def find_status():
                return (
                    ui_test.find(f"{window_name}//Frame/**/Rectangle[*].identifier=='ComfySetupStatusBanner'"),
                    ui_test.find(f"{window_name}//Frame/**/Label[*].name=='ComfyUIStatusTitle'"),
                    ui_test.find(f"{window_name}//Frame/**/Label[*].name=='ComfyUIStatusDetail'"),
                )

            def find_actions(identifier):
                return ui_test.find_all(f"{window_name}//Frame/**/Button[*].identifier=='{identifier}'")

            banner, status_title, detail = find_status()

            def assert_inside_banner(control):
                banner_left = banner.center.x - (banner.size.x / 2)
                banner_right = banner.center.x + (banner.size.x / 2)
                banner_top = banner.center.y - (banner.size.y / 2)
                banner_bottom = banner.center.y + (banner.size.y / 2)
                control_left = control.center.x - (control.size.x / 2)
                control_right = control.center.x + (control.size.x / 2)
                control_top = control.center.y - (control.size.y / 2)
                control_bottom = control.center.y + (control.size.y / 2)
                self.assertGreaterEqual(control_left, banner_left - 1)
                self.assertLessEqual(control_right, banner_right + 1)
                self.assertGreaterEqual(control_top, banner_top - 1)
                self.assertLessEqual(control_bottom, banner_bottom + 1)

            def assert_compact_right_aligned(control):
                banner_right = banner.center.x + (banner.size.x / 2)
                detail_right = detail.center.x + (detail.size.x / 2)
                title_top = status_title.center.y - (status_title.size.y / 2)
                detail_bottom = detail.center.y + (detail.size.y / 2)
                control_left = control.center.x - (control.size.x / 2)
                control_right = control.center.x + (control.size.x / 2)
                self.assertLess(control.size.x, banner.size.x / 2)
                self.assertGreater(control.center.x, detail.center.x)
                self.assertGreaterEqual(control_left, detail_right)
                self.assertGreaterEqual(control.center.y, title_top)
                self.assertLessEqual(control.center.y, detail_bottom)
                self.assertAlmostEqual(control_right, banner_right - 16, delta=5)

            self.assertTrue(status_title.widget.word_wrap)
            self.assertTrue(detail.widget.word_wrap)
            self.assertEqual(detail.widget.tooltip, detail.widget.text)
            ready_height = banner.size.y
            assert_inside_banner(status_title)
            assert_inside_banner(detail)
            self.assertEqual([], find_actions("ComfySetupOpenBrowser"))
            self.assertEqual([], find_actions("ComfySetupShowLogs"))

            notify = core.event_callback
            core.state = ComfyUIState.STARTING
            core.status_message = (
                "Connecting to a remote ComfyUI server while its availability and workflow services are verified."
            )
            notify(MagicMock(event_type=ComfyUIEventType.STATE_CHANGED))
            await ui_test.human_delay()
            banner, status_title, detail = find_status()
            self.assertEqual(detail.widget.tooltip, detail.widget.text)
            self.assertGreater(banner.size.y, ready_height)
            assert_inside_banner(status_title)
            assert_inside_banner(detail)
            self.assertEqual([], find_actions("ComfySetupOpenBrowser"))
            self.assertEqual([], find_actions("ComfySetupShowLogs"))

            core.state = ComfyUIState.RUNNING
            core.is_connected = True
            notify(MagicMock(event_type=ComfyUIEventType.STATE_CHANGED))
            await ui_test.human_delay()
            banner, status_title, detail = find_status()
            open_button = ui_test.find(f"{window_name}//Frame/**/Button[*].identifier=='ComfySetupOpenBrowser'")
            self.assertIsNotNone(open_button)
            self.assertEqual(detail.widget.tooltip, detail.widget.text)
            self.assertGreater(banner.size.y, ready_height)
            assert_inside_banner(status_title)
            assert_inside_banner(detail)
            assert_inside_banner(open_button)
            assert_compact_right_aligned(open_button)
            self.assertEqual([], find_actions("ComfySetupShowLogs"))

            endpoint_mock.return_value = None
            notify(MagicMock(event_type=ComfyUIEventType.STATE_CHANGED))
            await ui_test.human_delay()
            banner, status_title, detail = find_status()
            self.assertEqual(status_title.widget.text, "Connection Unavailable")
            self.assertEqual(detail.widget.tooltip, detail.widget.text)
            self.assertGreater(banner.size.y, ready_height)
            assert_inside_banner(status_title)
            assert_inside_banner(detail)
            self.assertEqual([], find_actions("ComfySetupOpenBrowser"))
            self.assertEqual([], find_actions("ComfySetupShowLogs"))

            core.state = ComfyUIState.ERROR
            core.is_connected = False
            core.status_message = (
                "The remote ComfyUI server could not be reached. Check its address and review the persistent logs."
            )
            notify(MagicMock(event_type=ComfyUIEventType.STATE_CHANGED))
            await ui_test.human_delay()
            banner, status_title, detail = find_status()
            show_logs_button = ui_test.find(f"{window_name}//Frame/**/Button[*].identifier=='ComfySetupShowLogs'")
            self.assertIsNotNone(show_logs_button)
            self.assertEqual(detail.widget.tooltip, detail.widget.text)
            self.assertGreater(banner.size.y, ready_height)
            assert_inside_banner(status_title)
            assert_inside_banner(detail)
            assert_inside_banner(show_logs_button)
            assert_compact_right_aligned(show_logs_button)
            self.assertEqual([], find_actions("ComfySetupOpenBrowser"))
        finally:
            await self._destroy_widget(window, widget)

    @patch(
        "lightspeed.trex.comfyui.widget.setup.widget.get_connected_endpoint",
        return_value=("https", "comfy.example.com", 443),
    )
    async def test_open_browser_connected_uses_verified_endpoint(self, endpoint_mock):
        """The connected-server action opens the verified endpoint in a browser."""
        window, widget, core = await self._create_widget("comfy_setup_open_browser")
        try:
            core.state = ComfyUIState.RUNNING
            core.is_connected = True
            widget.update_state_display()
            await ui_test.human_delay()
            open_button = ui_test.find(
                "comfy_setup_open_browser//Frame/**/Button[*].identifier=='ComfySetupOpenBrowser'"
            )

            # A user opens the verified ComfyUI endpoint from the connected banner.
            with (
                patch("lightspeed.trex.comfyui.widget.setup.widget.webbrowser.open", return_value=True) as open_mock,
                patch("lightspeed.trex.comfyui.widget.setup.widget.carb.log_warn") as log_warn_mock,
                patch("lightspeed.trex.comfyui.widget.setup.widget.carb.log_error") as log_error_mock,
            ):
                await open_button.click()
                open_mock.assert_called_once_with("https://comfy.example.com:443", new=0, autoraise=True)

                # A stale enabled button must not open either a missing endpoint or a disconnected core.
                endpoint_mock.return_value = None
                await open_button.click()
                core.state = ComfyUIState.READY
                core.is_connected = False
                await open_button.click()

                open_mock.assert_called_once()
                self.assertEqual(log_warn_mock.call_count, 2)
                log_warn_mock.assert_called_with(
                    "ComfyUI browser action skipped because the connection is no longer verified."
                )

                # Launch failures are contained and leave the recovered connection state unchanged.
                core.state = ComfyUIState.RUNNING
                core.is_connected = True
                endpoint_mock.return_value = ("https", "comfy.example.com", 443)
                open_mock.return_value = False
                await open_button.click()
                open_mock.side_effect = OSError("browser unavailable")
                await open_button.click()

                self.assertEqual(core.state, ComfyUIState.RUNNING)
                self.assertTrue(core.is_connected)
                log_error_mock.assert_has_calls(
                    [
                        call("Could not open the verified ComfyUI endpoint in the default browser."),
                        call(
                            "Could not open the verified ComfyUI endpoint in the default browser: browser unavailable"
                        ),
                    ]
                )
            self.assertEqual(endpoint_mock.call_count, 5)
        finally:
            await self._destroy_widget(window, widget)

    async def test_show_logs_error_opens_selectable_connection_failure_dialog(self):
        """The failed-connection action shows exact details in a selectable multiline field."""
        window, widget, core = await self._create_widget("comfy_setup_show_logs")
        try:
            core.state = ComfyUIState.ERROR
            core.status_message = (
                "Could not connect to ComfyUI. Check the server address and that ComfyUI is running, then try again."
            )
            core.last_connection_error = "connection refused by 127.0.0.1:8188"
            widget.update_state_display()
            await ui_test.human_delay()
            show_logs_button = ui_test.find(
                "comfy_setup_show_logs//Frame/**/Button[*].identifier=='ComfySetupShowLogs'"
            )

            # A user opens the exact current ComfyUI connection failure.
            with patch("lightspeed.trex.comfyui.widget.setup.widget.carb.log_warn") as log_warn_mock:
                await show_logs_button.click()
                await ui_test.human_delay()
                error_window = ui.Workspace.get_window("ComfyUI Connection Failed")
                details_field = ui_test.find(
                    "ComfyUI Connection Failed//Frame/**/StringField[*].identifier=='ComfySetupConnectionErrorText'"
                )
                close_button = ui_test.find("ComfyUI Connection Failed//Frame/**/Button[*].text=='Close'")
                self.assertTrue(error_window.visible)
                self.assertTrue(details_field.widget.multiline)
                self.assertTrue(details_field.widget.read_only)
                expected_details = "Endpoint: http://127.0.0.1:8188\n\nError: connection refused by 127.0.0.1:8188"
                self.assertEqual(
                    details_field.widget.model.as_string,
                    expected_details,
                )
                omni.kit.clipboard.copy("")
                await details_field.click()
                await ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
                await ui_test.emulate_keyboard_press(KeyboardInput.C, KEYBOARD_MODIFIER_FLAG_CONTROL)
                await ui_test.human_delay()
                self.assertEqual(omni.kit.clipboard.paste(), expected_details)
                self.assertEqual(details_field.widget.model.as_string, expected_details)
                await close_button.click()
                await ui_test.human_delay()
                self.assertFalse(error_window.visible)

                # An error event without retained technical details still shows its ComfyUI status guidance.
                core.last_connection_error = ""
                core.status_message = "The ComfyUI server did not respond."
                await show_logs_button.click()
                await ui_test.human_delay()
                error_window = ui.Workspace.get_window("ComfyUI Connection Failed")
                details_field = ui_test.find(
                    "ComfyUI Connection Failed//Frame/**/StringField[*].identifier=='ComfySetupConnectionErrorText'"
                )
                self.assertTrue(error_window.visible)
                self.assertEqual(
                    details_field.widget.model.as_string,
                    "Endpoint: http://127.0.0.1:8188\n\nError: The ComfyUI server did not respond.",
                )
                error_window.visible = False

                # A stale button cannot open another failure dialog.
                core.state = ComfyUIState.READY
                await show_logs_button.click()
                await ui_test.human_delay()
                self.assertFalse(error_window.visible)
                log_warn_mock.assert_called_once_with(
                    "ComfyUI logs action skipped because the connection error is no longer active."
                )
        finally:
            await self._destroy_widget(window, widget)

    async def test_standard_port_icon_is_aligned(self):
        """The rendered endpoint shortcut is aligned with the port field."""
        window, widget, core = await self._create_widget("comfy_setup_standard_port")
        try:
            # Measure the live endpoint shortcut against the rendered port field.
            port = ui_test.find("comfy_setup_standard_port//Frame/**/IntField[*].identifier=='ComfySetupPort'")
            standard_port = ui_test.find(
                "comfy_setup_standard_port//Frame/**/Image[*].identifier=='ComfySetupStandardPort'"
            )
            # The web icon occupies real space and shares the field's vertical center.
            self.assertIsNotNone(standard_port)
            self.assertEqual(standard_port.widget.name, "Web")
            self.assertGreater(standard_port.size.x, 0)
            self.assertGreater(standard_port.size.y, 0)
            self.assertGreater(standard_port.center.x, port.center.x)
            self.assertAlmostEqual(standard_port.center.y, port.center.y, delta=2)
        finally:
            await self._destroy_widget(window, widget)

    async def test_standard_port_icon_ignores_secondary_click(self):
        """A secondary click on the rendered endpoint shortcut does not change the port."""
        window, widget, core = await self._create_widget("comfy_setup_standard_port_secondary")
        try:
            port = ui_test.find(
                "comfy_setup_standard_port_secondary//Frame/**/IntField[*].identifier=='ComfySetupPort'"
            )
            standard_port = ui_test.find(
                "comfy_setup_standard_port_secondary//Frame/**/Image[*].identifier=='ComfySetupStandardPort'"
            )

            # Send a secondary click through the live icon.
            core.settings.set_port.reset_mock()
            await standard_port.right_click()
            await ui_test.human_delay()

            # Secondary input is inert and preserves the current endpoint.
            core.settings.set_port.assert_not_called()
            self.assertEqual(port.widget.model.as_int, 8188)
        finally:
            await self._destroy_widget(window, widget)

    async def test_standard_port_icon_uses_current_protocol(self):
        """A primary click applies the selected protocol's standard port."""
        window, widget, core = await self._create_widget("comfy_setup_standard_port_current_protocol")
        try:
            protocol = ui_test.find(
                "comfy_setup_standard_port_current_protocol//Frame/**/ComboBox[*].identifier=='ComfySetupProtocol'"
            )
            port = ui_test.find(
                "comfy_setup_standard_port_current_protocol//Frame/**/IntField[*].identifier=='ComfySetupPort'"
            )
            standard_port = ui_test.find(
                "comfy_setup_standard_port_current_protocol//Frame/**/Image[*].identifier=='ComfySetupStandardPort'"
            )
            protocol.widget.model.get_item_value_model().set_value(1)
            await ui_test.human_delay()
            core.settings.set_port.reset_mock()

            # Click the live shortcut after switching the protocol to HTTPS.
            await standard_port.click()
            await ui_test.human_delay()

            # The shortcut persists and renders the selected protocol's standard port.
            core.settings.set_port.assert_called_once_with(443)
            self.assertEqual(port.widget.model.as_int, 443)
        finally:
            await self._destroy_widget(window, widget)
