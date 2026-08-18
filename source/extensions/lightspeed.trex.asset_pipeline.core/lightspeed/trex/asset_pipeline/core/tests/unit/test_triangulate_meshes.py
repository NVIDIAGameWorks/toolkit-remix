"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import omni.kit.test
from pxr import Usd, UsdGeom, Vt

from lightspeed.trex.asset_pipeline.core.steps.triangulate_meshes import _is_triangulated, _triangulate_mesh


class TestTriangulateMeshes(omni.kit.test.AsyncTestCase):
    async def test_is_triangulated_returns_true_only_when_all_faces_are_triangles(self):
        """Triangulation checks stream face counts without requiring a unique-count collection."""
        # Arrange
        triangle_counts = Vt.IntArray([3, 3, 3])
        mixed_counts = Vt.IntArray([3, 4, 3])

        # Act
        all_triangles = _is_triangulated(triangle_counts)
        has_quad = _is_triangulated(mixed_counts)
        has_no_counts = _is_triangulated(None)

        # Assert
        self.assertTrue(all_triangles)
        self.assertFalse(has_quad)
        self.assertFalse(has_no_counts)

    async def test_triangulate_mesh_remaps_direct_subsets_only(self):
        """Triangulation updates direct material subsets without flattening nested subset scopes."""
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        mesh = UsdGeom.Mesh.Define(stage, "/World/Mesh")
        mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray([4]))
        mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray([0, 1, 2, 3]))
        direct_subset = UsdGeom.Subset.Define(stage, "/World/Mesh/DirectSubset")
        direct_subset.CreateIndicesAttr(Vt.IntArray([0]))
        nested_subset = UsdGeom.Subset.Define(stage, "/World/Mesh/DirectSubset/NestedSubset")
        nested_subset.CreateIndicesAttr(Vt.IntArray([0]))

        # Act
        changed = _triangulate_mesh(mesh.GetPrim())

        # Assert
        self.assertTrue(changed)
        self.assertEqual(list(mesh.GetFaceVertexCountsAttr().Get()), [3, 3])
        self.assertEqual(list(direct_subset.GetIndicesAttr().Get()), [0, 1])
        self.assertEqual(list(nested_subset.GetIndicesAttr().Get()), [0])

    async def test_triangulate_mesh_preserves_subsets_without_indices(self):
        """Partially-authored subsets keep unset indices while valid mesh topology is triangulated."""
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        mesh = UsdGeom.Mesh.Define(stage, "/World/Mesh")
        mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray([4]))
        mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray([0, 1, 2, 3]))
        subset = UsdGeom.Subset(stage.DefinePrim("/World/Mesh/Subset", "GeomSubset"))

        # Act
        changed = _triangulate_mesh(mesh.GetPrim())

        # Assert
        self.assertTrue(changed)
        self.assertEqual(list(mesh.GetFaceVertexCountsAttr().Get()), [3, 3])
        self.assertFalse(subset.GetIndicesAttr().HasAuthoredValue())
