"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.ui as ui
from lightspeed.trex.components_pane.stagecraft.models import EnumItems as ComponentsEnumItems
from lightspeed.trex.properties_pane.shared.asset_replacements.widget import (
    AssetReplacementsPane as _AssetReplacementsPane,
)
from lightspeed.trex.properties_pane.shared.mod_packaging.widget import ModPackagingPane as _ModPackagingPane
from lightspeed.trex.properties_pane.shared.mod_setup.widget import ModSetupPane as _ModSetupPan
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class SetupUI:
    def __init__(self, context_name):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {"_all_frames": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._all_frames = {}
        self._context_name = context_name
        self.__create_ui()

    def get_frame(self, component_type_value: ComponentsEnumItems):  # noqa PLR1710
        for component_type, frame in self._all_frames.items():  # noqa: R503
            if component_type == component_type_value:
                return frame
        return None

    def __create_ui(self):
        with ui.ZStack():
            ui.Rectangle(name="WorkspaceBackground")
            self._all_frames[ComponentsEnumItems.MOD_SETUP] = _ModSetupPan(self._context_name)
            self._all_frames[ComponentsEnumItems.ASSET_REPLACEMENTS] = _AssetReplacementsPane(self._context_name)
            self._all_frames[ComponentsEnumItems.MOD_PACKAGING] = _ModPackagingPane(self._context_name)

    def show_panel(self, title: str = None, forced_value: bool = None):
        for enum_item in ComponentsEnumItems:
            if enum_item in self._all_frames:
                if title and forced_value is None:
                    self._all_frames[enum_item].show(enum_item.value == title)
                elif forced_value is not None:
                    self._all_frames[enum_item].show(forced_value)

    def destroy(self):
        for frame in self._all_frames.values():
            frame.destroy()
        _reset_default_attrs(self)
