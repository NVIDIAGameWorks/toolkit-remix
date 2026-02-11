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
from omni.flux.utils.common import path_utils as _path_utils
from pxr import Sdf

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD


class RelativeReferences(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        pass

    name = "RelativeReferences"
    tooltip = "This plugin will replace absolute reference paths with relative paths."
    data_type = Data
    display_name = "Make References Relative"

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to check if the input prims have absolute paths in their references

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        message = "Check:\n"
        all_pass = True
        for prim in selector_plugin_data:
            refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
            abs_references = []
            for ref, _ in refs_and_layers:
                if _path_utils.is_absolute_path(str(ref.assetPath)):
                    abs_references.append(str(ref.assetPath))

            if len(abs_references) > 0:
                message += f"- FAIL: {str(prim.GetPath())} references: {abs_references}\n"
                all_pass = False
            else:
                message += f"- PASS: {str(prim.GetPath())}\n"

        return all_pass, message, None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to change all reference paths to relative.

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        message = "Fix:\n"
        all_pass = True
        stage = omni.usd.get_context(context_plugin_data).get_stage()
        cur_layer = stage.GetEditTarget().GetLayer()
        base_path = cur_layer.identifier
        all_layers = stage.GetUsedLayers()
        all_layers.reverse()
        weaker_layers = set()
        for layer in all_layers:
            if layer == cur_layer:
                break
            weaker_layers.add(layer)
        for prim in selector_plugin_data:
            refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
            abs_in_current_layer = False
            abs_in_weaker_layer = False
            unfixiable = False
            for ref, ref_layer in refs_and_layers:
                if _path_utils.is_absolute_path(str(ref.assetPath)):
                    if ref_layer == cur_layer:
                        abs_in_current_layer = True
                    elif ref_layer in weaker_layers:
                        abs_in_weaker_layer = True
                    else:
                        # Absolute reference is in a layer stronger than the current Edit target, cannot be fixed.
                        unfixiable = True

            if abs_in_weaker_layer:
                # absolute path in a sublayer - need to flatten all the weaker references into this layer to fix it.
                refs = []
                for ref, ref_layer in refs_and_layers:
                    if ref_layer in weaker_layers:
                        # Need to convert references to absolute paths.
                        abs_path = Sdf.ComputeAssetPathRelativeToLayer(ref_layer, ref.assetPath)
                        rel_path = omni.client.make_relative_url(base_path, abs_path)
                        refs.append(
                            Sdf.Reference(
                                assetPath=rel_path,
                                primPath=ref.primPath,
                                customData=ref.customData,
                            )
                        )

                prim.GetReferences().SetReferences(refs)
            elif abs_in_current_layer:
                # absolute path in the current edit layer - need to fix it without stomping lower level references.
                stack = prim.GetPrimStack()
                for prim_spec in stack:
                    if prim_spec.layer == cur_layer:
                        op = prim_spec.GetInfo(Sdf.PrimSpec.ReferencesKey)
                        if op.isExplicit:
                            op.explicitItems = self._make_refs_relative(cur_layer, op.explicitItems)
                        else:
                            op.addedItems = self._make_refs_relative(cur_layer, op.addedItems)
                            op.prependedItems = self._make_refs_relative(cur_layer, op.prependedItems)
                            op.appendedItems = self._make_refs_relative(cur_layer, op.appendedItems)
                            op.deletedItems = self._make_refs_relative(cur_layer, op.deletedItems)
                            op.orderedItems = self._make_refs_relative(cur_layer, op.orderedItems)

                        prim_spec.SetInfo(Sdf.PrimSpec.ReferencesKey, op)
                        break
            if unfixiable:
                message += f"- FAIL: absolute reference exists above current EditTarget. {str(prim.GetPath())}\n"
                all_pass = False
            else:
                message += f"- PASS: {str(prim.GetPath())}\n"

        return all_pass, message, None

    def _make_refs_relative(self, layer, refs):
        ret_refs = []
        for ref in refs:
            if _path_utils.is_absolute_path(str(ref.assetPath)):
                rel_path = omni.client.make_relative_url(layer.identifier, str(ref.assetPath))
                ref_new = Sdf.Reference(
                    assetPath=rel_path,
                    primPath=ref.primPath,
                    layerOffset=ref.layerOffset,
                    customData=ref.customData,
                )
            else:
                ref_new = ref
            ret_refs.append(ref_new)
        return ret_refs

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
