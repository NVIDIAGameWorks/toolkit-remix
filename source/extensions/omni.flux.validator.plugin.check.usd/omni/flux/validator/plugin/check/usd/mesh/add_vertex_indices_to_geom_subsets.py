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


class AddVertexIndicesToGeomSubsets(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        pass

    name = "AddVertexIndicesToGeomSubsets"
    tooltip = (
        "This plugin will ensure any GeomSubsets of the input triangulated mesh prims have up-to-date per-vertex"
        " indices properties."
    )
    data_type = Data
    display_name = "Add Vertex Indices to Geometry Subsets"

    _attr_name = "triangleIndices"

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to check if the input prims have up to date geom subsets

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        message = "Check:\n"
        all_pass = True
        for prim in selector_plugin_data:
            mesh = UsdGeom.Mesh(prim)
            if not mesh:
                message += f"- Invalid input: {str(prim.GetPath())} is not a mesh prim. \n"
                # Not a valid input, but also not broken
                continue

            faces = mesh.GetFaceVertexCountsAttr().Get()
            if not faces:
                message += f"- Invalid input: {str(prim.GetPath())} is missing a valid `faces` attribute. \n"
                all_pass = False
                continue

            if not self._is_triangulated(faces):
                message += f"- Invalid input: {str(prim.GetPath())} is not triangulated. \n"
                all_pass = False
                continue

            face_vertex_indices = mesh.GetFaceVertexIndicesAttr().Get()
            display_predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
            children_iterator = iter(Usd.PrimRange(prim, display_predicate))
            prim_passed = True
            for child_prim in children_iterator:
                if child_prim.IsA(UsdGeom.Subset):
                    vert_indices_attr = child_prim.GetAttribute(self._attr_name)
                    if not vert_indices_attr:
                        prim_passed = False
                        break

                    subset = UsdGeom.Subset(child_prim)
                    face_indices = subset.GetIndicesAttr().Get()
                    vert_indices = vert_indices_attr.Get()
                    for i, face_index in enumerate(face_indices):
                        if (
                            vert_indices[i * 3 + 0] != face_vertex_indices[face_index * 3 + 0]
                            or vert_indices[i * 3 + 1] != face_vertex_indices[face_index * 3 + 1]
                            or vert_indices[i * 3 + 2] != face_vertex_indices[face_index * 3 + 2]
                        ):
                            prim_passed = False
                            break
                if not prim_passed:
                    break

            if not prim_passed:
                message += f"- FAIL: {str(prim.GetPath())}\n"
                all_pass = False
            else:
                message += f"- PASS: {str(prim.GetPath())}\n"

        return all_pass, message, None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
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
                mesh = UsdGeom.Mesh(prim)
                if not mesh:
                    message += f"- Invalid input - not a mesh: {str(prim.GetPath())}\n"
                    continue
                faces = mesh.GetFaceVertexCountsAttr().Get()
                if not faces:
                    message += f"- Invalid input - no faces: {str(prim.GetPath())}\n"
                    all_pass = False
                    continue
                if not self._is_triangulated(faces):
                    message += f"- Invalid input - not triangulated: {str(prim.GetPath())}\n"
                    all_pass = False
                    continue
                face_vertex_indices = mesh.GetFaceVertexIndicesAttr().Get()
                display_predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
                children_iterator = iter(Usd.PrimRange(prim, display_predicate))
                for child_prim in children_iterator:
                    if child_prim.IsA(UsdGeom.Subset):
                        subset = UsdGeom.Subset(child_prim)
                        face_indices = subset.GetIndicesAttr().Get()
                        vert_indices = []
                        for face_index in face_indices:
                            vert_indices.append(face_vertex_indices[face_index * 3 + 0])
                            vert_indices.append(face_vertex_indices[face_index * 3 + 1])
                            vert_indices.append(face_vertex_indices[face_index * 3 + 2])
                        child_prim.CreateAttribute(self._attr_name, Sdf.ValueTypeNames.IntArray).Set(vert_indices)

                message += f"- PASS: {str(prim.GetPath())}\n"

        return all_pass, message, None

    def _is_triangulated(self, faces):
        return set(faces) == {3}

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
