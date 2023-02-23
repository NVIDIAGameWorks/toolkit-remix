"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
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
