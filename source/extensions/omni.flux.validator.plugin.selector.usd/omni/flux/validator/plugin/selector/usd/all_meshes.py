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

from typing import Any, Tuple

import omni.ui as ui
import omni.usd
from pxr import UsdGeom

from .base.base_selector import SelectorUSDBase as _SelectorUSDBase


class AllMeshes(_SelectorUSDBase):
    class Data(_SelectorUSDBase.Data):
        include_geom_subset: bool = False

    name = "AllMeshes"
    tooltip = "This plugin will select all meshes in the stage"
    data_type = Data

    @omni.usd.handle_exception
    async def _select(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to select the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the previous selector plugin

        Returns: True if ok + message + the selected data
        """

        stage = omni.usd.get_context(context_plugin_data).get_stage()
        if schema_data.include_geom_subset:
            all_geos = [
                prim_ref
                for prim_ref in stage.TraverseAll()
                if prim_ref.IsA(UsdGeom.Mesh) or prim_ref.IsA(UsdGeom.Subset)
            ]
        else:
            all_geos = [prim_ref for prim_ref in stage.TraverseAll() if prim_ref.IsA(UsdGeom.Mesh)]
        return True, "Ok", all_geos

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
