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
from pxr import Sdf


class TestDeleteRestoreActionWidgetPlugin(AsyncTestCase):
    _restore_identifier = "delete_restore_widget_restore"
    _delete_identifier = "delete_restore_widget_delete"

    async def setUp(self):
        await arrange_windows()
        self.temp_dir = TemporaryDirectory()

        await self._open_test_project()
        self.stage = usd.get_context().get_stage()

    async def tearDown(self):
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

    async def test_restore_disabled_widget_action(self):
        test_prim = Sdf.Path("/RootNode/meshes/mesh_0AB745B8BEE1F16B")

        prim = self.stage.GetPrimAtPath(test_prim)
        self.assertTrue(prim.IsValid())

        window, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)
        item = StageManagerTreeItem(display_name=prim.GetName(), tooltip="foobar", data=prim)

        with window.frame:
            widget.build_icon_ui(StageManagerTreeModel(), item, 1, True)

        id_check = ui_test.find(f"{window.title}//Frame/Image[*].identifier=='{self._restore_identifier}'")

        self.assertIsNotNone(id_check)
        self.assertFalse(id_check.widget.enabled)
        self.assertEqual(id_check.widget.name, "Restore")
        self.assertEqual(id_check.widget.tooltip, "The Prim may not be restored")

        widget = None
        window.destroy()

    async def test_restore_disabled_for_protected_path(self):
        """Verify that protected paths (e.g. /RootNode/meshes) always get RESTOREDISABLED
        and render a disabled restore icon."""
        test_prim = Sdf.Path("/RootNode/meshes")

        prim = self.stage.GetPrimAtPath(test_prim)
        self.assertTrue(prim.IsValid())

        window, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)

        self.assertEqual(
            widget._get_prim_action_type(prim),
            widget.ActionType.RESTOREDISABLED,
        )

        item = StageManagerTreeItem(display_name=prim.GetName(), tooltip="foobar", data=prim)

        with window.frame:
            widget.build_icon_ui(StageManagerTreeModel(), item, 1, True)

        id_check = ui_test.find(f"{window.title}//Frame/Image[*].identifier=='{self._restore_identifier}'")

        self.assertIsNotNone(id_check)
        self.assertFalse(id_check.widget.enabled)
        self.assertEqual(id_check.widget.name, "Restore")
        self.assertEqual(id_check.widget.tooltip, "The Prim may not be restored")

        widget = None
        window.destroy()

    async def test_restore_widget_action(self):
        test_prim = Sdf.Path("/RootNode/meshes/mesh_BAC90CAA733B0859")
        prim = self.stage.GetPrimAtPath(test_prim)
        self.assertTrue(prim.IsValid())

        graph_path = test_prim.AppendChild("RemixLogicGraph")
        success = await self._create_graph_at_prim(graph_path)
        self.assertTrue(success)

        window, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)
        item = StageManagerTreeItem(display_name=prim.GetName(), tooltip="foobar", data=prim)

        with window.frame:
            widget.build_icon_ui(StageManagerTreeModel(), item, 1, True)

        id_check = ui_test.find(f"{window.title}//Frame/Image[*].identifier=='{self._restore_identifier}'")

        self.assertIsNotNone(id_check)
        self.assertEqual(id_check.widget.name, "Restore")
        self.assertEqual(id_check.widget.tooltip, "Restore Prim To Capture State")

        widget = None
        window.destroy()

    async def test_delete_widget_action(self):
        test_prim = Sdf.Path("/RootNode/meshes/mesh_CED45075A077A49A")
        graph_path = test_prim.AppendChild("RemixLogicGraph")
        prim = self.stage.GetPrimAtPath(test_prim)
        self.assertTrue(prim.IsValid())

        success = await self._create_graph_at_prim(graph_path)

        self.assertTrue(success)
        graph_prim = self.stage.GetPrimAtPath(graph_path)
        self.assertTrue(graph_prim.IsValid())

        window, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)

        item = StageManagerTreeItem(display_name=graph_prim.GetName(), tooltip="foobar", data=graph_prim)

        with window.frame:
            widget.build_icon_ui(StageManagerTreeModel(), item, 1, True)

        id_check = ui_test.find(f"{window.title}//Frame/Image[*].identifier=='{self._delete_identifier}'")

        self.assertIsNotNone(id_check)
        self.assertEqual(id_check.widget.name, "TrashCan")
        self.assertTrue(id_check.widget.enabled)
        self.assertEqual(id_check.widget.tooltip, "Delete Prim")

        widget = None
        window.destroy()

    async def test_delete_via_instance_path(self):
        """Verify that selecting an instance path correctly resolves to the prototype
        and deletes the prototype prim via _delete_prim_cb."""
        mesh_path = Sdf.Path("/RootNode/meshes/mesh_CED45075A077A49A")
        graph_path = mesh_path.AppendChild("RemixLogicGraph")
        instance_graph_path = "/RootNode/instances/inst_CED45075A077A49A_0/RemixLogicGraph"

        success = await self._create_graph_at_prim(graph_path)
        self.assertTrue(success)

        proto_prim = self.stage.GetPrimAtPath(graph_path)
        self.assertTrue(proto_prim.IsValid())
        instance_prim = self.stage.GetPrimAtPath(instance_graph_path)
        self.assertTrue(instance_prim.IsValid())

        window, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)

        self.assertEqual(
            widget._get_prim_action_type(instance_prim),
            widget.ActionType.DELETE,
        )

        usd.get_context().get_selection().set_selected_prim_paths([instance_graph_path], False)
        widget._delete_prim_cb()

        proto_prim = self.stage.GetPrimAtPath(graph_path)
        self.assertFalse(proto_prim.IsValid())
        instance_prim = self.stage.GetPrimAtPath(instance_graph_path)
        self.assertFalse(instance_prim.IsValid())

        widget = None
        window.destroy()

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

        id_check = ui_test.find(f"{window.title}//Frame/Image[*].identifier=='{self._restore_identifier}'")

        self.assertIsNotNone(id_check)
        self.assertFalse(id_check.widget.enabled)
        self.assertEqual(id_check.widget.name, "Restore")
        self.assertEqual(id_check.widget.tooltip, "The Prim may not be restored")

        widget = None
        window.destroy()

    async def test_delete_prim_in_both_local_and_ancestral(self):
        """Verify that a prim with specs in both the edit target (local) and a
        replacement sublayer (ancestral) is fully deleted from both layers when
        _delete_prim_cb is invoked."""
        stage = self.stage

        replacement_layer = None
        for layer_path in stage.GetRootLayer().subLayerPaths:
            layer = Sdf.Layer.FindRelativeToLayer(stage.GetRootLayer(), layer_path)
            if layer and layer.customLayerData.get("lightspeed_layer_type") == "replacement":
                replacement_layer = layer
                break
        self.assertIsNotNone(replacement_layer)

        sublayer = Sdf.Layer.CreateAnonymous()
        replacement_layer.subLayerPaths.append(sublayer.identifier)

        test_prim_path = "/RootNode/meshes/test_both_local_and_ancestral"
        ancestral_spec = Sdf.CreatePrimInLayer(sublayer, test_prim_path)
        ancestral_spec.specifier = Sdf.SpecifierDef
        ancestral_spec.typeName = "Xform"

        edit_target_layer = stage.GetEditTarget().GetLayer()
        local_spec = Sdf.CreatePrimInLayer(edit_target_layer, test_prim_path)
        local_spec.specifier = Sdf.SpecifierOver

        prim = stage.GetPrimAtPath(test_prim_path)
        self.assertTrue(prim.IsValid())

        window, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)

        self.assertEqual(
            widget._get_prim_action_type(prim),
            widget.ActionType.DELETE,
        )

        # Verify the prim satisfies both classification conditions in _delete_prim_cb,
        # meaning it will end up in both local_paths and ancestral_paths.
        rep_layers = widget._layer_manager.get_replacement_layers()
        self.assertIsNotNone(edit_target_layer.GetPrimAtPath(test_prim_path))
        self.assertTrue(any(layer.GetPrimAtPath(test_prim_path) for layer in rep_layers))

        usd.get_context().get_selection().set_selected_prim_paths([test_prim_path], False)
        widget._delete_prim_cb()

        self.assertIsNone(edit_target_layer.GetPrimAtPath(test_prim_path))
        self.assertIsNone(sublayer.GetPrimAtPath(test_prim_path))

        prim = stage.GetPrimAtPath(test_prim_path)
        self.assertFalse(prim.IsValid())

        widget = None
        window.destroy()

    async def test_delete_ancestral_prim(self):
        """Verify that prims with no spec in the edit target (ancestral) are deleted
        from the replacement sublayer where they are actually defined via the full
        _delete_prim_cb routing path."""
        stage = self.stage

        replacement_layer = None
        for layer_path in stage.GetRootLayer().subLayerPaths:
            layer = Sdf.Layer.FindRelativeToLayer(stage.GetRootLayer(), layer_path)
            if layer and layer.customLayerData.get("lightspeed_layer_type") == "replacement":
                replacement_layer = layer
                break
        self.assertIsNotNone(replacement_layer)

        sublayer = Sdf.Layer.CreateAnonymous()
        replacement_layer.subLayerPaths.append(sublayer.identifier)

        test_prim_path = "/RootNode/meshes/test_ancestral_prim"
        prim_spec = Sdf.CreatePrimInLayer(sublayer, test_prim_path)
        prim_spec.specifier = Sdf.SpecifierDef
        prim_spec.typeName = "Xform"

        prim = stage.GetPrimAtPath(test_prim_path)
        self.assertTrue(prim.IsValid())

        edit_target_layer = stage.GetEditTarget().GetLayer()
        self.assertIsNone(edit_target_layer.GetPrimAtPath(test_prim_path))
        self.assertIsNotNone(sublayer.GetPrimAtPath(test_prim_path))

        window, widget = await self._setup_widget(DeleteRestoreActionWidgetPlugin)

        self.assertEqual(
            widget._get_prim_action_type(prim),
            widget.ActionType.DELETE,
        )

        usd.get_context().get_selection().set_selected_prim_paths([test_prim_path], False)
        widget._delete_prim_cb()

        self.assertIsNone(sublayer.GetPrimAtPath(test_prim_path))

        prim = stage.GetPrimAtPath(test_prim_path)
        self.assertFalse(prim.IsValid())

        widget = None
        window.destroy()
