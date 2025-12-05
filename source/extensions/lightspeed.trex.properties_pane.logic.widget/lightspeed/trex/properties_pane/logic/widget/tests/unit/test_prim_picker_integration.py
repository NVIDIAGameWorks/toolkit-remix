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

import tempfile
from pathlib import Path

import omni.graph.core as og
import omni.kit.test
import omni.usd
from lightspeed.trex.properties_pane.logic.widget import LogicPropertyWidget
from omni.flux.property_widget_builder.model.usd import USDRelationshipItem
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows
from pxr import Sdf


class TestLogicWidgetIntegration(omni.kit.test.AsyncTestCase):
    """
    Integration tests for Logic Widget with USD relationships.

    Tests the component integration without complex UI interactions.
    """

    async def setUp(self):
        await arrange_windows()
        context = omni.usd.get_context()
        await context.new_stage_async()

    async def tearDown(self):
        context = omni.usd.get_context()
        await context.close_stage_async()

    async def test_widget_creates_relationship_item_for_target(self):
        """Arrange: MeshProximity node, Act: Refresh widget, Assert: Creates USDRelationshipItem."""
        # Arrange
        context = omni.usd.get_context()
        stage = context.get_stage()

        controller = og.Controller(undoable=False)
        _, (node,), _, _ = controller.edit(
            "/World/LogicGraph",
            {
                og.Controller.Keys.CREATE_NODES: [
                    ("MeshProximity", "lightspeed.trex.logic.MeshProximity"),
                ],
            },
        )
        await controller.evaluate()

        widget = LogicPropertyWidget("")
        node_prim = stage.GetPrimAtPath(node.get_prim_path())

        # Act
        widget.refresh([node_prim])
        await ui_test.human_delay(human_delay_speed=10)
        items = widget.property_model.get_all_items()

        # Assert
        relationship_items = [item for item in items if isinstance(item, USDRelationshipItem)]
        target_items = [
            item
            for item in relationship_items
            if any("Target" in str(nm.get_value_as_string()) for nm in item.name_models)
        ]

        self.assertEqual(len(target_items), 1)

        widget.destroy()

    async def test_relationship_item_value_model_sets_usd_relationship(self):
        """Arrange: Widget with node, Act: Set via value model, Assert: USD updated."""
        # Arrange
        context = omni.usd.get_context()
        stage = context.get_stage()
        stage.DefinePrim("/World/TestMesh", "Mesh")

        controller = og.Controller(undoable=False)
        _, (node,), _, _ = controller.edit(
            "/World/LogicGraph",
            {
                og.Controller.Keys.CREATE_NODES: [
                    ("MeshProximity", "lightspeed.trex.logic.MeshProximity"),
                ],
            },
        )
        await controller.evaluate()

        widget = LogicPropertyWidget("")
        node_prim = stage.GetPrimAtPath(node.get_prim_path())
        widget.refresh([node_prim])
        await ui_test.human_delay(human_delay_speed=10)

        items = widget.property_model.get_all_items()
        relationship_items = [item for item in items if isinstance(item, USDRelationshipItem)]

        # Act
        relationship_items[0].value_models[0].set_value("/World/TestMesh")
        await omni.kit.app.get_app().next_update_async()

        # Assert
        relationship = node_prim.GetRelationship("inputs:target")
        targets = relationship.GetTargets()
        self.assertEqual(str(targets[0]), "/World/TestMesh")

        widget.destroy()

    async def test_relationship_target_persists_across_save_reload(self):
        """Arrange: Set target, Act: Save and reload, Assert: Target persists."""
        # Arrange
        context = omni.usd.get_context()
        stage = context.get_stage()
        stage.DefinePrim("/World/SavedMesh", "Mesh")

        controller = og.Controller(undoable=False)
        _, (node,), _, _ = controller.edit(
            "/World/LogicGraph",
            {
                og.Controller.Keys.CREATE_NODES: [
                    ("MeshProximity", "lightspeed.trex.logic.MeshProximity"),
                ],
            },
        )
        await controller.evaluate()

        widget = LogicPropertyWidget("")
        node_prim = stage.GetPrimAtPath(node.get_prim_path())
        widget.refresh([node_prim])
        await ui_test.human_delay(human_delay_speed=10)

        items = widget.property_model.get_all_items()
        relationship_items = [item for item in items if isinstance(item, USDRelationshipItem)]

        # Act - set target
        relationship_items[0].value_models[0].set_value("/World/SavedMesh")
        await omni.kit.app.get_app().next_update_async()

        # Act - save and reload
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "persist_test.usda"
            stage.GetRootLayer().Export(str(test_file))

            widget.destroy()
            await context.close_stage_async()
            await context.open_stage_async(str(test_file))

            # Assert
            loaded_stage = context.get_stage()
            loaded_node = loaded_stage.GetPrimAtPath(node.get_prim_path())
            loaded_rel = loaded_node.GetRelationship("inputs:target")

            loaded_targets = loaded_rel.GetTargets()
            self.assertEqual(len(loaded_targets), 1, "Target should persist")
            self.assertEqual(str(loaded_targets[0]), "/World/SavedMesh", "Persisted target should be /World/SavedMesh")

    async def test_multiselect_with_different_targets_shows_mixed(self):
        """Arrange: 2 nodes different targets, Act: Multi-select, Assert: Value model shows mixed."""
        # Arrange
        context = omni.usd.get_context()
        stage = context.get_stage()

        controller = og.Controller(undoable=False)
        _, (node1, node2), _, _ = controller.edit(
            "/World/LogicGraph",
            {
                og.Controller.Keys.CREATE_NODES: [
                    ("MeshProx1", "lightspeed.trex.logic.MeshProximity"),
                    ("MeshProx2", "lightspeed.trex.logic.MeshProximity"),
                ],
            },
        )
        await controller.evaluate()

        node1_prim = stage.GetPrimAtPath(node1.get_prim_path())
        node1_prim.GetRelationship("inputs:target").SetTargets([Sdf.Path("/World/Mesh1")])

        node2_prim = stage.GetPrimAtPath(node2.get_prim_path())
        node2_prim.GetRelationship("inputs:target").SetTargets([Sdf.Path("/World/Mesh2")])

        widget = LogicPropertyWidget("")

        # Act
        widget.refresh([node1_prim, node2_prim])
        await ui_test.human_delay(human_delay_speed=10)
        items = widget.property_model.get_all_items()
        relationship_items = [item for item in items if isinstance(item, USDRelationshipItem)]

        # Assert
        value_model = relationship_items[0].value_models[0]
        self.assertEqual(value_model.get_value_as_string(), "<Mixed>")

        widget.destroy()

    async def test_multiselect_set_value_updates_all_relationships(self):
        """Arrange: Multi-select 2 nodes, Act: Set value, Assert: Both USD relationships updated."""
        # Arrange
        context = omni.usd.get_context()
        stage = context.get_stage()
        stage.DefinePrim("/World/CommonTarget", "Mesh")

        controller = og.Controller(undoable=False)
        _, (node1, node2), _, _ = controller.edit(
            "/World/LogicGraph",
            {
                og.Controller.Keys.CREATE_NODES: [
                    ("MeshProx1", "lightspeed.trex.logic.MeshProximity"),
                    ("MeshProx2", "lightspeed.trex.logic.MeshProximity"),
                ],
            },
        )
        await controller.evaluate()

        widget = LogicPropertyWidget("")
        node1_prim = stage.GetPrimAtPath(node1.get_prim_path())
        node2_prim = stage.GetPrimAtPath(node2.get_prim_path())

        widget.refresh([node1_prim, node2_prim])
        await ui_test.human_delay(human_delay_speed=10)

        items = widget.property_model.get_all_items()
        relationship_items = [item for item in items if isinstance(item, USDRelationshipItem)]

        # Act
        relationship_items[0].value_models[0].set_value("/World/CommonTarget")
        await omni.kit.app.get_app().next_update_async()

        # Assert
        targets1 = node1_prim.GetRelationship("inputs:target").GetTargets()
        targets2 = node2_prim.GetRelationship("inputs:target").GetTargets()
        self.assertEqual(str(targets1[0]), "/World/CommonTarget")
        self.assertEqual(str(targets2[0]), "/World/CommonTarget")

        widget.destroy()
