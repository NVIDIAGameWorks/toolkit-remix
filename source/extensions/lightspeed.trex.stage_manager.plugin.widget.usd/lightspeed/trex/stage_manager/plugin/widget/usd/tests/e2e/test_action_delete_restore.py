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

__all__ = ["TestDeleteRestoreActionWidgetPlugin"]

from tempfile import TemporaryDirectory

import omni.graph.core as og
from lightspeed.trex.stage_manager.plugin.widget.usd.action_delete_restore import DeleteRestoreActionWidgetPlugin
from omni import client, ui, usd
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.widget.resources import get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows
from pxr import Sdf, Usd


class TestDeleteRestoreActionWidgetPlugin(AsyncTestCase):
    _restore_identifier = "delete_restore_widget_restore"
    _restore_disabled_identifier = "delete_restore_widget_restore_disabled"
    _delete_identifier = "delete_restore_widget_delete"
    _delete_capture_identifier = "delete_restore_widget_delete_capture"

    async def setUp(self):
        await arrange_windows()
        self.temp_dir = TemporaryDirectory()
        self._test_window = None
        self._test_widget = None

        await self._open_test_project()
        self.stage = usd.get_context().get_stage()

    async def tearDown(self):
        self._test_widget = None
        if self._test_window is not None:
            self._test_window.destroy()
            self._test_window = None

        if usd.get_context().get_stage():
            await usd.get_context().close_stage_async()

        self.temp_dir.cleanup()
        self.temp_dir = None
        self.stage = None

    async def _open_test_project(self):
        project_path = OmniUrl(get_test_data("usd/project_example/combined.usda"))
        temp_path = OmniUrl(self.temp_dir.name) / OmniUrl(project_path.parent_url).stem
        temp_project = temp_path / project_path.name

        result = await client.copy_async(project_path.parent_url, temp_path.path)
        if result != client.Result.OK:
            raise OSError(f"Can't copy the project path to the temporary directory: {result}")

        await usd.get_context().open_stage_async(temp_project.path)

    async def _setup_widget(self, widget_plugin_type: type[DeleteRestoreActionWidgetPlugin]):
        window = ui.Window("TestWidgetPluginsWindow", width=200, height=100)
        with window.frame:
            widget = widget_plugin_type()

        self._test_window = window
        self._test_widget = widget
        return window, widget

    async def _create_graph_at_prim(self, graph_path: Sdf.Path) -> bool:
        graph = og.get_global_orchestration_graphs()[0]
        success, _ = og.cmds.CreateGraphAsNode(
            graph=graph,
            node_name=graph_path.name,
            graph_path=graph_path.pathString,
            evaluator_name="component",
            is_global_graph=True,
            backed_by_usd=True,
            fc_backing_type=og.GraphBackingType.GRAPH_BACKING_TYPE_FLATCACHE_SHARED,
            pipeline_stage=og.GraphPipelineStage.GRAPH_PIPELINE_STAGE_SIMULATION,
        )
        return success

    def _find_replacement_layer(self):
        for layer_path in self.stage.GetRootLayer().subLayerPaths:
            layer = Sdf.Layer.FindRelativeToLayer(self.stage.GetRootLayer(), layer_path)
            if layer and layer.customLayerData.get("lightspeed_layer_type") == "replacement":
                return layer
        return None

    def _set_edit_target_to_replacement(self):
        """Set the stage edit target to the replacement layer, matching the real app's authoring_layer behavior."""
        replacement = self._find_replacement_layer()
        self.assertIsNotNone(replacement)
        self.stage.SetEditTarget(Usd.EditTarget(replacement))

    # ------------------------------------------------------------------
    # State classification tests
    # ------------------------------------------------------------------

    async def test_delete_capture_action_type(self):
        """Capture prim without replacement-layer overrides is classified as DELETECAPTURE."""
        # Arrange
        prim = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_0AB745B8BEE1F16B")
        self.assertTrue(prim.IsValid())
        _, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)

        # Act
        action_type = widget._get_prim_action_type(prim)

        # Assert
        self.assertEqual(action_type, widget.ActionType.DELETECAPTURE)

    async def test_restore_disabled_action_type_for_protected_path(self):
        """Protected paths are classified as RESTOREDISABLED."""
        # Arrange
        prim = self.stage.GetPrimAtPath("/RootNode/meshes")
        self.assertTrue(prim.IsValid())
        _, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)

        # Act
        action_type = widget._get_prim_action_type(prim)

        # Assert
        self.assertEqual(action_type, widget.ActionType.RESTOREDISABLED)

    async def test_restore_disabled_action_type_for_composition_only_prim(self):
        """Non-capture prims with no spec in edit target or replacement layers
        are classified as RESTOREDISABLED."""
        # Arrange
        composition_layer = Sdf.Layer.CreateAnonymous()
        self.stage.GetRootLayer().subLayerPaths.append(composition_layer.identifier)
        test_prim_path = "/RootNode/meshes/test_composition_only_prim"
        prim_spec = Sdf.CreatePrimInLayer(composition_layer, test_prim_path)
        prim_spec.specifier = Sdf.SpecifierDef
        prim_spec.typeName = "Xform"
        prim = self.stage.GetPrimAtPath(test_prim_path)
        self.assertTrue(prim.IsValid())
        _, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)

        # Act
        action_type = widget._get_prim_action_type(prim)

        # Assert
        self.assertEqual(action_type, widget.ActionType.RESTOREDISABLED)

    async def test_restore_action_type_for_capture_prim_with_replacement_ref_edits(self):
        """Capture prim whose capture refs were deleted is classified as RESTORE."""
        # Arrange — delete the capture reference via the widget callback so that
        # SetExplicitReferencesCommand properly authors an explicit empty ref list
        # on the replacement layer through Kit's command pipeline.
        test_prim_path = "/RootNode/meshes/mesh_0AB745B8BEE1F16B"
        prim = self.stage.GetPrimAtPath(test_prim_path)
        self.assertTrue(prim.IsValid())  # Guard: prim must exist in test project
        _, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)
        self.assertEqual(
            widget._get_prim_action_type(prim), widget.ActionType.DELETECAPTURE
        )  # Guard: starts as DELETECAPTURE
        self._set_edit_target_to_replacement()
        usd.get_context().get_selection().set_selected_prim_paths([test_prim_path], False)
        widget._delete_capture_prim_cb()
        self.assertEqual(len(usd.get_composed_references_from_prim(prim, False)), 0)  # Guard: refs removed by callback

        # Act
        action_type = widget._get_prim_action_type(prim)

        # Assert
        self.assertEqual(action_type, widget.ActionType.RESTORE)

    async def test_delete_action_type_for_instance_path(self):
        """Instance paths resolve to their prototype and are classified as DELETE."""
        # Arrange
        mesh_path = Sdf.Path("/RootNode/meshes/mesh_CED45075A077A49A")
        graph_path = mesh_path.AppendChild("RemixLogicGraph")
        instance_graph_path = "/RootNode/instances/inst_CED45075A077A49A_0/RemixLogicGraph"
        success = await self._create_graph_at_prim(graph_path)
        self.assertTrue(success)
        instance_prim = self.stage.GetPrimAtPath(instance_graph_path)
        self.assertTrue(instance_prim.IsValid())
        _, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)

        # Act
        action_type = widget._get_prim_action_type(instance_prim)

        # Assert
        self.assertEqual(action_type, widget.ActionType.DELETE)

    # ------------------------------------------------------------------
    # UI rendering tests
    # ------------------------------------------------------------------

    async def test_delete_capture_widget_renders_trash_can(self):
        """DELETECAPTURE prim renders an enabled TrashCan icon."""
        # Arrange
        prim = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_0AB745B8BEE1F16B")
        self.assertTrue(prim.IsValid())
        window, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)
        item = StageManagerTreeItem(display_name=prim.GetName(), tooltip="foobar", data=prim)

        # Act
        with window.frame:
            widget.build_icon_ui(StageManagerTreeModel(), item, 1, True)

        # Assert
        id_check = ui_test.find(f"{window.title}//Frame/Image[*].identifier=='{self._delete_capture_identifier}'")
        self.assertIsNotNone(id_check)
        self.assertTrue(id_check.widget.enabled)
        self.assertEqual(id_check.widget.name, "TrashCan")
        self.assertEqual(id_check.widget.tooltip, "Delete Capture Prim")

    async def test_restore_disabled_widget_renders_disabled_restore(self):
        """RESTOREDISABLED prim renders a disabled Restore icon."""
        # Arrange
        prim = self.stage.GetPrimAtPath("/RootNode/meshes")
        self.assertTrue(prim.IsValid())
        window, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)
        item = StageManagerTreeItem(display_name=prim.GetName(), tooltip="foobar", data=prim)

        # Act
        with window.frame:
            widget.build_icon_ui(StageManagerTreeModel(), item, 1, True)

        # Assert
        id_check = ui_test.find(f"{window.title}//Frame/Image[*].identifier=='{self._restore_disabled_identifier}'")
        self.assertIsNotNone(id_check)
        self.assertFalse(id_check.widget.enabled)
        self.assertEqual(id_check.widget.name, "Restore")
        self.assertEqual(id_check.widget.tooltip, "The prim cannot be restored")

    async def test_restore_widget_renders_restore_icon(self):
        """Capture prim whose capture refs were deleted renders a Restore icon."""
        # Arrange — delete capture ref via the widget so the command pipeline
        # authors a proper explicit empty ref list on the replacement layer.
        test_prim_path = "/RootNode/meshes/mesh_0AB745B8BEE1F16B"
        prim = self.stage.GetPrimAtPath(test_prim_path)
        self.assertTrue(prim.IsValid())  # Guard: prim must exist in test project
        window, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)
        self._set_edit_target_to_replacement()
        usd.get_context().get_selection().set_selected_prim_paths([test_prim_path], False)
        widget._delete_capture_prim_cb()
        self.assertEqual(len(usd.get_composed_references_from_prim(prim, False)), 0)  # Guard: refs removed by callback
        item = StageManagerTreeItem(display_name=prim.GetName(), tooltip="foobar", data=prim)

        # Act
        with window.frame:
            widget.build_icon_ui(StageManagerTreeModel(), item, 1, True)

        # Assert
        id_check = ui_test.find(f"{window.title}//Frame/Image[*].identifier=='{self._restore_identifier}'")
        self.assertIsNotNone(id_check)
        self.assertEqual(id_check.widget.name, "Restore")
        self.assertEqual(id_check.widget.tooltip, "Restore Prim To Capture State")

    async def test_delete_widget_renders_trash_can(self):
        """Non-capture prim with spec renders an enabled TrashCan icon."""
        # Arrange
        test_prim = Sdf.Path("/RootNode/meshes/mesh_CED45075A077A49A")
        graph_path = test_prim.AppendChild("RemixLogicGraph")
        success = await self._create_graph_at_prim(graph_path)
        self.assertTrue(success)
        graph_prim = self.stage.GetPrimAtPath(graph_path)
        self.assertTrue(graph_prim.IsValid())
        window, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)
        item = StageManagerTreeItem(display_name=graph_prim.GetName(), tooltip="foobar", data=graph_prim)

        # Act
        with window.frame:
            widget.build_icon_ui(StageManagerTreeModel(), item, 1, True)

        # Assert
        id_check = ui_test.find(f"{window.title}//Frame/Image[*].identifier=='{self._delete_identifier}'")
        self.assertIsNotNone(id_check)
        self.assertEqual(id_check.widget.name, "TrashCan")
        self.assertTrue(id_check.widget.enabled)
        self.assertEqual(id_check.widget.tooltip, "Delete the prim")

    # ------------------------------------------------------------------
    # Callback behavior tests
    # ------------------------------------------------------------------

    async def test_delete_via_instance_path(self):
        """Selecting an instance path deletes the prototype prim."""
        # Arrange
        mesh_path = Sdf.Path("/RootNode/meshes/mesh_CED45075A077A49A")
        graph_path = mesh_path.AppendChild("RemixLogicGraph")
        instance_graph_path = "/RootNode/instances/inst_CED45075A077A49A_0/RemixLogicGraph"
        success = await self._create_graph_at_prim(graph_path)
        self.assertTrue(success)
        self.assertTrue(self.stage.GetPrimAtPath(graph_path).IsValid())
        self.assertTrue(self.stage.GetPrimAtPath(instance_graph_path).IsValid())
        _, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)
        usd.get_context().get_selection().set_selected_prim_paths([instance_graph_path], False)

        # Act
        widget._delete_prim_cb()

        # Assert
        self.assertFalse(self.stage.GetPrimAtPath(graph_path).IsValid())
        self.assertFalse(self.stage.GetPrimAtPath(instance_graph_path).IsValid())

    async def test_restore_disabled_for_composition_only_prim(self):
        """Verify that non-capture prims with no spec in the edit target or any
        replacement layer (composition-only) are classified as RESTOREDISABLED."""
        stage = self.stage

        composition_layer = Sdf.Layer.CreateAnonymous()
        stage.GetRootLayer().subLayerPaths.append(composition_layer.identifier)

        test_prim_path = "/RootNode/meshes/test_composition_only_prim"
        prim_spec = Sdf.CreatePrimInLayer(composition_layer, test_prim_path)
        prim_spec.specifier = Sdf.SpecifierDef
        prim_spec.typeName = "Xform"

        prim = stage.GetPrimAtPath(test_prim_path)
        self.assertTrue(prim.IsValid())

        edit_target_layer = stage.GetEditTarget().GetLayer()
        self.assertIsNone(edit_target_layer.GetPrimAtPath(test_prim_path))

        window, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)

        self.assertEqual(
            widget._get_prim_action_type(prim),
            widget.ActionType.RESTOREDISABLED,
        )

        item = StageManagerTreeItem(display_name=prim.GetName(), tooltip="foobar", data=prim)

        with window.frame:
            widget.build_icon_ui(StageManagerTreeModel(), item, 1, True)

        id_check = ui_test.find(f"{window.title}//Frame/Image[*].identifier=='{self._restore_disabled_identifier}'")

        self.assertIsNotNone(id_check)
        self.assertFalse(id_check.widget.enabled)
        self.assertEqual(id_check.widget.name, "Restore")
        self.assertEqual(id_check.widget.tooltip, "The prim cannot be restored")

        widget = None
        window.destroy()

    async def test_delete_prim_in_both_local_and_ancestral(self):
        """Prim with specs in both edit target and replacement sublayer is fully deleted."""
        # Arrange
        replacement_layer = self._find_replacement_layer()
        self.assertIsNotNone(replacement_layer)
        sublayer = Sdf.Layer.CreateAnonymous()
        replacement_layer.subLayerPaths.append(sublayer.identifier)

        test_prim_path = "/RootNode/meshes/test_both_local_and_ancestral"
        ancestral_spec = Sdf.CreatePrimInLayer(sublayer, test_prim_path)
        ancestral_spec.specifier = Sdf.SpecifierDef
        ancestral_spec.typeName = "Xform"
        edit_target_layer = self.stage.GetEditTarget().GetLayer()
        local_spec = Sdf.CreatePrimInLayer(edit_target_layer, test_prim_path)
        local_spec.specifier = Sdf.SpecifierOver

        self.assertTrue(self.stage.GetPrimAtPath(test_prim_path).IsValid())
        _, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)
        usd.get_context().get_selection().set_selected_prim_paths([test_prim_path], False)

        # Act
        widget._delete_prim_cb()

        # Assert
        self.assertIsNone(edit_target_layer.GetPrimAtPath(test_prim_path))
        self.assertIsNone(sublayer.GetPrimAtPath(test_prim_path))
        self.assertFalse(self.stage.GetPrimAtPath(test_prim_path).IsValid())

    async def test_delete_ancestral_prim(self):
        """Prim with no spec in edit target is deleted from replacement sublayer."""
        # Arrange
        replacement_layer = self._find_replacement_layer()
        self.assertIsNotNone(replacement_layer)
        sublayer = Sdf.Layer.CreateAnonymous()
        replacement_layer.subLayerPaths.append(sublayer.identifier)

        test_prim_path = "/RootNode/meshes/test_ancestral_prim"
        prim_spec = Sdf.CreatePrimInLayer(sublayer, test_prim_path)
        prim_spec.specifier = Sdf.SpecifierDef
        prim_spec.typeName = "Xform"

        self.assertTrue(self.stage.GetPrimAtPath(test_prim_path).IsValid())
        self.assertIsNotNone(sublayer.GetPrimAtPath(test_prim_path))
        _, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)
        usd.get_context().get_selection().set_selected_prim_paths([test_prim_path], False)

        # Act
        widget._delete_prim_cb()

        # Assert
        self.assertIsNone(sublayer.GetPrimAtPath(test_prim_path))
        self.assertFalse(self.stage.GetPrimAtPath(test_prim_path).IsValid())

    async def test_delete_capture_prim_removes_reference(self):
        """Deleting a capture prim removes its reference."""
        # Arrange
        test_prim_path = "/RootNode/meshes/mesh_0AB745B8BEE1F16B"
        prim = self.stage.GetPrimAtPath(test_prim_path)
        self.assertTrue(prim.IsValid())
        self.assertTrue(len(usd.get_composed_references_from_prim(prim, False)) > 0)
        _, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)
        usd.get_context().get_selection().set_selected_prim_paths([test_prim_path], False)

        # Act
        widget._delete_capture_prim_cb()

        # Assert
        self.assertEqual(len(usd.get_composed_references_from_prim(prim, False)), 0)

    async def test_delete_ref_overrides_clears_replacement_references(self):
        """_delete_ref_overrides clears reference list edits but preserves attribute opinions."""
        # Arrange — delete the capture ref via the widget to author a proper
        # explicit empty ref list, then add a test attribute that should survive.
        test_prim_path = "/RootNode/meshes/mesh_0AB745B8BEE1F16B"
        _, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)
        self._set_edit_target_to_replacement()
        usd.get_context().get_selection().set_selected_prim_paths([test_prim_path], False)
        widget._delete_capture_prim_cb()
        replacement_layer = self._find_replacement_layer()
        self.assertIsNotNone(replacement_layer)  # Guard: replacement layer must exist
        prim_spec = replacement_layer.GetPrimAtPath(test_prim_path)
        self.assertIsNotNone(prim_spec)  # Guard: callback must have authored a spec on replacement layer
        self.assertTrue(prim_spec.hasReferences)  # Guard: explicit empty ref list is an authored opinion
        attr_spec = Sdf.AttributeSpec(prim_spec, "testPreservedAttr", Sdf.ValueTypeNames.Bool)
        attr_spec.default = True

        # Act
        widget._delete_ref_overrides()

        # Assert
        prim_spec = replacement_layer.GetPrimAtPath(test_prim_path)
        self.assertFalse(prim_spec.hasReferences)
        self.assertIsNotNone(prim_spec.attributes.get("testPreservedAttr"))

    async def test_show_restore_context_menu_creates_menu(self):
        """_show_restore_context_menu creates a context menu."""
        # Arrange
        _, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)

        # Act
        widget._show_restore_context_menu()

        # Assert
        self.assertIsNotNone(widget._restore_context_menu)
