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
from pxr import Sdf, Usd, UsdGeom

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD


class ForcePrimvarToVertexInterpolation(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        pass

    name = "ForcePrimvarToVertexInterpolation"
    tooltip = (
        "This plugin will ensure that per vertex data does not use the `varying` or `faceVarying` interpolation"
        " schemes."
    )
    data_type = Data
    display_name = "Force Vertex Interpolation"

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to check if the input prims' vertex data is correctly interpolated. Remix doesn't
        support USD's `varying` or `faceVarying` interpolation schemes, so any mesh using those will fail this check.
        Further reading: https://graphics.pixar.com/usd/dev/api/class_usd_geom_primvar.html#Usd_InterpolationVals

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        message = "Check:\n"
        all_pass = True
        for prim in selector_plugin_data:
            if not prim.IsA(UsdGeom.Mesh):
                message += (
                    "- ForcePrimvarToVertexInterpolation only processes mesh prims. Invalid input:"
                    f" {str(prim.GetPath())}\n"
                )

            message += f"- Checking {str(prim.GetPath())} "
            if self._is_aligned(prim):
                message += "- PASS\n"
            else:
                message += "- FAIL\n"
                all_pass = False

        return all_pass, message, None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to recompute all primvars (including Normals) that use `varying` or `faceVarying
        interpoltion to use `vertex` interpolation.  To achieve this, all vertices will be split per face, and the index
        array will become [0, 1, 2, 3...].

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
                message += f"- Fixing {str(prim.GetPath())}"
                if self._align_vertex_data(prim):
                    message += "- PASS\n"
                else:
                    message += "- FAIL\n"
                    all_pass = False
        return all_pass, message, None

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")

    def _is_aligned(self, prim: Usd.Prim):
        mesh = UsdGeom.Mesh(prim)
        if mesh.GetFaceVertexCountsAttr().Get() is None:
            # the mesh is empty?
            return False
        normals_interp = mesh.GetNormalsInterpolation()
        if normals_interp in (UsdGeom.Tokens.faceVarying, UsdGeom.Tokens.varying):
            return False

        primvar_api = UsdGeom.PrimvarsAPI(prim)
        for primvar in primvar_api.GetPrimvars():
            interpolation = primvar.GetInterpolation()
            if interpolation in (UsdGeom.Tokens.faceVarying, UsdGeom.Tokens.varying):
                return False
        return True

    def _align_vertex_data(self, prim: Usd.Prim):
        # get the mesh schema API from the Prim
        mesh = UsdGeom.Mesh(prim)
        if mesh.GetFaceVertexCountsAttr().Get() is None:
            # the mesh is empty?
            return False

        face_vertex_indices = mesh.GetFaceVertexIndicesAttr().Get()
        points = mesh.GetPointsAttr().Get()

        primvar_api = UsdGeom.PrimvarsAPI(prim)
        geom_tokens = [UsdGeom.Tokens.faceVarying, UsdGeom.Tokens.varying, UsdGeom.Tokens.vertex]
        primvars = [
            {
                "primvar": primvar,
                "values": primvar.ComputeFlattened(),
                "fixed_values": [],
                "interpolation": primvar.GetInterpolation(),
                "element_size": primvar.GetElementSize(),
            }
            for primvar in primvar_api.GetPrimvars()
            if primvar.GetInterpolation() in geom_tokens
        ]

        fixed_indices = range(0, len(face_vertex_indices))
        fixed_points = [points[face_vertex_indices[i]] for i in fixed_indices]

        for primvar in primvars:
            if primvar["interpolation"] == UsdGeom.Tokens.vertex:
                element_size = primvar["element_size"]
                primvar["fixed_values"] = [
                    primvar["values"][face_vertex_indices[i] * element_size + j]
                    for i in fixed_indices
                    for j in range(element_size)
                ]

        normals_interp = mesh.GetNormalsInterpolation()
        normals = mesh.GetNormalsAttr().Get()
        if normals_interp == UsdGeom.Tokens.vertex and normals:
            # Normals are currently in the (old) vertex order.  need to expand them to be 1 normal per vertex per face
            fixed_normals = [normals[face_vertex_indices[i]] for i in fixed_indices]
            mesh.GetNormalsAttr().Set(fixed_normals)
        else:
            # Normals are already in 1 normal per vertex per face, need to set it to vertex so that triangulation
            # doesn't break it.
            mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)

        mesh.GetFaceVertexIndicesAttr().Set(fixed_indices)
        mesh.GetPointsAttr().Set(fixed_points)
        for primvar in primvars:
            if primvar["interpolation"] == UsdGeom.Tokens.vertex:
                primvar["values"] = primvar["fixed_values"]
            primvar["primvar"].Set(primvar["values"])
            primvar["primvar"].BlockIndices()
            primvar["primvar"].SetInterpolation(UsdGeom.Tokens.vertex)

        return True
