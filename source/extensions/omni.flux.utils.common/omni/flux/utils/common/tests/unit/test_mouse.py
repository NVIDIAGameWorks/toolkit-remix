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

from unittest.mock import MagicMock, patch

import omni.kit.test

from omni.flux.utils.common.mouse import get_mouse_position, is_point_inside_widget


def _make_widget(x=0, y=0, w=100, h=50):
    widget = MagicMock()
    widget.screen_position_x = x
    widget.screen_position_y = y
    widget.computed_width = w
    widget.computed_height = h
    return widget


class TestGetMousePosition(omni.kit.test.AsyncTestCase):
    async def test_pixel_coords_divided_by_dpi_scale_returns_logical_position(self):
        # Arrange
        with (
            patch("omni.appwindow.get_default_app_window") as mock_get_window,
            patch("carb.input.acquire_input_interface") as mock_acquire_input,
            patch("omni.ui.Workspace.get_dpi_scale", return_value=2.0),
        ):
            mock_window = MagicMock()
            mock_window.get_mouse.return_value = MagicMock()
            mock_get_window.return_value = mock_window
            mock_iface = MagicMock()
            mock_iface.get_mouse_coords_pixel.return_value = (50, 60)
            mock_acquire_input.return_value = mock_iface

            # Act
            result = get_mouse_position()

            # Assert
            self.assertEqual(result, (25, 30))

    async def test_returns_none_when_app_window_is_unavailable(self):
        # Arrange
        with patch("omni.appwindow.get_default_app_window", side_effect=RuntimeError("no window")):
            # Act
            result = get_mouse_position()

            # Assert
            self.assertIsNone(result)


class TestIsPointInsideWidget(omni.kit.test.AsyncTestCase):
    # -- None / missing bounds --

    async def test_returns_false_when_widget_is_none(self):
        # Act
        result = is_point_inside_widget(None, (10, 10))

        # Assert
        self.assertFalse(result)

    async def test_returns_false_when_widget_has_no_screen_position(self):
        # Arrange
        widget = MagicMock()
        del widget.screen_position_x

        # Act
        result = is_point_inside_widget(widget, (50, 50))

        # Assert
        self.assertFalse(result)

    # -- Inside --

    async def test_point_at_widget_center_is_inside(self):
        # Arrange
        widget = _make_widget(x=0, y=0, w=100, h=50)

        # Act
        result = is_point_inside_widget(widget, (50, 25))

        # Assert
        self.assertTrue(result)

    async def test_point_at_top_left_corner_is_inside(self):
        # Arrange
        widget = _make_widget(x=0, y=0, w=100, h=50)

        # Act
        result = is_point_inside_widget(widget, (0, 0))

        # Assert
        self.assertTrue(result)

    async def test_point_at_last_inclusive_pixel_is_inside(self):
        # Arrange
        widget = _make_widget(x=0, y=0, w=100, h=50)

        # Act
        result = is_point_inside_widget(widget, (99, 49))

        # Assert
        self.assertTrue(result)

    # -- Outside (each edge) --

    async def test_point_one_pixel_left_of_widget_is_outside(self):
        # Arrange
        widget = _make_widget(x=10, y=10, w=100, h=50)

        # Act
        result = is_point_inside_widget(widget, (9, 35))

        # Assert
        self.assertFalse(result)

    async def test_point_at_right_edge_of_widget_is_outside(self):
        # Arrange
        widget = _make_widget(x=10, y=10, w=100, h=50)

        # Act
        result = is_point_inside_widget(widget, (110, 35))

        # Assert
        self.assertFalse(result)

    async def test_point_one_pixel_above_widget_is_outside(self):
        # Arrange
        widget = _make_widget(x=10, y=10, w=100, h=50)

        # Act
        result = is_point_inside_widget(widget, (50, 9))

        # Assert
        self.assertFalse(result)

    async def test_point_at_bottom_edge_of_widget_is_outside(self):
        # Arrange
        widget = _make_widget(x=10, y=10, w=100, h=50)

        # Act
        result = is_point_inside_widget(widget, (50, 60))

        # Assert
        self.assertFalse(result)

    # -- Boundary exclusivity (right/bottom edges are exclusive) --

    async def test_right_boundary_at_full_width_is_exclusive(self):
        # Arrange
        widget = _make_widget(x=0, y=0, w=1920, h=1080)

        # Act
        result = is_point_inside_widget(widget, (1920, 540))

        # Assert
        self.assertFalse(result)

    async def test_bottom_boundary_at_full_height_is_exclusive(self):
        # Arrange
        widget = _make_widget(x=0, y=0, w=1920, h=1080)

        # Act
        result = is_point_inside_widget(widget, (960, 1080))

        # Assert
        self.assertFalse(result)

    # -- Offset widgets at various screen positions --

    async def test_point_inside_center_screen_offset_widget(self):
        # Arrange
        widget = _make_widget(x=800, y=400, w=200, h=150)

        # Act
        result = is_point_inside_widget(widget, (900, 475))

        # Assert
        self.assertTrue(result)

    async def test_point_just_left_of_center_screen_offset_widget(self):
        # Arrange
        widget = _make_widget(x=800, y=400, w=200, h=150)

        # Act
        result = is_point_inside_widget(widget, (799, 475))

        # Assert
        self.assertFalse(result)

    async def test_point_inside_bottom_right_offset_widget(self):
        # Arrange
        widget = _make_widget(x=1500, y=900, w=100, h=80)

        # Act
        result = is_point_inside_widget(widget, (1550, 940))

        # Assert
        self.assertTrue(result)

    async def test_point_just_left_of_bottom_right_offset_widget(self):
        # Arrange
        widget = _make_widget(x=1500, y=900, w=100, h=80)

        # Act
        result = is_point_inside_widget(widget, (1499, 940))

        # Assert
        self.assertFalse(result)

    async def test_point_inside_small_offset_widget(self):
        # Arrange
        widget = _make_widget(x=100, y=200, w=50, h=30)

        # Act
        result = is_point_inside_widget(widget, (125, 215))

        # Assert
        self.assertTrue(result)

    async def test_point_at_right_edge_of_small_offset_widget_is_outside(self):
        # Arrange
        widget = _make_widget(x=100, y=200, w=50, h=30)

        # Act
        result = is_point_inside_widget(widget, (150, 215))

        # Assert
        self.assertFalse(result)
