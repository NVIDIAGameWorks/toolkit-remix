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

from enum import Enum
from typing import Any

import omni.ui as ui
import omni.usd
from pxr import UsdLux

from .base.base_selector import SelectorUSDBase as _SelectorUSDBase


class LightType(Enum):
    DomeLight = "DomeLight"
    DiskLight = "DiskLight"
    RectLight = "RectLight"
    SphereLight = "SphereLight"
    CylinderLight = "CylinderLight"
    DistantLight = "DistantLight"
    UnknownLight = "UnknownLight"


class AllLights(_SelectorUSDBase):
    class Data(_SelectorUSDBase.Data):
        light_types: set[LightType] | None = None

    name = "AllLights"
    tooltip = "This plugin will select all lights in the stage"
    data_type = Data

    @omni.usd.handle_exception
    async def _select(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to select the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the previous selector plugin

        Returns: True if ok + message + the selected data
        """

        light_types = (
            [self.__get_light_type(light_type) for light_type in schema_data.light_types]
            if schema_data.light_types
            else None
        )

        all_lights = []
        for prim in self._get_prims(schema_data, context_plugin_data):
            # Make sure the prim is a light
            if not (prim.HasAPI(UsdLux.LightAPI) if hasattr(UsdLux, "LightAPI") else prim.IsA(UsdLux.Light)):
                continue
            # Only attempt filtering if we set the light_types in the schema data
            if light_types:
                valid_light_type = False
                for light_type in light_types:
                    if not light_type:
                        continue
                    if prim.IsA(light_type):
                        valid_light_type = True
                        break
                if not valid_light_type:
                    continue
            all_lights.append(prim)

        return True, "Ok", all_lights

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")

    def __get_light_type(
        self, light_type: LightType
    ) -> UsdLux.BoundableLightBase | UsdLux.NonboundableLightBase | None:
        match light_type:
            case LightType.DomeLight:
                return UsdLux.DomeLight
            case LightType.DiskLight:
                return UsdLux.DiskLight
            case LightType.RectLight:
                return UsdLux.RectLight
            case LightType.SphereLight:
                return UsdLux.SphereLight
            case LightType.CylinderLight:
                return UsdLux.CylinderLight
            case LightType.DistantLight:
                return UsdLux.DistantLight
            case _:
                return None
        return None
