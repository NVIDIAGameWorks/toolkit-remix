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

import omni.kit.test
import omni.usd
from omni.flux.property_widget_builder.model.usd.utils import (
    get_item_relationships,
    is_property_relationship,
    is_relationship_overridden,
)
from pxr import Sdf


class TestRelationshipUtils(omni.kit.test.AsyncTestCase):
    """Test utility functions for USD relationship detection and access."""

    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None

    async def test_is_property_relationship_returns_true_for_relationship(self):
        """Arrange: Create relationship, Act: Check type, Assert: Returns True."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        prim.CreateRelationship("testRel")

        # Act
        result = is_property_relationship(self.stage, Sdf.Path("/TestPrim.testRel"))

        # Assert
        self.assertTrue(result, "Should detect relationship correctly")

    async def test_is_property_relationship_returns_false_for_attribute(self):
        """Arrange: Create attribute, Act: Check type, Assert: Returns False."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        prim.CreateAttribute("testAttr", Sdf.ValueTypeNames.Float)

        # Act
        result = is_property_relationship(self.stage, Sdf.Path("/TestPrim.testAttr"))

        # Assert
        self.assertFalse(result, "Should not detect attribute as relationship")

    async def test_is_property_relationship_returns_false_for_invalid_path(self):
        """Arrange: Invalid path, Act: Check type, Assert: Returns False."""
        # Arrange - no prim created

        # Act
        result = is_property_relationship(self.stage, Sdf.Path("/NonExistent.prop"))

        # Assert
        self.assertFalse(result, "Should return False for invalid paths")

    async def test_get_item_relationships_returns_valid_relationships(self):
        """Arrange: Create 2 relationships, Act: Get them, Assert: Returns both."""
        # Arrange
        prim1 = self.stage.DefinePrim("/Prim1")
        prim1.CreateRelationship("rel")
        prim2 = self.stage.DefinePrim("/Prim2")
        prim2.CreateRelationship("rel")

        # Act
        relationships = get_item_relationships(self.stage, [Sdf.Path("/Prim1.rel"), Sdf.Path("/Prim2.rel")])

        # Assert
        self.assertEqual(len(relationships), 2, "Should return both relationships")
        self.assertTrue(all(rel.IsValid() for rel in relationships), "All should be valid")

    async def test_get_item_relationships_skips_invalid_paths(self):
        """Arrange: Mix of valid and invalid, Act: Get them, Assert: Returns only valid."""
        # Arrange
        prim = self.stage.DefinePrim("/ValidPrim")
        prim.CreateRelationship("rel")

        # Act
        relationships = get_item_relationships(self.stage, [Sdf.Path("/ValidPrim.rel"), Sdf.Path("/Invalid.rel")])

        # Assert
        self.assertEqual(len(relationships), 1, "Should skip invalid path")
        self.assertTrue(relationships[0].IsValid(), "Returned relationship should be valid")

    async def test_is_relationship_overridden_returns_false_for_no_overrides(self):
        """Arrange: Relationship in root, Act: Check override, Assert: Returns False."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        rel = prim.CreateRelationship("rel")

        # Act
        result = is_relationship_overridden(self.stage, [rel])

        # Assert
        self.assertFalse(result, "Should not detect overrides when none exist")

    async def test_is_relationship_overridden_returns_false_for_empty_list(self):
        """Arrange: Empty list, Act: Check override, Assert: Returns False."""
        # Arrange - nothing

        # Act
        result = is_relationship_overridden(self.stage, [])

        # Assert
        self.assertFalse(result, "Should handle empty list gracefully")

    async def test_is_relationship_overridden_returns_false_for_none_stage(self):
        """Arrange: None stage, Act: Check override, Assert: Returns False."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        rel = prim.CreateRelationship("rel")

        # Act
        result = is_relationship_overridden(None, [rel])

        # Assert
        self.assertFalse(result, "Should handle None stage gracefully")
