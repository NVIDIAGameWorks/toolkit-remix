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

from __future__ import annotations

from typing import Any

import omni.kit.app
import omni.kit.material.library
from omni import ui, usd
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from pxr import Tf, Usd, UsdGeom, UsdShade

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD


class DefaultMaterial(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        # The first shader will be used by default when converting invalid materials
        context_name: str = ""
        default_material_mdl_url: str = "OmniPBR.mdl"
        default_material_mdl_name: str = "OmniPBR"

    name = "DefaultMaterial"
    tooltip = "This plugin will ensure all meshes in the stage use valid materials"
    data_type = Data
    display_name = "Create Default Materials"

    @usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns:
            bool: True if the check passed, False if not. If the check is True, it will NOT run the fix
            str: the message you want to show, like "Succeeded to check this"
            any: data that you want to pass. For now this is used no where. So you can pass whatever you want (None)
        """
        message = "Check:\n"
        progress = 0
        success = True

        self.on_progress(progress, "Start", success)

        if selector_plugin_data:
            progress_delta = 1 / len(selector_plugin_data)
            stage = usd.get_context(context_plugin_data).get_stage()

            for p in selector_plugin_data:
                prim = stage.GetPrimAtPath(p.GetPath())

                prims_without_materials = await self._get_children_without_materials(prim)

                # if we have prims without materials, then it's not valid, and we must fix
                is_valid = len(prims_without_materials) == 0

                result_message = ""

                if is_valid:
                    result_message = f"- OK: {str(p.GetPath())}\n"
                else:
                    for to_fix in prims_without_materials:
                        result_message += f"- CHECK: {str(to_fix.GetPath())}\n"

                message += result_message
                progress += progress_delta

                success &= is_valid
                self.on_progress(progress, result_message, success)
        else:
            message += "- SKIPPED: No selected prims"

        return success, message, None

    @usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to fix the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns:
            bool: True if the check passed, False if not. If the check is True, it will NOT run the fix
            str: the message you want to show, like "Succeeded to check this"
            any: data that you want to pass. For now this is used no where. So you can pass whatever you want (None)
        """
        message = "Fix:\n"
        progress = 0
        success = True

        self.on_progress(progress, "Start", success)

        if selector_plugin_data:
            progress_delta = 1 / len(selector_plugin_data)

            for prim in selector_plugin_data:
                was_fixed = True
                result_message = ""

                # get list of prims to fix
                prims_without_materials = await self._get_children_without_materials(prim)

                # do the fixing (create default materials where none existed)
                for to_fix in prims_without_materials:
                    was_fixed &= await self._create_default_material(context_plugin_data, schema_data, to_fix)
                    result_message += f"- {'FIXED' if was_fixed else 'ERROR'}: {str(to_fix.GetPath())}\n"

                message += result_message
                progress += progress_delta
                success &= was_fixed
                self.on_progress(progress, result_message, success)

        return success, message, None

    @usd.handle_exception
    async def _get_children_without_materials(self, prim) -> list[Usd.Prim]:
        prims_without_material = []

        # is there any material bound to this prim?
        bound_material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        empty_mesh = False

        # when no material is detected
        if not bound_material:
            has_geom_subset = False
            display_predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
            children_iterator = iter(Usd.PrimRange(prim, display_predicate))
            # first check if the mesh prim has any geometry subsets
            for child_prim in children_iterator:
                if child_prim.IsA(UsdGeom.Mesh) and not UsdGeom.Mesh(prim).GetPointsAttr().Get():
                    # skip empty mesh
                    empty_mesh = True
                    continue
                if child_prim.IsA(UsdGeom.Subset):
                    has_geom_subset = True
                    subset_bound_material, _ = UsdShade.MaterialBindingAPI(child_prim).ComputeBoundMaterial()
                    if not subset_bound_material and child_prim.IsValid():
                        prims_without_material.append(child_prim)

            # if there's no geomsubsets, use the parent prim to determine validity
            if not has_geom_subset and prim.IsValid() and not empty_mesh:
                prims_without_material.append(prim)

        return prims_without_material

    @usd.handle_exception
    async def _create_default_material(
        self, context_plugin_data: _SetupDataTypeVar, schema_data: Data, prim: Usd.Prim
    ) -> bool:
        stage = omni.usd.get_context(context_plugin_data).get_stage()

        # create a unique valid prim path based on the filename
        mtl_path = omni.usd.get_stage_next_free_path(
            stage, f"/AssetImporter/Looks/{Tf.MakeValidIdentifier(_OmniUrl(prim).stem)}", False
        )

        # create a new OmniPBR node
        omni.kit.commands.execute(
            "CreateMdlMaterialPrim",
            mtl_url=schema_data.default_material_mdl_url,
            mtl_name=schema_data.default_material_mdl_name,
            mtl_path=mtl_path,
            stage=stage,
        )

        # validate the new material was created
        output_material_prim = stage.GetPrimAtPath(mtl_path)
        if not omni.usd.get_shader_from_material(output_material_prim, get_prim=True):
            return False

        # bind newly created material to desired prim
        omni.kit.commands.execute(
            "BindMaterial",
            prim_path=prim.GetPath(),
            material_path=output_material_prim.GetPath(),
            strength=UsdShade.Tokens.strongerThanDescendants,
            stage=stage,
        )

        return True

    @usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
