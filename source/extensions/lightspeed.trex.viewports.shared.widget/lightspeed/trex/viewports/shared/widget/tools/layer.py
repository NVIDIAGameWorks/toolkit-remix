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
__all__ = ["ViewportToolsLayer"]

from omni import ui
from omni.kit.widget.toolbar import Toolbar as _Toolbar
from omni.kit.widget.toolbar import get_instance as _get_widget_instance

from ..interface.i_layer_item import LayerItem as _LayerItem


class ViewportToolsLayer(_LayerItem):
    def __init__(self, desc: dict):

        self.__viewport_api = desc.get("viewport_api")
        self.__root: ui.Frame = ui.Frame(
            horizontal_clipping=True, vertical_clipping=True, content_clipping=True, opaque_for_mouse_events=True
        )
        self.__root.visible = True  # TODO: register display tool in the menubar as setting
        self.__widget_instance = None
        self.__build(self.__viewport_api)

    def __build(self, viewport_api):
        if self.__root:
            self.__root.clear()
        default_size = 30
        _Toolbar.DEFAULT_SIZE = default_size
        with self.__root:
            with ui.VStack(content_clipping=True, width=0):
                ui.Spacer(name="Spacer")
                with ui.ZStack(height=0):
                    ui.Rectangle(style_type_name_override="Viewport.Item.Background")
                    with ui.VStack():
                        ui.Spacer(name="Spacer", height=ui.Pixel(8))
                        with ui.HStack():
                            ui.Spacer(name="Spacer", width=ui.Pixel(4))
                            with ui.VStack():
                                frame = ui.Frame()
                                self.__widget_instance = _get_widget_instance()
                                self.__widget_instance.set_axis(ui.ToolBarAxis.Y)
                                self.__widget_instance.rebuild_toolbar(frame)
                            ui.Spacer(name="Spacer", width=ui.Pixel(4))
                        ui.Spacer(name="Spacer", height=ui.Pixel(8))
                ui.Spacer(name="Spacer")

    def destroy(self):
        if self.__root:
            self.__root.clear()
            self.__root = None

    @property
    def layers(self):
        return ()

    @property
    def visible(self):
        return self.__root.visible

    @visible.setter
    def visible(self, value):
        self.__root.visible = value

    @property
    def categories(self):
        return ("tools",)

    @property
    def name(self):
        return "All Tools"
