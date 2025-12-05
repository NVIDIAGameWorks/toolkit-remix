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
from omni.flux.property_widget_builder.model.usd.item_model.relationship_value import UsdRelationshipValueModel
from pxr import Sdf


class TestUsdRelationshipValueModel(omni.kit.test.AsyncTestCase):
    """Test UsdRelationshipValueModel following Arrange-Act-Assert pattern."""

    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None

    async def test_create_model_initializes_with_empty_value(self):
        """Arrange: Create relationship, Act: Create model, Assert: Value is empty."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        prim.CreateRelationship("testRel")

        # Act
        model = UsdRelationshipValueModel(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            read_only=False,
        )

        # Assert
        self.assertEqual(model.get_value(), "", "Initial value should be empty")
        self.assertFalse(model.is_mixed, "Should not be mixed initially")
        self.assertTrue(model.is_default, "Empty relationship should be default")

    async def test_set_value_updates_relationship_target(self):
        """Arrange: Create relationship, Act: Set value, Assert: Target set in USD."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        relationship = prim.CreateRelationship("testRel")
        self.stage.DefinePrim("/TargetPrim")

        model = UsdRelationshipValueModel(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            read_only=False,
        )

        # Act
        model.set_value("/TargetPrim")
        await omni.kit.app.get_app().next_update_async()

        # Assert
        targets = relationship.GetTargets()
        self.assertEqual(len(targets), 1, "Should have one target")
        self.assertEqual(str(targets[0]), "/TargetPrim", "Target should be /TargetPrim")
        self.assertEqual(model.get_value(), "/TargetPrim", "Model value should match")

    async def test_set_value_with_empty_string_clears_targets(self):
        """Arrange: Relationship with target, Act: Set empty, Assert: Targets cleared."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        relationship = prim.CreateRelationship("testRel")
        relationship.SetTargets([Sdf.Path("/TargetPrim")])

        model = UsdRelationshipValueModel(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            read_only=False,
        )

        # Act
        model.set_value("")
        await omni.kit.app.get_app().next_update_async()

        # Assert
        targets = relationship.GetTargets()
        self.assertEqual(len(targets), 0, "Should have no targets")
        self.assertEqual(model.get_value(), "", "Model value should be empty")

    async def test_refresh_reads_current_target_from_usd(self):
        """Arrange: Set target externally, Act: Refresh model, Assert: Model updated."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        relationship = prim.CreateRelationship("testRel")

        model = UsdRelationshipValueModel(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            read_only=False,
        )

        # Act - set target externally
        relationship.SetTargets([Sdf.Path("/ExternalTarget")])
        model.refresh()

        # Assert
        self.assertEqual(model.get_value(), "/ExternalTarget", "Should read external changes")

    async def test_read_only_model_cannot_set_value(self):
        """Arrange: Read-only model, Act: Try to set, Assert: No change in USD."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        relationship = prim.CreateRelationship("testRel")

        model = UsdRelationshipValueModel(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            read_only=True,
        )

        # Act
        model.set_value("/TargetPrim")
        await omni.kit.app.get_app().next_update_async()

        # Assert
        targets = relationship.GetTargets()
        self.assertEqual(len(targets), 0, "Read-only should not modify USD")
        self.assertTrue(model.read_only, "Should report as read-only")

    async def test_mixed_values_when_multiple_relationships_differ(self):
        """Arrange: 2 rels with different targets, Act: Create model, Assert: is_mixed True."""
        # Arrange
        prim1 = self.stage.DefinePrim("/Prim1")
        rel1 = prim1.CreateRelationship("rel")
        rel1.SetTargets([Sdf.Path("/Target1")])

        prim2 = self.stage.DefinePrim("/Prim2")
        rel2 = prim2.CreateRelationship("rel")
        rel2.SetTargets([Sdf.Path("/Target2")])

        # Act
        model = UsdRelationshipValueModel(
            context_name="",
            relationship_paths=[Sdf.Path("/Prim1.rel"), Sdf.Path("/Prim2.rel")],
            read_only=False,
        )

        # Assert
        self.assertTrue(model.is_mixed, "Should detect mixed values")
        self.assertEqual(model.get_value_as_string(), "<Mixed>", "Should display <Mixed>")

    async def test_not_mixed_when_all_relationships_match(self):
        """Arrange: 2 rels with same target, Act: Create model, Assert: is_mixed False."""
        # Arrange
        prim1 = self.stage.DefinePrim("/Prim1")
        rel1 = prim1.CreateRelationship("rel")
        rel1.SetTargets([Sdf.Path("/SameTarget")])

        prim2 = self.stage.DefinePrim("/Prim2")
        rel2 = prim2.CreateRelationship("rel")
        rel2.SetTargets([Sdf.Path("/SameTarget")])

        # Act
        model = UsdRelationshipValueModel(
            context_name="",
            relationship_paths=[Sdf.Path("/Prim1.rel"), Sdf.Path("/Prim2.rel")],
            read_only=False,
        )

        # Assert
        self.assertFalse(model.is_mixed, "Should not be mixed when values match")
        self.assertEqual(model.get_value(), "/SameTarget", "Should return common value")

    async def test_set_value_updates_all_relationships_in_multiselect(self):
        """Arrange: 2 rels, Act: Set value, Assert: Both updated."""
        # Arrange
        prim1 = self.stage.DefinePrim("/Prim1")
        rel1 = prim1.CreateRelationship("rel")

        prim2 = self.stage.DefinePrim("/Prim2")
        rel2 = prim2.CreateRelationship("rel")

        model = UsdRelationshipValueModel(
            context_name="",
            relationship_paths=[Sdf.Path("/Prim1.rel"), Sdf.Path("/Prim2.rel")],
            read_only=False,
        )

        # Act
        model.set_value("/NewTarget")
        await omni.kit.app.get_app().next_update_async()

        # Assert
        targets1 = rel1.GetTargets()
        targets2 = rel2.GetTargets()
        self.assertEqual(len(targets1), 1, "First rel should have target")
        self.assertEqual(len(targets2), 1, "Second rel should have target")
        self.assertEqual(str(targets1[0]), "/NewTarget", "First target should match")
        self.assertEqual(str(targets2[0]), "/NewTarget", "Second target should match")

    async def test_set_value_multiple_times_updates_correctly(self):
        """Arrange: Create model, Act: Set value twice, Assert: Second value persists."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        relationship = prim.CreateRelationship("testRel")

        model = UsdRelationshipValueModel(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            read_only=False,
        )

        # Act - set first value
        model.set_value("/Target1")
        await omni.kit.app.get_app().next_update_async()

        # Act - set second value
        model.set_value("/Target2")
        await omni.kit.app.get_app().next_update_async()

        # Assert
        targets = relationship.GetTargets()
        self.assertEqual(len(targets), 1, "Should have one target")
        self.assertEqual(str(targets[0]), "/Target2", "Should have latest target")
        self.assertEqual(model.get_value(), "/Target2", "Model should reflect latest value")

    async def test_get_value_as_bool_returns_true_when_target_set(self):
        """Arrange: Set target, Act: Get as bool, Assert: Returns True."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        prim.CreateRelationship("testRel")

        model = UsdRelationshipValueModel(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            read_only=False,
        )

        # Act
        model.set_value("/Target")
        result = model.get_value_as_bool()

        # Assert
        self.assertTrue(result, "Should return True when target is set")

    async def test_get_value_as_bool_returns_false_when_empty(self):
        """Arrange: Empty relationship, Act: Get as bool, Assert: Returns False."""
        # Arrange
        prim = self.stage.DefinePrim("/TestPrim")
        prim.CreateRelationship("testRel")

        model = UsdRelationshipValueModel(
            context_name="",
            relationship_paths=[Sdf.Path("/TestPrim.testRel")],
            read_only=False,
        )

        # Act
        result = model.get_value_as_bool()

        # Assert
        self.assertFalse(result, "Should return False when empty")
