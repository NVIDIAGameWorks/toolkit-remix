"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ("TestPrimCollection",)

import omni.kit.app
import omni.kit.test
import omni.usd
from omni.flux.stage_prim_picker.widget.prim_collection import PrimCollection
from pxr import UsdGeom


class TestPrimCollection(omni.kit.test.AsyncTestCase):
    """
    Unit tests for PrimCollection pagination and has_more accuracy.

    These tests verify that has_more accurately reflects whether there are
    actually more items beyond the current limit, not just whether the limit
    was reached.
    """

    async def setUp(self):
        self._context_name = ""  # Default context
        self.context = omni.usd.get_context(self._context_name)
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
        if self.context and self.context.get_stage():
            await self.context.close_stage_async()
        self.stage = None

    async def test_has_more_false_when_exactly_at_limit(self):
        """has_more=False when stage has exactly limit items (no items beyond)."""
        # Arrange - Create exactly 5 prims
        UsdGeom.Xform.Define(self.stage, "/World")
        for i in range(4):
            UsdGeom.Mesh.Define(self.stage, f"/World/Mesh_{i}")

        collection = PrimCollection(self._context_name, initial_items=5)

        # Act
        prim_items, has_more = collection.get_prim_paths()

        # Assert - 5 items returned (World + 4 meshes), no more available
        self.assertEqual(len(prim_items), 5)
        self.assertFalse(has_more, "has_more should be False when exactly at limit with no items beyond")

    async def test_has_more_true_when_items_beyond_limit(self):
        """has_more=True when stage has more items than the limit."""
        # Arrange - Create 10 prims, limit to 5
        UsdGeom.Xform.Define(self.stage, "/World")
        for i in range(9):
            UsdGeom.Mesh.Define(self.stage, f"/World/Mesh_{i}")

        collection = PrimCollection(self._context_name, initial_items=5)

        # Act
        prim_items, has_more = collection.get_prim_paths()

        # Assert - 5 items returned, more available
        self.assertEqual(len(prim_items), 5)
        self.assertTrue(has_more, "has_more should be True when items exist beyond limit")

    async def test_has_more_false_when_fewer_than_limit(self):
        """has_more=False when stage has fewer items than the limit."""
        # Arrange - Create 3 prims, limit to 10
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Mesh.Define(self.stage, "/World/Mesh_0")
        UsdGeom.Mesh.Define(self.stage, "/World/Mesh_1")

        collection = PrimCollection(self._context_name, initial_items=10)

        # Act
        prim_items, has_more = collection.get_prim_paths()

        # Assert - 3 items returned, no more available
        self.assertEqual(len(prim_items), 3)
        self.assertFalse(has_more, "has_more should be False when fewer items than limit")

    async def test_has_more_false_with_filter_exact_match_count(self):
        """has_more=False when filtered results exactly match limit."""
        # Arrange - Create 5 meshes and 5 spheres, filter to meshes with limit 5
        UsdGeom.Xform.Define(self.stage, "/World")
        for i in range(5):
            UsdGeom.Mesh.Define(self.stage, f"/World/Mesh_{i}")
        for i in range(5):
            UsdGeom.Sphere.Define(self.stage, f"/World/Sphere_{i}")

        collection = PrimCollection(self._context_name, initial_items=5)

        # Act - Filter to only meshes
        prim_items, has_more = collection.get_prim_paths(search_filter="Mesh")

        # Assert - Exactly 5 meshes, no more matching the filter
        self.assertEqual(len(prim_items), 5)
        self.assertFalse(has_more, "has_more should be False when filtered results exactly match limit")

    async def test_has_more_true_with_filter_more_matches(self):
        """has_more=True when filtered results exceed limit."""
        # Arrange - Create 10 meshes and 5 spheres, filter to meshes with limit 5
        UsdGeom.Xform.Define(self.stage, "/World")
        for i in range(10):
            UsdGeom.Mesh.Define(self.stage, f"/World/Mesh_{i}")
        for i in range(5):
            UsdGeom.Sphere.Define(self.stage, f"/World/Sphere_{i}")

        collection = PrimCollection(self._context_name, initial_items=5)

        # Act - Filter to only meshes
        prim_items, has_more = collection.get_prim_paths(search_filter="Mesh")

        # Assert - 5 meshes returned, more available
        self.assertEqual(len(prim_items), 5)
        self.assertTrue(has_more, "has_more should be True when more filtered results exist")

    async def test_load_more_increases_limit(self):
        """load_more() increases the limit for subsequent get_prim_paths calls."""
        # Arrange
        UsdGeom.Xform.Define(self.stage, "/World")
        for i in range(20):
            UsdGeom.Mesh.Define(self.stage, f"/World/Mesh_{i}")

        collection = PrimCollection(self._context_name, initial_items=5, page_size=10)

        # Act - Initial fetch
        prim_items1, has_more1 = collection.get_prim_paths()
        # Load more
        collection.load_more()
        prim_items2, has_more2 = collection.get_prim_paths()

        # Assert
        self.assertEqual(len(prim_items1), 5)
        self.assertTrue(has_more1)
        self.assertEqual(len(prim_items2), 15)  # 5 + 10
        self.assertTrue(has_more2)  # Still more (21 total: World + 20 meshes)

    async def test_empty_stage_has_more_false(self):
        """has_more=False when stage is empty."""
        # Arrange - Empty stage (just default root)
        collection = PrimCollection(self._context_name, initial_items=10)

        # Act
        _, has_more = collection.get_prim_paths()

        # Assert - Empty or minimal items, no more
        self.assertFalse(has_more, "has_more should be False on empty stage")
