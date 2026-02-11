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

import omni.kit.app
import omni.kit.material.library
from omni import ui, usd
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from omni.usd.commands import prim_can_be_removed_without_destruction as _prim_can_be_removed_without_destruction
from pxr import UsdShade

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD


class ClearUnassignedMaterial(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        pass

    name = "ClearUnassignedMaterial"
    tooltip = "This plugin will delete materials that are not assigned to anything"
    data_type = Data
    display_name = "Clear Unassigned Material"

    def get_not_assigned_materials(self, stage, assigned_materials):
        return [
            str(prim.GetPath())
            for prim in stage.TraverseAll()
            if prim.IsA(UsdShade.Material)
            and _prim_can_be_removed_without_destruction(stage, prim.GetPath())
            and prim.GetPath() not in assigned_materials
        ]

    def get_assigned_materials(self, message, stage, selector_plugin_data):
        assigned_materials = set()
        progress = 0
        progress_delta = 0.9 / len(selector_plugin_data)

        for p in selector_plugin_data:
            prim = stage.GetPrimAtPath(p.GetPath())

            result_message = f"- Checking: {str(p.GetPath())}\n"

            if not omni.usd.is_prim_material_supported(prim):
                continue
            mat, _rel = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
            if mat:
                assigned_materials.add(mat.GetPrim().GetPath())

            message += result_message
            progress += progress_delta

            self.on_progress(progress, result_message, True)
        return assigned_materials

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
            stage = usd.get_context(context_plugin_data).get_stage()

            assigned_materials = self.get_assigned_materials(message, stage, selector_plugin_data)

            no_assigned_materials = self.get_not_assigned_materials(stage, assigned_materials)
            success = not bool(no_assigned_materials)
            progress += 0.1
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
            stage = usd.get_context(context_plugin_data).get_stage()
            assigned_materials = self.get_assigned_materials(message, stage, selector_plugin_data)

            to_delete = self.get_not_assigned_materials(stage, assigned_materials)
            message += f"Deleting:\n{to_delete}"
            omni.kit.commands.execute("DeletePrims", paths=to_delete, stage=stage)
            progress += 0.1

        return success, message, None

    @usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
