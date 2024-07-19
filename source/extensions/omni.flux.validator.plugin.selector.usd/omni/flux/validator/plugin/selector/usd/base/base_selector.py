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

import omni.usd
from omni.flux.utils.common.utils import get_omni_prims as _get_omni_prims
from omni.flux.validator.factory import SelectorBase as _SelectorBase
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from pxr import Sdf, Usd


class SelectorUSDBase(_SelectorBase):
    class Data(_SelectorBase.Data):
        select_from_root_layer_only: bool = False

    @omni.usd.handle_exception
    async def _on_crash(self, schema_data: Any, context_plugin_data: _SetupDataTypeVar) -> None:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data of the plugin from the schema
        """
        context = omni.usd.get_context(context_plugin_data or "")
        if context and context.can_close_stage():
            stage = context.get_stage()
            root_layer = stage.GetRootLayer()
            # ugly work around to un-hold layers
            Sdf._TestTakeOwnership(root_layer)  # noqa
            await context.close_stage_async()

    def _get_prims(self, schema_data: Any, context_plugin_data: _SetupDataTypeVar) -> list["Usd.Prim"]:
        """
        Retrieve prims based on the given schema data and context plugin data.

        If `select_from_root_layer_only` is True in the schema data, the function retrieves the prims present on the
        root layer of the USD stage. Otherwise, it retrieves all prims from the entire stage.

        Args:
            schema_data: The data of the plugin from the schema.
            context_plugin_data: The context plugin data.

        Returns:
            A list of prims.
        """
        stage = omni.usd.get_context(context_plugin_data).get_stage()

        def traverse_instanced_children(prim, layer):
            for child in prim.GetFilteredChildren(Usd.PrimAllPrimsPredicate):
                # Discard omniverse prims
                if child.GetPath() in _get_omni_prims():
                    continue
                # If filtering for root layer prims, make sure the prim spec exists on the root layer
                if schema_data.select_from_root_layer_only and not layer.GetPrimAtPath(child.GetPath()):
                    continue
                yield child
                yield from traverse_instanced_children(child, layer)

        return list(traverse_instanced_children(stage.GetPseudoRoot(), stage.GetRootLayer()))
