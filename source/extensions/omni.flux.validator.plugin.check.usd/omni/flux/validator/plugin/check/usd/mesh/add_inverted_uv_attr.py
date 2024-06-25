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

import numpy as np
import omni.ui as ui
import omni.usd
from pxr import Sdf, UsdGeom

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD  # noqa PLE0402


class AddInvertedUVAttr(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        attr_name: str = "invertedUvs"

    name = "AddInvertedUVAttr"
    tooltip = (
        "This plugin will ensure all meshes have an `invertedUvs` property, which contains the texCoords with an"
        " inverted y coordinate."
    )
    data_type = Data
    display_name = "Add Inverted UV Attribute"

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to check if the input prims have an up to date invertedUvs property

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        message = "Check:\n"
        all_pass = True
        for prim in selector_plugin_data:
            gp_pv = UsdGeom.PrimvarsAPI(prim)
            if not gp_pv:
                message += f"- Invalid input: {str(prim.GetPath())}\n"
                continue

            st_prim_var = gp_pv.GetPrimvar("st")

            if st_prim_var:
                inverted_uvs_attr = prim.GetAttribute(schema_data.attr_name)
                if not inverted_uvs_attr:
                    message += f"- FAIL, never set: {str(prim.GetPath())}\n"
                    all_pass = False
                    continue

                inverted_uvs = np.array(inverted_uvs_attr.Get())
                flattened_uvs = np.array(st_prim_var.ComputeFlattened())
                if inverted_uvs.shape != flattened_uvs.shape:
                    message += f"- FAIL, length mismatch: {str(prim.GetPath())}\n"
                    all_pass = False
                    continue

                flattened_uvs[:, 1] = -flattened_uvs[:, 1]
                if not np.equal(inverted_uvs, flattened_uvs).all():
                    message += f"- FAIL, value mismatch: {str(prim.GetPath())}\n"
                    all_pass = False
                    continue

            message += f"- PASS: {str(prim.GetPath())}\n"

        return all_pass, message, None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to triangulate the mesh prims (including geom subsets)

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        message = "Fix:\n"
        all_pass = True
        with Sdf.ChangeBlock():
            for prim in selector_plugin_data:
                # get the primvars API of the prim
                gp_pv = UsdGeom.PrimvarsAPI(prim)
                if not gp_pv:
                    continue

                # get the primvars attribute of the UVs
                st_prim_var = gp_pv.GetPrimvar("st")

                if st_prim_var:
                    # [AJAUS] Because USD and Directx8/9 assume different texture coordinate origins,
                    # invert the vertical texture coordinate
                    uvs = np.array(st_prim_var.ComputeFlattened())
                    uvs[:, 1] = -uvs[:, 1]
                    prim.CreateAttribute(schema_data.attr_name, Sdf.ValueTypeNames.Float2Array, False).Set(uvs.tolist())

                message += f"- PASS: {str(prim.GetPath())}\n"

        return all_pass, message, None

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
