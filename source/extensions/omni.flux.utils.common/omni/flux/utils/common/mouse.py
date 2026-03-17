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

from __future__ import annotations


import carb.input
import omni.appwindow
import omni.ui as ui


def get_mouse_position() -> tuple[int, int] | None:
    """
    Return the current mouse position in window-relative logical pixels (DPI-scaled).

    Coordinates match the space used by omni.ui widget properties
    (screen_position_x/y, computed_width/height), so the result can be
    passed directly to is_point_inside_widget for hit-testing.

    Returns None if the position cannot be determined (e.g. no app window
    or input interface).

    Returns:
        (x, y) in window-relative logical pixels, or None on failure.
    """
    try:
        app_window = omni.appwindow.get_default_app_window()
        iface = carb.input.acquire_input_interface()
        dpi_scale = ui.Workspace.get_dpi_scale()
        mx_px, my_px = iface.get_mouse_coords_pixel(app_window.get_mouse())
        screen_x = int(mx_px / dpi_scale)
        screen_y = int(my_px / dpi_scale)
        return (screen_x, screen_y)
    except (AttributeError, TypeError, RuntimeError, OSError, ZeroDivisionError, ValueError):
        return None


def is_point_inside_widget(widget: ui.Widget, point: tuple[int, int]) -> bool:
    """
    Return True if the given point lies inside the widget's bounding box.

    Used to determine if a click or drop occurred inside a widget. Point must be
    in the same coordinate space as the widget (window-relative logical pixels);
    use get_mouse_position() for the current mouse position.

    Args:
        widget: An omni.ui widget with screen_position_x/y and computed_width/height.
        point: (x, y) in window-relative logical pixels.

    Returns:
        True if point is inside the widget rect, False otherwise (or if widget
        is None or has no bounds).
    """
    try:
        left = widget.screen_position_x
        top = widget.screen_position_y
        w = widget.computed_width
        h = widget.computed_height
    except (AttributeError, TypeError):
        return False
    x, y = point
    if not (left <= x < left + w):
        return False
    return top <= y < top + h
