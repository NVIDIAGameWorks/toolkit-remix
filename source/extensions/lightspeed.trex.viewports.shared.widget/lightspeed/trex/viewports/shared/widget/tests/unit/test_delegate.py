"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from unittest.mock import MagicMock, patch

import carb.input
import omni.kit.test
from lightspeed.common.constants import GlobalEventNames
from lightspeed.trex.viewports.shared.widget.events.delegate import ViewportEventDelegate

_ZOOM_OP = "lightspeed.trex.viewports.shared.widget.events.delegate._zoom_operation"
_EVENT_MANAGER = "lightspeed.trex.viewports.shared.widget.events.delegate._get_event_manager_instance"


class TestViewportEventDelegate(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._scene_view = MagicMock()
        self._viewport_api = MagicMock()
        self._viewport_api.camera_path = "/OmniverseKit_Persp"
        self._viewport_api.usd_context_name = "test_context"
        self._delegate = ViewportEventDelegate(self._scene_view, self._viewport_api)

    async def tearDown(self):
        self._delegate.destroy()
        self._delegate = None

    async def test_zoom_unscaled_at_default_camera_speed(self):
        """Zoom delta is unscaled when camMoveVelocity equals the default (5.0)."""
        mock_settings = MagicMock()
        mock_settings.get.return_value = 5.0

        with (
            patch.object(self._delegate, "adjust_flight_speed", return_value=False),
            patch("carb.settings.get_settings", return_value=mock_settings),
            patch(_ZOOM_OP) as mock_zoom,
        ):
            self._delegate.mouse_wheel(0, 1.0, 0)

        mock_zoom.assert_called_once_with(0, 1.0, self._viewport_api)

    async def test_zoom_scaled_down_at_low_camera_speed(self):
        """Zoom delta is proportionally smaller when camMoveVelocity < default."""
        mock_settings = MagicMock()
        mock_settings.get.return_value = 1.0

        with (
            patch.object(self._delegate, "adjust_flight_speed", return_value=False),
            patch("carb.settings.get_settings", return_value=mock_settings),
            patch(_ZOOM_OP) as mock_zoom,
        ):
            self._delegate.mouse_wheel(0, 1.0, 0)

        mock_zoom.assert_called_once_with(0, 1.0 * (1.0 / 5.0), self._viewport_api)

    async def test_zoom_scaled_up_at_high_camera_speed(self):
        """Zoom delta is proportionally larger when camMoveVelocity > default."""
        mock_settings = MagicMock()
        mock_settings.get.return_value = 10.0

        with (
            patch.object(self._delegate, "adjust_flight_speed", return_value=False),
            patch("carb.settings.get_settings", return_value=mock_settings),
            patch(_ZOOM_OP) as mock_zoom,
        ):
            self._delegate.mouse_wheel(0, 2.0, 0)

        mock_zoom.assert_called_once_with(0, 2.0 * (10.0 / 5.0), self._viewport_api)

    async def test_zoom_fallback_when_setting_is_none(self):
        """Zoom delta is unscaled when camMoveVelocity setting returns None."""
        mock_settings = MagicMock()
        mock_settings.get.return_value = None

        with (
            patch.object(self._delegate, "adjust_flight_speed", return_value=False),
            patch("carb.settings.get_settings", return_value=mock_settings),
            patch(_ZOOM_OP) as mock_zoom,
        ):
            self._delegate.mouse_wheel(0, 3.0, 0)

        mock_zoom.assert_called_once_with(0, 3.0, self._viewport_api)

    async def test_zoom_not_called_during_flight_speed_adjustment(self):
        """_zoom_operation is not invoked when adjust_flight_speed consumes the event."""
        with (
            patch.object(self._delegate, "adjust_flight_speed", return_value=True),
            patch(_ZOOM_OP) as mock_zoom,
        ):
            self._delegate.mouse_wheel(0, 1.0, 0)

        mock_zoom.assert_not_called()

    async def test_zoom_not_called_when_regular_key_is_down_without_scene_key_callback(self):
        """_zoom_operation is not invoked when input state reports a held regular key."""
        # Arrange
        keyboard = object()
        app_window = MagicMock()
        app_window.get_keyboard.return_value = keyboard
        input_interface = MagicMock()
        input_interface.get_keyboard_value.side_effect = lambda requested_keyboard, key: (
            requested_keyboard is keyboard and key == carb.input.KeyboardInput.B
        )

        with (
            patch.object(self._delegate, "adjust_flight_speed", return_value=False),
            patch("omni.appwindow.get_default_app_window", return_value=app_window),
            patch("carb.input.acquire_input_interface", return_value=input_interface),
            patch(_ZOOM_OP) as mock_zoom,
        ):
            # Act
            self._delegate.mouse_wheel(0, 1.0, 0)

        # Assert
        mock_zoom.assert_not_called()

    async def test_zoom_horizontal_scroll_always_zero(self):
        """Horizontal scroll component is always passed as zero regardless of input."""
        mock_settings = MagicMock()
        mock_settings.get.return_value = 5.0

        with (
            patch.object(self._delegate, "adjust_flight_speed", return_value=False),
            patch("carb.settings.get_settings", return_value=mock_settings),
            patch(_ZOOM_OP) as mock_zoom,
        ):
            self._delegate.mouse_wheel(99.0, 1.0, 0)

        mock_zoom.assert_called_once_with(0, 1.0, self._viewport_api)

    async def test_zoom_negative_scroll_direction(self):
        """Negative scroll values are correctly scaled."""
        mock_settings = MagicMock()
        mock_settings.get.return_value = 2.5

        with (
            patch.object(self._delegate, "adjust_flight_speed", return_value=False),
            patch("carb.settings.get_settings", return_value=mock_settings),
            patch(_ZOOM_OP) as mock_zoom,
        ):
            self._delegate.mouse_wheel(0, -1.0, 0)

        mock_zoom.assert_called_once_with(0, -1.0 * (2.5 / 5.0), self._viewport_api)

    async def test_zoom_delegates_camera_boundary_to_zoom_operation(self):
        """Mouse-wheel zoom lets the zoom helper own game-camera redirect decisions."""
        mock_settings = MagicMock()
        mock_settings.get.return_value = 5.0

        with (
            patch.object(self._delegate, "adjust_flight_speed", return_value=False),
            patch("carb.settings.get_settings", return_value=mock_settings),
            patch(_ZOOM_OP) as mock_zoom,
        ):
            self._delegate.mouse_wheel(0, 1.0, 0)

        mock_zoom.assert_called_once_with(0, 1.0, self._viewport_api)

    async def test_delete_released_without_modifiers_emits_delete_request_for_viewport_context(self):
        # Arrange
        with patch(_EVENT_MANAGER) as mock_get_event_manager:
            # Act
            self._delegate.key_pressed(int(carb.input.KeyboardInput.DEL), 0, False)

        # Assert
        mock_get_event_manager.return_value.call_global_custom_event.assert_called_once_with(
            GlobalEventNames.VIEWPORT_DELETE_SELECTION_REQUEST.value,
            "test_context",
        )

    async def test_numpad_delete_released_without_modifiers_emits_delete_request_for_viewport_context(self):
        # Arrange
        with patch(_EVENT_MANAGER) as mock_get_event_manager:
            # Act
            self._delegate.key_pressed(int(carb.input.KeyboardInput.NUMPAD_DEL), 0, False)

        # Assert
        mock_get_event_manager.return_value.call_global_custom_event.assert_called_once_with(
            GlobalEventNames.VIEWPORT_DELETE_SELECTION_REQUEST.value,
            "test_context",
        )

    async def test_delete_pressed_does_not_emit_delete_request(self):
        # Arrange
        with patch(_EVENT_MANAGER) as mock_get_event_manager:
            # Act
            self._delegate.key_pressed(int(carb.input.KeyboardInput.DEL), 0, True)

        # Assert
        mock_get_event_manager.return_value.call_global_custom_event.assert_not_called()

    async def test_delete_released_with_modifiers_does_not_emit_delete_request(self):
        # Arrange
        with patch(_EVENT_MANAGER) as mock_get_event_manager:
            # Act
            self._delegate.key_pressed(int(carb.input.KeyboardInput.DEL), 1, False)

        # Assert
        mock_get_event_manager.return_value.call_global_custom_event.assert_not_called()

    async def test_unrelated_key_released_does_not_emit_delete_request(self):
        # Arrange
        with patch(_EVENT_MANAGER) as mock_get_event_manager:
            # Act
            self._delegate.key_pressed(int(carb.input.KeyboardInput.B), 0, False)

        # Assert
        mock_get_event_manager.return_value.call_global_custom_event.assert_not_called()
