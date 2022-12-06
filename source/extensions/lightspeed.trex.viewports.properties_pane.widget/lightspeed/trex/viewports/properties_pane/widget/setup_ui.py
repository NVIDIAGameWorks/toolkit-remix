"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from enum import Enum

import omni.ui as ui
from lightspeed.trex.properties_pane.shared.camera.widget import CameraPane as _CameraPane
from lightspeed.trex.properties_pane.shared.render.widget import RenderPane as _RenderPane
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class EnumItems(Enum):
    CAMERA = "camera"
    RENDER = "render"


class SetupUI:
    def __init__(self, context_name: str):
        """Nvidia Viewport property panel"""

        self._default_attr = {"_all_frames": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._all_frames = {}
        self.__create_ui()

    def get_frame(self, component_type_value: EnumItems):  # noqa PLR1710
        for component_type, frame in self._all_frames.items():  # noqa: R503
            if component_type == component_type_value:
                return frame

    def __create_ui(self):
        with ui.ZStack():
            ui.Rectangle(name="WorkspaceBackground")
            self._all_frames[EnumItems.CAMERA] = _CameraPane(self._context_name)
            self._all_frames[EnumItems.RENDER] = _RenderPane(self._context_name)

    def show_panel(self, title: str = None, forced_value: bool = None):
        for enum_item in EnumItems:
            if enum_item in self._all_frames:
                if title and forced_value is None:
                    self._all_frames[enum_item].show(enum_item.value == title)
                elif forced_value is not None:
                    self._all_frames[enum_item].show(forced_value)

    def destroy(self):
        _reset_default_attrs(self)
