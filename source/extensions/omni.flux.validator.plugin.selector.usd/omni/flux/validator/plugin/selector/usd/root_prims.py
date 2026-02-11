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

from typing import Any

import omni.ui as ui
import omni.usd
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar

from .base.base_selector import SelectorUSDBase as _SelectorUSDBase


class RootPrims(_SelectorUSDBase):
    class Data(_SelectorUSDBase.Data):
        select_session_layer_prims: bool = False

    name = "RootPrims"
    tooltip = "This plugin will select all root prims in the stage"
    data_type = Data

    @omni.usd.handle_exception
    async def _select(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to select the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the previous selector plugin

        Returns: True if ok + message + the selected data
        """

        root_prims = []

        stage = omni.usd.get_context(context_plugin_data).get_stage()
        session_layer = stage.GetSessionLayer()
        for prim in stage.GetPseudoRoot().GetChildren():
            # Get all the root prims except for Session Layer prims
            if not schema_data.select_session_layer_prims and session_layer.GetPrimAtPath(prim.GetPath()):
                continue
            root_prims.append(prim)

        return True, "Ok", root_prims

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
