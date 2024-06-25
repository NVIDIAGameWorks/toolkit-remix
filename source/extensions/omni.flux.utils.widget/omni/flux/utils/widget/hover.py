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

import enum

import carb
import omni.appwindow
import omni.kit.window.cursor as _window_cursor
import omni.ui as ui
from carb.windowing import CursorStandardShape


class CursorShapesEnum(enum.Enum):
    """
    Enumeration of the cursor shapes.

    Provides a simpler way for developers to define their desired cursor shape, since carb.windowing.CursorStandardShape
    is not a standard Python Enum - it's a binding.
    """

    ARROW = CursorStandardShape.ARROW
    CROSSHAIR = CursorStandardShape.CROSSHAIR
    HAND = CursorStandardShape.HAND
    HORIZONTAL_RESIZE = CursorStandardShape.HORIZONTAL_RESIZE
    IBEAM = CursorStandardShape.IBEAM
    VERTICAL_RESIZE = CursorStandardShape.VERTICAL_RESIZE


_DEFAULT_CURSOR_SHAPE: CursorStandardShape = CursorShapesEnum.HAND.value


def _verify_cursor_shape(cursor_shape: CursorStandardShape | CursorShapesEnum | None) -> CursorStandardShape:
    if cursor_shape is None:
        return _DEFAULT_CURSOR_SHAPE
    if isinstance(cursor_shape, CursorStandardShape):
        return cursor_shape
    if isinstance(cursor_shape, CursorShapesEnum):
        return cursor_shape.value
    # Those are the only valid options, so raise an exception
    valid_shapes = ", ".join([str(shape.value) for shape in list(CursorShapesEnum)])
    raise ValueError(f"'cursor_shape' must be one of: {valid_shapes} - got '{cursor_shape}'")


class _HoverHelper:
    """A class to handle hover events. Only used internally."""

    def __init__(self, widget: ui.Widget, cursor_shape: CursorShapesEnum | CursorStandardShape | None = None) -> None:
        self._widget = widget
        self._in_hover = False
        self._main_window_cursor = _window_cursor.get_main_window_cursor()
        shape = _verify_cursor_shape(cursor_shape)
        self._cursor_shape_override = shape
        self._iface = carb.input.acquire_input_interface()
        app_window = omni.appwindow.get_default_app_window()
        self._mouse = app_window.get_mouse()

        widget.set_mouse_hovered_fn(self.__on_widget_hovered)
        widget.set_mouse_released_fn(self.__on_widget_mouse_released)

    def __on_widget_hovered(self, hovered: bool) -> None:
        """
        Called when the widget is hovered.

        If the mouse is being dragged, the mouse event started elsewhere, so no changes are needed.

        Args:
            hovered: True when starting to hover; False when leaving hover

        Returns:
            None
        """
        self._in_hover = hovered
        dragging = self._iface.get_mouse_value(self._mouse, carb.input.MouseInput.LEFT_BUTTON)
        if dragging:
            return
        if hovered:
            self._main_window_cursor.override_cursor_shape(self._cursor_shape_override)
        else:
            self._main_window_cursor.clear_overridden_cursor_shape()

    def __on_widget_mouse_released(self, *args) -> None:
        """
        Called when the mouse button is released.

        If the user starts a drag event on the widget, and releases it outside the widget, the cursor will remain
        overridden. This method ensures that the cursor is reset.

        If the user releases the mouse while still hovering, nothing should happen.
        """
        if not self._in_hover:
            self._main_window_cursor.clear_overridden_cursor_shape()


def hover_helper(widget: ui.Widget, cursor_shape: CursorStandardShape | None = None) -> None:
    """
    Adds hover actions for the specified widget.

    The cursor will change to the cursor shape passed to the __init__() function, with a default of HAND. The shape must
    be one of the shapes defined in carb.windowing.CursorStandardShape; these are:

    * ARROW
    * CROSSHAIR
    * HAND
    * HORIZONTAL_RESIZE
    * IBEAM
    * VERTICAL_RESIZE"""
    _HoverHelper(widget, cursor_shape)
