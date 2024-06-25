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

from typing import Callable

from omni import ui


def show_popup(
    title: str,
    positive_text: str,
    negative_text: str,
    build_fn: Callable[[], None],
    positive_callback: Callable[[], bool] = lambda: True,
    negative_callback: Callable[[], bool] = lambda: True,
    width: int = 300,
    height: int = 200,
    flags: tuple = None,
):
    def on_positive_clicked():
        if positive_callback():
            popup_window.visible = False

    def on_negative_clicked():
        if negative_callback():
            popup_window.visible = False

    popup_window = ui.Window(
        title,
        width=width,
        height=height,
        flags=flags
        or (
            ui.WINDOW_FLAGS_MODAL
            | ui.WINDOW_FLAGS_NO_DOCKING
            | ui.WINDOW_FLAGS_NO_COLLAPSE
            | ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_CLOSE
            | ui.WINDOW_FLAGS_NO_MOVE
            | ui.WINDOW_FLAGS_NO_RESIZE
            | ui.WINDOW_FLAGS_NO_SCROLLBAR
        ),
    )

    with popup_window.frame:
        with ui.HStack():
            ui.Spacer(height=0, width=ui.Pixel(16))
            with ui.VStack():
                ui.Spacer(width=0)
                with ui.VStack(height=0):
                    build_fn()
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.HStack():
                        ui.Spacer(height=0)
                        ui.Button(
                            positive_text, clicked_fn=on_positive_clicked, height=ui.Pixel(24), width=ui.Pixel(96)
                        )
                        ui.Button(
                            negative_text, clicked_fn=on_negative_clicked, height=ui.Pixel(24), width=ui.Pixel(96)
                        )
                        ui.Spacer(height=0)
                ui.Spacer(width=0)
            ui.Spacer(height=0, width=ui.Pixel(16))
