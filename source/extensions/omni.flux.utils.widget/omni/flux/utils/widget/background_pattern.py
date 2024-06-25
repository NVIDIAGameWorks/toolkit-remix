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

import functools
from typing import Callable, Tuple, Union

import omni.ui as ui


def create_widget_with_pattern(
    widget: Union[Callable, functools.partial],
    background_name: str,
    v_pattern_loop: int = 3,
    h_pattern_loop: int = 3,
    image_size: int = 256,
    height: ui.Length = None,
    width: ui.Length = None,
    background_margin: Tuple[int, int] = None,
    pattern_image_name: str = "TreePanelLinesBackground",
    pattern_background_rectangle_name: str = "WorkspaceBackground",
    widget_margin: Tuple[int, int] = None,
):
    """
    Create a widget with a pattern as a background

    Args:
        widget: the function that will create the widget, like `ui.Widget`
        background_name: the name of the rectangle used as a background of the widget
        v_pattern_loop: the number of time the pattern will loop vertically
        h_pattern_loop: the number of time the pattern will loop horizontally
        image_size: the size of the pattern image
        height: the height of the whole ui widget
        width: the width of the whole ui widget
        background_margin: margin of the whole ui widget
        pattern_image_name: image name to use for the pattern
        pattern_background_rectangle_name: image name to use for the background rectangle of the pattern
        widget_margin: margin of the given widget to create

    Returns:
        ui.Widget: the created widget given by the "widget" arg
    """
    size_arg = {}
    if height is not None:
        size_arg["height"] = height
    if width is not None:
        size_arg["width"] = width
    if background_margin is None:
        background_margin = (0, 0)
    with ui.ZStack(**size_arg):
        with ui.VStack():
            ui.Spacer(width=0, height=background_margin[1])
            with ui.HStack():
                ui.Spacer(height=0, width=background_margin[0])
                with ui.ZStack():
                    ui.Rectangle(name=pattern_background_rectangle_name)
                    with ui.ScrollingFrame(
                        style={"background_color": 0x0},
                        vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        scroll_y_max=0,
                    ):
                        with ui.VStack():
                            for _ in range(v_pattern_loop):
                                with ui.HStack():
                                    for _ in range(h_pattern_loop):
                                        ui.Image(
                                            "",
                                            name=pattern_image_name,
                                            fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                            height=ui.Pixel(image_size),
                                            width=ui.Pixel(image_size),
                                        )
                ui.Spacer(height=0, width=background_margin[0])
            ui.Spacer(width=0, height=background_margin[1])
        if widget_margin is None:
            widget_margin = (0, 0)
        with ui.Frame(separate_window=True):
            with ui.ZStack(content_clipping=True):
                with ui.VStack():
                    ui.Spacer(width=0, height=background_margin[1])
                    with ui.HStack():
                        ui.Spacer(height=0, width=background_margin[0])
                        ui.Rectangle(name=background_name)
                        ui.Spacer(height=0, width=background_margin[0])
                    ui.Spacer(width=0, height=background_margin[1])
                with ui.VStack():
                    ui.Spacer(width=0, height=widget_margin[1])
                    with ui.HStack():
                        ui.Spacer(height=0, width=widget_margin[0])
                        wid = widget()
                        ui.Spacer(height=0, width=widget_margin[0])
                    ui.Spacer(width=0, height=widget_margin[1])
                return wid
