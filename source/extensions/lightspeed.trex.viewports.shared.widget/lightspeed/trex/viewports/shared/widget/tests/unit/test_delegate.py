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

import omni.kit.test
from lightspeed.trex.viewports.shared.widget.events.delegate import ViewportEventDelegate

_ZOOM_OP = "lightspeed.trex.viewports.shared.widget.events.delegate._zoom_operation"


class TestViewportEventDelegateMouseWheel(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._scene_view = MagicMock()
        self._viewport_api = MagicMock()
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
