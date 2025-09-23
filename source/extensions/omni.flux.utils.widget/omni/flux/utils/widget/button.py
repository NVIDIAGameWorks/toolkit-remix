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

from collections.abc import Callable

import omni.ui as ui

from .label import create_label_with_font as _create_label_with_font


def create_button_from_widget(widget: ui.Widget, on_clicked: Callable[[float, float, int, int], None]):
    """
    Sets the mouse pressed/hovered/release button events to the given widget to give it button behavior.


    Args:
        widget: Widget that will have events added to it.
        on_clicked: (optional) method that is fired with same arguments as ui.Widget.set_mouse_pressed_fn callback
    """
    can_click = [False]

    def on_hover(is_hovered):
        # latch on hover state to ensure that clicks are only processed if the mouse button is
        # released while still over the button. Storing as an array here so it can be accessed
        # in the helper functions.
        can_click[0] = is_hovered

    def on_pressed(x, y, button, m):
        if button != 0:
            return
        widget.selected = True

    def on_released(x, y, button, m):
        if button != 0:
            return
        widget.selected = False
        if can_click[0]:
            on_clicked(x, y, button, m)

    widget.set_mouse_hovered_fn(on_hover)
    widget.set_mouse_pressed_fn(on_pressed)
    widget.set_mouse_released_fn(on_released)
    widget.opaque_for_mouse_events = True


def create_button_with_custom_font(
    text: str,
    text_style_name: str,
    rectangle_style_name: str,
    height: ui.Length,
    height_padding: ui.Length,
    pressed_fn: Callable | None = None,
) -> tuple[ui.ByteImageProvider, ui.Rectangle]:
    """
    Create a button with a text that has a custom font

    Args:
        text: the text to show
        text_style_name: the style name of the text label
        rectangle_style_name: the style name of the background rectangle
        height: the height of the button
        height_padding: padding between the top of the button, the text, and the bottom
        pressed_fn: function that will be called when the button if pressed

    Returns:
        The image ui widget that contains the text and the background rectangle ui widget
    """

    with ui.ZStack():
        rectangle = ui.Rectangle(name=rectangle_style_name)
        create_button_from_widget(rectangle, lambda x, y, b, m: pressed_fn())

        with ui.VStack():
            ui.Spacer(width=ui.Pixel(0), height=height_padding)
            with ui.HStack():
                ui.Spacer(height=ui.Pixel(0))

                images_provider, _, _ = _create_label_with_font(
                    text, text_style_name, remove_offset=True, custom_image_height=height
                )
                ui.Spacer(height=ui.Pixel(0))
            ui.Spacer(width=ui.Percent(0), height=height_padding)
    return images_provider, rectangle


def create_button_with_label_style(
    text: str,
    text_style_name: str,
    rectangle_style_name: str,
    on_clicked: Callable[[float, float, int, int], None] | None = None,
) -> tuple[ui.Label, ui.Rectangle]:
    """
    Create a button with a text that have a custom style

    Args:
        text: the text to show
        text_style_name: the style name of the text label
        rectangle_style_name: the style name of the background rectangle
        on_clicked: (optional) method that is fired with same arguments as ui.Widget.set_mouse_pressed_fn callback

    Returns:
        The label ui widget and the background rectangle ui widget
    """

    with ui.ZStack():
        rectangle = ui.Rectangle(name=rectangle_style_name)
        label = ui.Label(text, name=text_style_name, alignment=ui.Alignment.CENTER)
        create_button_from_widget(rectangle, on_clicked)
        create_button_from_widget(label, on_clicked)

    return label, rectangle
