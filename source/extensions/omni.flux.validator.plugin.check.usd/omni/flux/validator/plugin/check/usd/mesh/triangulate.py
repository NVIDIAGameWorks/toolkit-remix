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
from pxr import Sdf, Usd, UsdGeom

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD  # noqa PLE0402


class Triangulate(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        pass

    name = "Triangulate"
    tooltip = "This plugin will check if meshes are triangulated, or triangulate them.  Includes processing GeomSubsets"
    data_type = Data
    display_name = "Triangulate Mesh"

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to check if the input prims are triangulated meshes

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
                message += f"- Triangulate only processes mesh prims. Invalid input: {str(prim.GetPath())}\n"

            faces = mesh.GetFaceVertexCountsAttr().Get()
            if faces is None:
                # the mesh is empty?
                message += f"- FAIL: {str(prim.GetPath())} is missing a valid `faces` attribute\n"
                all_pass = False
                continue
            if self._is_triangulated(faces):
                message += f"- PASS: {str(prim.GetPath())}\n"
            else:
                message += f"- FAIL: {str(prim.GetPath())}\n"
                all_pass = False

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
                message += f"- {str(prim.GetPath())}\n"
                if self._triangulate_mesh(prim):
                    message += f"- PASS: {str(prim.GetPath())}\n"
                else:
                    message += f"- FAIL: {str(prim.GetPath())}\n"
                    all_pass = False
        return all_pass, message, None

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")

    def _is_triangulated(self, faces):
        return set(faces) == {3}

    def _triangulate_mesh(self, prim: Usd.Prim):
        # indices and faces converted to triangles
        mesh = UsdGeom.Mesh(prim)
        faces = mesh.GetFaceVertexCountsAttr().Get()
        if faces is None:
            # the mesh is empty
            return False
        if self._is_triangulated(faces):
            return True

        indices = mesh.GetFaceVertexIndicesAttr().Get()

        if not indices or not faces:
            return True

        indices_offset = 0
        new_face_counts = []
        triangles = []
        subsets = []

        # need to update geom subset face lists
        display_predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
        children_iterator = iter(Usd.PrimRange(prim, display_predicate))
        for child_prim in children_iterator:
            if child_prim.IsA(UsdGeom.Subset):
                subset = UsdGeom.Subset.Get(prim.GetStage(), child_prim.GetPath())
                subsets.append(
                    {
                        "subset": subset,
                        "old_faces": set(subset.GetIndicesAttr().Get()),  # set of old face indices in this subset
                        "new_faces": [],  # the new face index list
                    }
                )

        for old_face_index, face_count in enumerate(faces):
            start_index = indices[indices_offset]
            for face_index in range(face_count - 2):
                for subset in subsets:
                    if old_face_index in subset["old_faces"]:
                        subset["new_faces"].append(len(new_face_counts))
                new_face_counts.append(3)
                index1 = indices_offset + face_index + 1
                index2 = indices_offset + face_index + 2
                triangles.append(start_index)
                triangles.append(indices[index1])
                triangles.append(indices[index2])
            indices_offset += face_count

        for subset in subsets:
            subset["subset"].GetIndicesAttr().Set(subset["new_faces"])

        mesh.GetFaceVertexIndicesAttr().Set(triangles)
        mesh.GetFaceVertexCountsAttr().Set(new_face_counts)
        return True
