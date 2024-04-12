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
