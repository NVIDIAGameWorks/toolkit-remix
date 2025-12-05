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
from omni.flux.property_widget_builder.model.usd import USDRelationshipItem
from pxr import Sdf


class TestUSDRelationshipItem(omni.kit.test.AsyncTestCase):
    """Test USDRelationshipItem following Arrange-Act-Assert pattern."""

    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None

    async def test_create_item_initializes_correctly(self):
        """Arrange: Create relationship, Act: Create item, Assert: Properties set."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        prim.CreateRelationship("testRel")

        # Act
        item = USDRelationshipItem(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            display_attr_names=["Test Relationship"],
            display_attr_names_tooltip=["Test tooltip"],
            read_only=False,
        )

        # Assert
        self.assertEqual(item.element_count, 1, "Relationships always have element_count = 1")
        self.assertEqual(len(item.name_models), 1, "Should have one name model")
        self.assertEqual(len(item.value_models), 1, "Should have one value model")
        self.assertFalse(item.read_only, "Should not be read_only")

    async def test_item_name_model_displays_custom_name(self):
        """Arrange: Create item with custom name, Act: Get name, Assert: Shows custom name."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        prim.CreateRelationship("testRel")

        # Act
        item = USDRelationshipItem(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            display_attr_names=["Custom Name"],
            read_only=False,
        )

        # Assert
        name = item.name_models[0].get_value_as_string()
        self.assertEqual(name, "Custom Name", "Should display custom name")

    async def test_item_value_model_reads_relationship_target(self):
        """Arrange: Relationship with target, Act: Create item, Assert: Value model reads target."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        relationship = prim.CreateRelationship("testRel")
        relationship.SetTargets([Sdf.Path("/TargetPrim")])

        # Act
        item = USDRelationshipItem(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            read_only=False,
        )

        # Assert
        value = item.value_models[0].get_value()
        self.assertEqual(value, "/TargetPrim", "Value model should read existing target")

    async def test_item_value_model_sets_relationship_target(self):
        """Arrange: Create item, Act: Set via value model, Assert: USD updated."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        relationship = prim.CreateRelationship("testRel")
        self.stage.DefinePrim("/NewTarget")

        item = USDRelationshipItem(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            read_only=False,
        )

        # Act
        item.value_models[0].set_value("/NewTarget")
        await omni.kit.app.get_app().next_update_async()

        # Assert
        targets = relationship.GetTargets()
        self.assertEqual(len(targets), 1, "Should have one target")
        self.assertEqual(str(targets[0]), "/NewTarget", "Should be /NewTarget")

    async def test_item_refresh_updates_value_models(self):
        """Arrange: Change relationship externally, Act: Refresh item, Assert: Values updated."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        relationship = prim.CreateRelationship("testRel")

        item = USDRelationshipItem(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            read_only=False,
        )

        # Act - change externally then refresh
        relationship.SetTargets([Sdf.Path("/ExternalChange")])
        item.refresh()

        # Assert
        value = item.value_models[0].get_value()
        self.assertEqual(value, "/ExternalChange", "Refresh should update value from USD")

    async def test_read_only_item_cannot_modify_relationship(self):
        """Arrange: Read-only item, Act: Try to set, Assert: No change."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        relationship = prim.CreateRelationship("testRel")

        item = USDRelationshipItem(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            read_only=True,
        )

        # Act
        item.value_models[0].set_value("/Target")
        await omni.kit.app.get_app().next_update_async()

        # Assert
        targets = relationship.GetTargets()
        self.assertEqual(len(targets), 0, "Read-only item should not modify USD")
        self.assertTrue(item.read_only, "Item should report as read-only")

    async def test_item_with_multiple_relationships_updates_all(self):
        """Arrange: Item with 2 relationships, Act: Set value, Assert: Both updated."""
        # Arrange
        prim1 = self.stage.DefinePrim("/Prim1")
        rel1 = prim1.CreateRelationship("rel")

        prim2 = self.stage.DefinePrim("/Prim2")
        rel2 = prim2.CreateRelationship("rel")

        item = USDRelationshipItem(
            context_name="",
            relationship_paths=[Sdf.Path("/Prim1.rel"), Sdf.Path("/Prim2.rel")],
            read_only=False,
        )

        # Act
        item.value_models[0].set_value("/CommonTarget")
        await omni.kit.app.get_app().next_update_async()

        # Assert
        targets1 = rel1.GetTargets()
        targets2 = rel2.GetTargets()
        self.assertEqual(str(targets1[0]), "/CommonTarget", "First rel should be updated")
        self.assertEqual(str(targets2[0]), "/CommonTarget", "Second rel should be updated")
