"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb.settings
import omni.kit.usd.layers as _layers

from .singleton import Singleton as _Singleton

SETTINGS_SHOW_PRIM_DISPLAYNAME = "/persistent/ext/omni.kit.widget.stage/show_prim_displayname"
SETTINGS_KEEP_CHILDREN_ORDER = "/persistent/ext/omni.usd/keep_children_order"


@_Singleton
class StageSettings:
    def __init__(self):
        super().__init__()
        self._settings = carb.settings.get_settings()
        self._settings.set_default_bool(SETTINGS_SHOW_PRIM_DISPLAYNAME, False)
        self._settings.set_default_bool(_layers.SETTINGS_AUTO_RELOAD_NON_SUBLAYERS, False)
        self._settings.set_default_bool(SETTINGS_KEEP_CHILDREN_ORDER, False)

    @property
    def show_prim_displayname(self):
        return self._settings.get_as_bool(SETTINGS_SHOW_PRIM_DISPLAYNAME)

    @show_prim_displayname.setter
    def show_prim_displayname(self, enabled: bool):
        self._settings.set(SETTINGS_SHOW_PRIM_DISPLAYNAME, enabled)

    @property
    def auto_reload_prims(self):
        return self._settings.get_as_bool(_layers.SETTINGS_AUTO_RELOAD_NON_SUBLAYERS)

    @auto_reload_prims.setter
    def auto_reload_prims(self, enabled: bool):
        self._settings.set(_layers.SETTINGS_AUTO_RELOAD_NON_SUBLAYERS, enabled)

    @property
    def should_keep_children_order(self):
        return self._settings.get_as_bool(SETTINGS_KEEP_CHILDREN_ORDER)

    @should_keep_children_order.setter
    def should_keep_children_order(self, value):
        self._settings.set(SETTINGS_KEEP_CHILDREN_ORDER, value)
