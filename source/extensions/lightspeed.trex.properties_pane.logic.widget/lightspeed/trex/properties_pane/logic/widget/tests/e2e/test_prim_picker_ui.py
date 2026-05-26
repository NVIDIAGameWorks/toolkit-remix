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
import omni.ui as ui
import omni.usd
from lightspeed.trex.properties_pane.logic.widget import LogicPropertyWidget
from omni.flux.property_widget_builder.model.usd import USDRelationshipItem
from omni.flux.utils.common.interactive_usd_notices import register_objects_changed_listener as _register_listener
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows
from pxr import Sdf


class TestLogicWidgetUIComplete(omni.kit.test.AsyncTestCase):
    """Complete UI interaction tests for Logic Widget."""

    async def setUp(self):
        await arrange_windows()
        self._test_widget = None
        self._test_window = None
        context = omni.usd.get_context()
        await context.new_stage_async()

    async def tearDown(self):
        if self._test_widget is not None:
            self._test_widget.destroy()
            self._test_widget = None
            await ui_test.wait_n_updates(1)
        if self._test_window is not None:
            self._test_window.destroy()
            self._test_window = None
        context = omni.usd.get_context()
        await context.close_stage_async()

    async def test_complete_ui_workflow_click_picker_select_mesh_save_reload(self):
        """
        COMPLETE UI TEST:
        Arrange: Render widget with OmniGraph node
        Act: Click picker, select mesh from dropdown, save, reload
        Assert: Relationship set in USD, saved to file, persists after reload
        """
        # Arrange
        context = omni.usd.get_context()
        stage = context.get_stage()

        stage.DefinePrim("/World/Mesh1", "Mesh")
        stage.DefinePrim("/World/Mesh2", "Mesh")

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
        await omni.kit.app.get_app().next_update_async()

        # Create UI with proper sizing
        window = ui.Window("TestLogicWidgetUI", height=600, width=400)
        self._test_window = window
        with window.frame:
            with ui.Frame(width=400, height=600):
                widget = LogicPropertyWidget("")
                self._test_widget = widget
                widget.show(True)

        await ui_test.human_delay()

        # Refresh widget
        node_prim = stage.GetPrimAtPath(node.get_prim_path())
        widget.refresh([node_prim])

        # Wait for async refresh and frame rebuild
        await omni.kit.app.get_app().next_update_async()
        await omni.kit.app.get_app().next_update_async()
        await ui_test.human_delay(human_delay_speed=5)

        # Verify relationship item was created
        items = widget.property_model.get_all_items()
        relationship_items = [item for item in items if isinstance(item, USDRelationshipItem)]
        self.assertGreater(len(relationship_items), 0, "Widget should create USDRelationshipItem")

        # Groups are expanded by default (ItemGroup.expanded=True in setup_ui.py)
        await ui_test.human_delay(human_delay_speed=3)

        # Find the visible picker field before opening the real dropdown.
        picker_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].name=='StagePrimPickerField'")
        self.assertIsNotNone(picker_field, "StagePrimPickerField must render in UI")

        async def select_target(prim_path):
            await picker_field.click()
            await ui_test.wait_n_updates(1)
            dropdown_id = "StagePrimPickerDropdown_prim_picker_0"
            search_field = ui_test.find(f"{dropdown_id}//Frame/**/StringField[*].name=='StagePrimPickerSearch'")
            self.assertIsNotNone(search_field, "StagePrimPickerSearch must render in dropdown")
            await search_field.click()
            await search_field.input(prim_path.split("/")[-1])

            prim_button = None
            for _ in range(20):
                await ui_test.human_delay(human_delay_speed=1)
                prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Label[*]")
                prim_button = next(
                    (
                        button
                        for button in prim_buttons
                        if button.widget.text == prim_path
                        or (button.widget.tooltip and button.widget.tooltip.endswith(prim_path))
                    ),
                    None,
                )
                if prim_button is not None:
                    break
            self.assertIsNotNone(prim_button, f"{prim_path} must be selectable in dropdown")
            await prim_button.click()
            await ui_test.wait_n_updates(1)

        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "ui_test.usda"
            notices = []
            subscription = _register_listener(stage, lambda notice, stage: notices.append((notice, stage)))
            notice_counts_when_value_changed = []
            relationship_items[0].value_models[0].add_value_changed_fn(
                lambda _: notice_counts_when_value_changed.append(len(notices))
            )
            try:
                # Choose a target through the real picker dropdown so the UI write path runs.
                await select_target("/World/Mesh1")

                # The relationship updates immediately, but the refresh notice waits for the picker dropdown to close.
                relationship = node_prim.GetRelationship("inputs:target")
                targets = relationship.GetTargets()
                self.assertEqual(len(targets), 1, "Should have one target set")
                self.assertEqual(str(targets[0]), "/World/Mesh1", "Target should be /World/Mesh1")
                self.assertTrue(notice_counts_when_value_changed)
                self.assertEqual(notice_counts_when_value_changed[0], 0)
                for _ in range(20):
                    if len(notices) >= 1:
                        break
                    await ui_test.human_delay(human_delay_speed=1)
                self.assertEqual(len(notices), 1)

                # Save the selected relationship before clearing it through the UI.
                stage.GetRootLayer().Export(str(test_file))

                clear_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='StagePrimPickerClear'")
                self.assertIsNotNone(clear_button, "StagePrimPickerClear must render after selection")
                await clear_button.click()
                for _ in range(20):
                    if len(notices) >= 2:
                        break
                    await ui_test.human_delay(human_delay_speed=1)
                self.assertEqual(relationship.GetTargets(), [])
                self.assertEqual(len(notices), 2)
            finally:
                subscription.Revoke()

            # The exported layer keeps the selected target.
            usda_content = test_file.read_text()
            self.assertIn("inputs:target = </World/Mesh1>", usda_content)

            # Destroy the first widget and reload the saved layer to check persistence.
            widget.destroy()
            self._test_widget = None
            await ui_test.wait_n_updates(1)

            window.destroy()
            self._test_window = None

            await context.close_stage_async()
            await context.open_stage_async(str(test_file))

            # The reloaded relationship still points at the selected prim.
            loaded_stage = context.get_stage()
            loaded_node = loaded_stage.GetPrimAtPath(node.get_prim_path())
            loaded_rel = loaded_node.GetRelationship("inputs:target")
            loaded_targets = loaded_rel.GetTargets()

            self.assertEqual(str(loaded_targets[0]), "/World/Mesh1", "Should persist")

    async def test_ui_creates_relationship_item_and_renders_picker(self):
        """
        Arrange: Widget with MeshProximity node
        Act: Refresh widget
        Assert: USDRelationshipItem created, StagePrimPickerField renders
        """
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
        window = ui.Window("TestUI", height=600, width=400)
        with window.frame:
            with ui.Frame(width=400, height=600):
                widget = LogicPropertyWidget("")
                widget.show(True)

        node_prim = stage.GetPrimAtPath(node.get_prim_path())

        # Act
        widget.refresh([node_prim])
        await omni.kit.app.get_app().next_update_async()
        await omni.kit.app.get_app().next_update_async()
        await ui_test.human_delay(human_delay_speed=5)

        items = widget.property_model.get_all_items()

        # Groups are expanded by default (ItemGroup.expanded=True in setup_ui.py)
        await ui_test.human_delay(human_delay_speed=3)

        # Assert
        relationship_items = [item for item in items if isinstance(item, USDRelationshipItem)]
        picker_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].name=='StagePrimPickerField'")

        self.assertEqual(len(relationship_items), 1)
        self.assertIsNotNone(picker_field)

        widget.destroy()
        window.destroy()

    async def test_ui_multiselect_different_targets_shows_mixed(self):
        """
        Arrange: 2 nodes with different targets
        Act: Multi-select both nodes
        Assert: Picker shows <Mixed>
        """
        # Arrange
        context = omni.usd.get_context()
        stage = context.get_stage()
        controller = og.Controller(undoable=False)
        _, (node1, node2), _, _ = controller.edit(
            "/World/LogicGraph",
            {
                og.Controller.Keys.CREATE_NODES: [
                    ("Node1", "lightspeed.trex.logic.MeshProximity"),
                    ("Node2", "lightspeed.trex.logic.MeshProximity"),
                ],
            },
        )
        await controller.evaluate()

        node1_prim = stage.GetPrimAtPath(node1.get_prim_path())
        node1_prim.GetRelationship("inputs:target").SetTargets([Sdf.Path("/World/Mesh1")])

        node2_prim = stage.GetPrimAtPath(node2.get_prim_path())
        node2_prim.GetRelationship("inputs:target").SetTargets([Sdf.Path("/World/Mesh2")])

        window = ui.Window("TestUI", height=600, width=400)
        with window.frame:
            with ui.Frame(width=400, height=600):
                widget = LogicPropertyWidget("")
                widget.show(True)
        # Act
        widget.refresh([node1_prim, node2_prim])
        await omni.kit.app.get_app().next_update_async()
        await omni.kit.app.get_app().next_update_async()
        await ui_test.human_delay(human_delay_speed=5)

        items = widget.property_model.get_all_items()

        # Groups are expanded by default (ItemGroup.expanded=True in setup_ui.py)
        await ui_test.human_delay(human_delay_speed=3)

        relationship_items = [item for item in items if isinstance(item, USDRelationshipItem)]
        picker_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].name=='StagePrimPickerField'")

        # Assert
        self.assertIsNotNone(picker_field)
        self.assertEqual(relationship_items[0].value_models[0].get_value_as_string(), "<Mixed>")

        widget.destroy()
        window.destroy()

    async def test_ui_multiselect_set_value_updates_both_nodes(self):
        """
        Arrange: 2 nodes, multi-select
        Act: Set common target via value model
        Assert: Both USD relationships updated
        """
        # Arrange
        context = omni.usd.get_context()
        stage = context.get_stage()
        stage.DefinePrim("/World/CommonMesh", "Mesh")
        controller = og.Controller(undoable=False)
        _, (node1, node2), _, _ = controller.edit(
            "/World/LogicGraph",
            {
                og.Controller.Keys.CREATE_NODES: [
                    ("Node1", "lightspeed.trex.logic.MeshProximity"),
                    ("Node2", "lightspeed.trex.logic.MeshProximity"),
                ],
            },
        )
        await controller.evaluate()
        window = ui.Window("TestUI", height=600, width=400)
        with window.frame:
            with ui.Frame(width=400, height=600):
                widget = LogicPropertyWidget("")
                widget.show(True)

        node1_prim = stage.GetPrimAtPath(node1.get_prim_path())
        node2_prim = stage.GetPrimAtPath(node2.get_prim_path())

        widget.refresh([node1_prim, node2_prim])
        await omni.kit.app.get_app().next_update_async()
        await omni.kit.app.get_app().next_update_async()
        await ui_test.human_delay(human_delay_speed=5)

        items = widget.property_model.get_all_items()
        relationship_items = [item for item in items if isinstance(item, USDRelationshipItem)]

        # Act
        relationship_items[0].value_models[0].set_value("/World/CommonMesh")
        await omni.kit.app.get_app().next_update_async()

        # Assert
        targets1 = node1_prim.GetRelationship("inputs:target").GetTargets()
        targets2 = node2_prim.GetRelationship("inputs:target").GetTargets()

        self.assertEqual(str(targets1[0]), "/World/CommonMesh")
        self.assertEqual(str(targets2[0]), "/World/CommonMesh")

        widget.destroy()
        window.destroy()

    async def test_ui_set_target_and_verify_persistence(self):
        """
        Arrange: Widget with node
        Act: Set target, save, reload
        Assert: Target persists correctly
        """
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
        window = ui.Window("TestUI", height=600, width=400)
        with window.frame:
            with ui.Frame(width=400, height=600):
                widget = LogicPropertyWidget("")
                widget.show(True)
        node_prim = stage.GetPrimAtPath(node.get_prim_path())
        widget.refresh([node_prim])
        await omni.kit.app.get_app().next_update_async()
        await omni.kit.app.get_app().next_update_async()
        await ui_test.human_delay(human_delay_speed=5)

        items = widget.property_model.get_all_items()
        relationship_items = [item for item in items if isinstance(item, USDRelationshipItem)]

        # Act
        relationship_items[0].value_models[0].set_value("/World/TestMesh")
        await omni.kit.app.get_app().next_update_async()

        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "persist_test.usda"
            stage.GetRootLayer().Export(str(test_file))

            widget.destroy()
            await omni.kit.app.get_app().next_update_async()
            window.destroy()

            await context.close_stage_async()
            await context.open_stage_async(str(test_file))

            loaded_stage = context.get_stage()
            loaded_node = loaded_stage.GetPrimAtPath(node.get_prim_path())
            loaded_targets = loaded_node.GetRelationship("inputs:target").GetTargets()

        # Assert
        self.assertEqual(str(loaded_targets[0]), "/World/TestMesh")
