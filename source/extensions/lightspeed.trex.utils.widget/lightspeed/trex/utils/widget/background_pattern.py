"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import functools
from typing import Tuple

import omni.ui as ui


def create_widget_with_pattern(
    widget: functools.partial,
    background_name: str,
    v_pattern_loop: int = 3,
    h_pattern_loop: int = 3,
    image_size: int = 256,
    height: ui.Length = None,
    width: ui.Length = None,
    background_margin: Tuple[int, int] = None,
):
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
                    ui.Rectangle(name="WorkspaceBackground")
                    with ui.ScrollingFrame(
                        name="TreePanelBackground",
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
                                            name="TreePanelLinesBackground",
                                            fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                            height=ui.Pixel(image_size),
                                            width=ui.Pixel(image_size),
                                        )
                ui.Spacer(height=0, width=background_margin[0])
            ui.Spacer(width=0, height=background_margin[1])
        with ui.Frame(separate_window=True):
            with ui.ZStack(content_clipping=True):
                with ui.VStack():
                    ui.Spacer(width=0, height=background_margin[1])
                    with ui.HStack():
                        ui.Spacer(height=0, width=background_margin[0])
                        ui.Rectangle(name=background_name)
                        ui.Spacer(height=0, width=background_margin[0])
                    ui.Spacer(width=0, height=background_margin[1])
                return widget()
