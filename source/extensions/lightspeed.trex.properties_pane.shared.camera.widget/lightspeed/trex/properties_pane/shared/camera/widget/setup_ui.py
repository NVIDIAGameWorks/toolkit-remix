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

import omni.ui as ui
from lightspeed.trex.camera_properties.shared.widget import SetupUI as _CameraPropertiesWidget
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.collapsable_frame import (
    PropertyCollapsableFrameWithInfoPopup as _PropertyCollapsableFrameWithInfoPopup,
)


class CameraPane:
    def __init__(self, context_name: str):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {
            "_root_frame": None,
            "_properties_widget": None,
            "_properties_collapsable_frame": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self.__create_ui()

    def __create_ui(self):
        self._root_frame = ui.Frame()
        with self._root_frame:
            with ui.ScrollingFrame(
                name="PropertiesPaneSection",
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            ):
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(56))

                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8), height=ui.Pixel(0))
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            self._properties_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "CAMERA PROPERTIES",
                                info_text="Camera properties.\n\n- Will show different camera properties.\n",
                                collapsed=False,
                            )
                            with self._properties_collapsable_frame:
                                self._properties_widget = _CameraPropertiesWidget(self._context_name)
                            self._properties_collapsable_frame.root.set_collapsed_changed_fn(
                                functools.partial(self.__on_collapsable_frame_changed, self._properties_widget)
                            )

                            ui.Spacer(height=ui.Pixel(16))

    def __on_collapsable_frame_changed(self, widget, collapsed):
        widget.show(not collapsed)

    def refresh(self, path: str):
        self._properties_widget.refresh(path)

    def show(self, value: bool):
        # Update the widget visibility
        self._root_frame.visible = value
        self._properties_widget.show(value)

    def destroy(self):
        _reset_default_attrs(self)
