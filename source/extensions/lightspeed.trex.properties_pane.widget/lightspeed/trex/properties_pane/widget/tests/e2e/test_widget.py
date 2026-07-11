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

import tempfile
from pathlib import Path
from unittest import mock

import omni.kit.undo
import omni.ui as ui
import omni.usd
from carb.input import KeyboardInput
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.properties_pane.particle.widget.particle_lookup_table import (
    get_particle_lookup_table as _get_particle_lookup_table,
)
from lightspeed.trex.properties_pane.widget import AssetReplacementsPane as _AssetReplacementsPane
from lightspeed.trex.properties_pane.widget import setup_ui
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.flux.layer_tree.usd.widget import LayerTransferTarget as _LayerTransferTarget
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, open_stage
from pxr import Sdf, Usd

NUM_PIN_ICONS = 4  # Object, Material, Particles, Logic
NUM_COLLAPSABLE_FRAMES = 7  # Object, Material, Particles, Logic, Selection Tree, Bookmark Tree, History
_TRANSFER_WINDOW_TITLES = (
    "Transfer Modification to Layer",
    "Transfer Definition to Layer",
    "Transfer Layer Changes to Layer",
)


class TestAssetReplacementsWidget(AsyncTestCase):
    PARTICLE_MESH_PATH = "/RootNode/meshes/transfer_workflow_particle_definition/mesh"
    SECOND_PARTICLE_MESH_PATH = "/RootNode/meshes/transfer_workflow_particle_override/mesh"
    NON_PARTICLE_INSTANCE_MESH_PATH = "/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"

    async def test_frame_prim_event_frames_active_viewport(self):
        prim = mock.Mock()
        prim.GetPath.return_value = Sdf.Path("/World/Prim")
        pane = _AssetReplacementsPane.__new__(_AssetReplacementsPane)

        with mock.patch.object(setup_ui, "_get_active_viewport") as viewport:
            pane._on_frame_prim(prim)

        viewport.return_value.frame_viewport_selection.assert_called_once_with(["/World/Prim"])

    async def test_frame_prim_event_without_active_viewport_does_not_get_prim_path(self):
        prim = mock.Mock()
        pane = _AssetReplacementsPane.__new__(_AssetReplacementsPane)

        with mock.patch.object(setup_ui, "_get_active_viewport", return_value=None) as viewport:
            pane._on_frame_prim(prim)

        viewport.assert_called_once_with()
        prim.GetPath.assert_not_called()

    # Before running each test
    async def setUp(self):
        await arrange_windows()
        await open_stage(_get_test_data("usd/project_example/combined.usda"))
        self.temp_dir = tempfile.TemporaryDirectory()
        self._test_windows = []
        self._test_widgets = []

    async def tearDown(self):
        try:
            for wid in reversed(self._test_widgets):
                wid.destroy()
            for window in reversed(self._test_windows):
                window.destroy()
        finally:
            self._test_widgets.clear()
            self._test_windows.clear()
            self.__destroy_transfer_windows()
            if omni.usd.get_context().get_stage():
                await omni.usd.get_context().close_stage_async()
            self.temp_dir.cleanup()

    async def __setup_widget(self, title: str):
        window = ui.Window(title, height=800, width=500)
        with window.frame:
            wid = _AssetReplacementsPane("")
            wid.show(True)
        self._test_windows.append(window)
        self._test_widgets.append(wid)

        await ui_test.human_delay(human_delay_speed=2)  # test re-runs will fail if speed < 2

        return window, wid

    async def __destroy(self, window, wid):
        try:
            wid.destroy()
        finally:
            window.destroy()
            if window in self._test_windows:
                self._test_windows.remove(window)
            if wid in self._test_widgets:
                self._test_widgets.remove(wid)

    @staticmethod
    def __destroy_transfer_windows() -> None:
        for title in _TRANSFER_WINDOW_TITLES:
            transfer_window = ui.Workspace.get_window(title)
            if transfer_window:
                transfer_window.destroy()

    async def __set_selection(self, prim_paths: list[str], human_delay_speed: int = 10):
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(prim_paths, False)
        await ui_test.human_delay(human_delay_speed=human_delay_speed)

    @staticmethod
    def __visible(selector: str):
        return [
            widget
            for widget in ui_test.find_all(selector)
            if widget.widget.visible and widget.widget.computed_width > 0 and widget.widget.computed_height > 0
        ]

    def __label(self, window_title: str, *, text: str | None = None, tooltip: str | None = None):
        for label in self.__visible(f"{window_title}//Frame/**/Label[*]"):
            if text is not None and label.widget.text == text:
                return label
            if tooltip is not None and label.widget.tooltip == tooltip:
                return label
        return None

    async def __scroll_to_label(self, window_title: str, label_text: str, alignment: float = 0.1):
        scroll_frame = ui_test.find(f"{window_title}//Frame/**/ScrollingFrame[*].name=='WorkspaceBackground'")
        self.assertIsNotNone(scroll_frame)
        for _ in range(12):
            label = self.__label(window_title, text=label_text)
            if label:
                label.widget.scroll_here_y(alignment)
                await ui_test.human_delay(human_delay_speed=8)
                return label
            scroll_frame.widget.scroll_y += 80
            await ui_test.human_delay(human_delay_speed=4)
        self.fail(f"Could not find label {label_text!r}")
        raise AssertionError("unreachable")

    async def __expand_group(self, window_title: str, group_label: str):
        label = await self.__scroll_to_label(window_title, group_label)
        branches = [
            branch
            for branch in self.__visible(f"{window_title}//Frame/**/Image[*].identifier=='property_branch'")
            if abs(branch.center.y - label.center.y) <= 8 and branch.center.x < label.center.x
        ]
        self.assertGreater(len(branches), 0)
        await min(branches, key=lambda branch: label.center.x - branch.center.x).click()
        await ui_test.human_delay(human_delay_speed=8)

    def __float_drags_for_attribute(self, window_title: str, attribute_path: str):
        fields = []
        for widget_type in ("FloatBoundedDrag", "FloatDrag"):
            for field in self.__visible(f"{window_title}//Frame/**/{widget_type}[*]"):
                if attribute_path in field.widget.identifier.split(","):
                    fields.append(field)
        self.assertGreater(len(fields), 0)
        return sorted(fields, key=lambda field: field.center.x)

    @staticmethod
    def __remove_property_specs(layer: Sdf.Layer, property_paths: tuple[str, ...]) -> None:
        with Sdf.ChangeBlock():
            for property_path in property_paths:
                path = Sdf.Path(property_path)
                prop_spec = layer.GetPropertyAtPath(path)
                if prop_spec is None:
                    continue
                prim_spec = layer.GetPrimAtPath(path.GetPrimPath())
                if prim_spec is not None:
                    prim_spec.RemoveProperty(prop_spec)

    async def __confirm_transfer(self, transfer_window_title: str, target_layer: Sdf.Layer):
        target_layer_frame = ui_test.find(
            f"{transfer_window_title}//Frame/**/Frame[*].tooltip=='{target_layer.identifier}'"
        )
        self.assertIsNotNone(target_layer_frame)
        await target_layer_frame.click()
        await ui_test.human_delay(human_delay_speed=4)

        transfer_button = ui_test.find(
            f"{transfer_window_title}//Frame/**/Button[*].identifier=='property_transfer_confirm'"
        )
        self.assertIsNotNone(transfer_button)
        for _ in range(8):
            if transfer_button.widget.enabled:
                break
            await ui_test.human_delay(human_delay_speed=4)
        self.assertTrue(transfer_button.widget.enabled)
        await transfer_button.click()
        await ui_test.human_delay(human_delay_speed=8)
        self.__destroy_transfer_windows()

    async def __transfer_property(self, window_title: str, target_layer: Sdf.Layer, *, text=None, tooltip=None):
        label = self.__label(window_title, text=text, tooltip=tooltip)
        if label is None and text is not None:
            label = await self.__scroll_to_label(window_title, text)
        self.assertIsNotNone(label)

        more_buttons = [
            image
            for image in self.__visible(f"{window_title}//Frame/**/Image[*].identifier=='override_more_menu_button'")
            if abs(image.center.y - label.center.y) <= 8 and image.center.x < label.center.x
        ]
        self.assertGreater(len(more_buttons), 0)
        await min(more_buttons, key=lambda image: label.center.x - image.center.x).click()
        await ui_test.human_delay(human_delay_speed=4)
        await ui_test.select_context_menu("Transfer This Property Modification to Layer...", human_delay_speed=8)
        await ui_test.human_delay(human_delay_speed=8)
        await self.__confirm_transfer("Transfer Modification to Layer", target_layer)

    async def __transfer_action(self, window_title: str, target_layer: Sdf.Layer, identifier: str, menu_label: str):
        actions = [
            image
            for image in self.__visible(f"{window_title}//Frame/**/Image[*].identifier=='{identifier}'")
            if image.widget.name == "More"
        ]
        self.assertGreater(len(actions), 0)
        action = actions[0]
        action.widget.scroll_here_y(0.5)
        await ui_test.human_delay(human_delay_speed=8)
        await action.click()
        await ui_test.human_delay(human_delay_speed=4)
        await ui_test.select_context_menu(menu_label, human_delay_speed=8)
        await ui_test.human_delay(human_delay_speed=8)
        await self.__confirm_transfer(
            "Transfer Definition to Layer" if "definition" in menu_label else "Transfer Modification to Layer",
            target_layer,
        )

    async def test_transfer_full_property_pane_workflow_uses_project_fixture_cases(self):
        object_selection_path = "/RootNode/instances/inst_FEE1DEADF00D0001_0/reference_override/Cube_01"
        object_property_paths = (
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/reference_override/Cube_01.xformOp:translate",
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/reference_override/Cube_01.xformOp:rotateXYZ",
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/reference_override/Cube_01.xformOp:scale",
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/reference_override/Cube_01.xformOpOrder",
        )
        material_selection_path = "/RootNode/meshes/transfer_workflow_material_mesh/mesh"
        material_property_path = "/RootNode/Looks/transfer_workflow_material/Shader.inputs:transferWorkflowRoughness"
        reference_parent_path = "/RootNode/meshes/mesh_FEE1DEADF00D0001"
        reference_prim_path = "/RootNode/meshes/mesh_FEE1DEADF00D0001/reference_override"
        light_path = "/RootNode/meshes/mesh_FEE1DEADF00D0001/TransferWorkflowLight"
        light_intensity_path = "/RootNode/meshes/mesh_FEE1DEADF00D0001/TransferWorkflowLight.inputs:intensity"
        particle_definition_path = "/RootNode/meshes/transfer_workflow_particle_definition/mesh"
        particle_definition_gravity_path = (
            "/RootNode/meshes/transfer_workflow_particle_definition/mesh.primvars:particle:gravityForce"
        )
        particle_definition_override_path = (
            "/RootNode/meshes/transfer_workflow_particle_definition/mesh.primvars:particle:maxNumParticles"
        )
        particle_override_path = "/RootNode/meshes/transfer_workflow_particle_override/mesh"
        particle_property_path = (
            "/RootNode/meshes/transfer_workflow_particle_override/mesh.primvars:particle:maxNumParticles"
        )
        logic_mesh_path = "/RootNode/meshes/mesh_FEE1DEADF00D0001/mesh"
        logic_graph_path = "/RootNode/meshes/mesh_FEE1DEADF00D0001/mesh/TransferWorkflowLogicGraph"
        logic_node_path = "/RootNode/meshes/mesh_FEE1DEADF00D0001/mesh/TransferWorkflowLogicGraph/MeshProximity"
        logic_property_path = (
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/mesh/TransferWorkflowLogicGraph/MeshProximity.inputs:target"
        )

        source_layer = Sdf.Layer.FindOrOpen(_get_test_data("usd/project_example/replacements.usda"))
        self.assertIsNotNone(source_layer)
        target_layer = Sdf.Layer.FindOrOpen(_get_test_data("usd/project_example/transfer_workflow_target.usda"))
        self.assertIsNotNone(target_layer)
        particle_definition_override_layer = Sdf.Layer.FindOrOpen(
            _get_test_data("usd/project_example/transfer_workflow_particle_overrides.usda")
        )
        particle_override_layer = Sdf.Layer.FindOrOpen(
            _get_test_data("usd/project_example/transfer_workflow_second_particle_overrides.usda")
        )
        self.assertIsNotNone(particle_definition_override_layer)
        self.assertIsNotNone(particle_override_layer)

        stage = omni.usd.get_context().get_stage()
        target_light_intensity = target_layer.GetAttributeAtPath(light_intensity_path).default
        self.assertIsNotNone(target_light_intensity)
        particle_info = _get_particle_lookup_table()[particle_property_path.rsplit(".", 1)[-1]]
        particle_composed_value = stage.GetAttributeAtPath(particle_property_path).Get()
        _window, _wid = await self.__setup_widget("test_transfer_full_property_pane_workflow")

        try:
            # Transfer the transform rows from the object panel; these must move as one group.
            source_layer_before = source_layer.ExportToString()
            target_layer_before = target_layer.ExportToString()
            await self.__set_selection([object_selection_path])
            await self.__transfer_property(_window.title, target_layer, tooltip="xformOp:translate")
            for property_path in object_property_paths:
                self.assertIsNone(source_layer.GetPropertyAtPath(property_path))
                self.assertIsNotNone(target_layer.GetPropertyAtPath(property_path))

            # Undo/redo of one real UI property transfer covers the modal command flow.
            omni.kit.undo.undo()
            await ui_test.human_delay(human_delay_speed=4)
            self.assertEqual(source_layer.ExportToString(), source_layer_before)
            self.assertEqual(target_layer.ExportToString(), target_layer_before)

            omni.kit.undo.redo()
            await ui_test.human_delay(human_delay_speed=4)
            for property_path in object_property_paths:
                self.assertIsNone(source_layer.GetPropertyAtPath(property_path))
                self.assertIsNotNone(target_layer.GetPropertyAtPath(property_path))

            # Transfer a material property from the native material-property row menu.
            await self.__set_selection([material_selection_path])
            await self.__expand_group(_window.title, "Specular")
            await self.__transfer_property(_window.title, target_layer, text="Transfer Workflow Roughness")
            self.assertIsNone(source_layer.GetPropertyAtPath(material_property_path))
            self.assertIsNotNone(target_layer.GetPropertyAtPath(material_property_path))

            # Transfer a non-captured reference override from the reference action button.
            await self.__set_selection([reference_parent_path])
            await self.__transfer_action(
                _window.title, target_layer, "reference_transfer_overrides", "Transfer modification to..."
            )
            source_reference_spec = source_layer.GetPrimAtPath(reference_prim_path)
            target_reference_spec = target_layer.GetPrimAtPath(reference_prim_path)
            self.assertTrue(source_reference_spec is None or not source_reference_spec.hasReferences)
            self.assertIsNotNone(target_reference_spec)
            self.assertTrue(target_reference_spec.hasReferences)

            # Transfer a stage-light definition while preserving the existing target-layer intensity override.
            await self.__set_selection(["/RootNode/instances/inst_FEE1DEADF00D0001_0/TransferWorkflowLight"])
            self.assertEqual(target_layer.GetAttributeAtPath(light_intensity_path).default, target_light_intensity)
            await self.__transfer_action(
                _window.title, target_layer, "stage_light_transfer_overrides", "Transfer definition to..."
            )

            self.assertIsNone(source_layer.GetPrimAtPath(light_path))
            self.assertIsNotNone(target_layer.GetPrimAtPath(light_path))
            self.assertEqual(target_layer.GetAttributeAtPath(light_intensity_path).default, target_light_intensity)

            # Transfer a particle system definition without touching overrides authored on other layers.
            particle_definition_override_before = particle_definition_override_layer.ExportToString()
            await self.__set_selection([particle_definition_path])
            await self.__scroll_to_label(_window.title, "PARTICLE PROPERTIES")
            await self.__transfer_action(
                _window.title, target_layer, "particle_properties_transfer_overrides", "Transfer definition to..."
            )

            self.assertIsNone(source_layer.GetPrimAtPath(particle_definition_path))
            self.assertEqual(particle_definition_override_layer.ExportToString(), particle_definition_override_before)
            self.assertAlmostEqual(
                target_layer.GetAttributeAtPath(particle_definition_gravity_path).default,
                9.8,
                places=5,
            )
            target_particle_definition_override = target_layer.GetAttributeAtPath(particle_definition_override_path)
            if target_particle_definition_override:
                self.assertNotEqual(target_particle_definition_override.default, 64)

            # Transfer a particle property override while preserving the particle system definition.
            await self.__set_selection([particle_override_path])
            await self.__scroll_to_label(_window.title, "PARTICLE PROPERTIES")
            await self.__expand_group(_window.title, particle_info["group"])
            await self.__transfer_property(_window.title, target_layer, text=particle_info["name"])

            particle_definition_spec = source_layer.GetPrimAtPath(particle_override_path)
            self.assertIsNotNone(particle_definition_spec)
            self.assertTrue(particle_definition_spec.HasInfo(Usd.Tokens.apiSchemas))
            self.assertIsNone(source_layer.GetPropertyAtPath(particle_property_path))
            self.assertIsNone(particle_override_layer.GetPropertyAtPath(particle_property_path))
            self.assertEqual(target_layer.GetAttributeAtPath(particle_property_path).default, particle_composed_value)

            # Transfer a logic-node property through the row menu.
            await self.__set_selection([logic_node_path])
            await self.__scroll_to_label(_window.title, "LOGIC PROPERTIES")
            await self.__transfer_property(_window.title, target_layer, text="Target")
            self.assertIsNone(source_layer.GetPropertyAtPath(logic_property_path))
            self.assertIsNotNone(target_layer.GetPropertyAtPath(logic_property_path))

            # Transfer the logic graph definition and verify the previously moved property remains on the target.
            await self.__set_selection([logic_mesh_path])
            await self.__scroll_to_label(_window.title, "TransferWorkflowLogicGraph", alignment=0.5)
            await self.__transfer_action(
                _window.title, target_layer, "logic_graph_transfer_overrides", "Transfer definition to..."
            )
            self.assertIsNone(source_layer.GetPrimAtPath(logic_graph_path))
            self.assertIsNotNone(target_layer.GetPrimAtPath(logic_graph_path))
            self.assertIsNotNone(target_layer.GetPropertyAtPath(logic_property_path))
        finally:
            await self.__destroy(_window, _wid)

    async def test_xform_double_click_does_not_author_override_until_value_changes(self):
        object_selection_path = "/RootNode/instances/inst_FEE1DEADF00D0001_0/reference_override/Cube_01"
        object_property_paths = (
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/reference_override/Cube_01.xformOp:translate",
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/reference_override/Cube_01.xformOp:rotateXYZ",
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/reference_override/Cube_01.xformOp:scale",
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/reference_override/Cube_01.xformOpOrder",
        )
        layer_manager = _LayerManagerCore(context_name="")
        replacement_layer = layer_manager.get_layer_of_type(_LayerType.replacement)
        self.assertIsNotNone(replacement_layer)
        replacement_layer_before = replacement_layer.ExportToString()
        stage = omni.usd.get_context().get_stage()
        translate_attr = stage.GetAttributeAtPath(object_property_paths[0])
        self.assertIsNotNone(translate_attr)
        _window, _wid = await self.__setup_widget(
            "test_xform_double_click_does_not_author_override_until_value_changes"
        )

        try:
            layer_manager.set_edit_target_layer_of_type(_LayerType.replacement, do_undo=False)
            self.__remove_property_specs(replacement_layer, object_property_paths)
            await self.__set_selection([object_selection_path])

            x_field, *_ = self.__float_drags_for_attribute(_window.title, object_property_paths[0])
            await x_field.double_click(human_delay_speed=2)
            await ui_test.emulate_keyboard_press(KeyboardInput.TAB)
            await ui_test.human_delay(human_delay_speed=8)

            self.assertEqual(
                [],
                [path for path in object_property_paths if replacement_layer.GetPropertyAtPath(path) is not None],
            )

            x_field, *_ = self.__float_drags_for_attribute(_window.title, object_property_paths[0])
            await x_field.double_click(human_delay_speed=2)
            await ui_test.emulate_char_press("2.0")
            await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
            await ui_test.human_delay(human_delay_speed=8)

            translate_value = translate_attr.Get()
            self.assertAlmostEqual(translate_value[0], 2.0)
            self.assertEqual(
                set(object_property_paths),
                {path for path in object_property_paths if replacement_layer.GetPropertyAtPath(path) is not None},
            )
        finally:
            replacement_layer.ImportFromString(replacement_layer_before)
            omni.kit.undo.clear_stack()
            omni.kit.undo.clear_history()
            await self.__destroy(_window, _wid)

    async def test_layer_project_transfer_uses_shared_transfer_window(self):
        source_layer = Sdf.Layer.FindOrOpen(
            _get_test_data("usd/project_example/transfer_workflow_second_particle_overrides.usda")
        )
        target_layer = Sdf.Layer.FindOrOpen(_get_test_data("usd/project_example/transfer_workflow_target.usda"))
        source_property_path = (
            "/RootNode/meshes/transfer_workflow_particle_override/mesh.primvars:particle:maxNumParticles"
        )
        self.assertIsNotNone(source_layer)
        self.assertIsNotNone(target_layer)
        self.assertIsNotNone(source_layer.GetPropertyAtPath(source_property_path))

        source_layer_before = source_layer.ExportToString()
        target_layer_before = target_layer.ExportToString()
        _window, _wid = await self.__setup_widget("test_layer_project_transfer_uses_shared_transfer_window")

        try:
            source_item = None
            for _ in range(8):
                source_item = _wid._layer_tree_widget._model.find_item(
                    source_layer.identifier,
                    lambda item, identifier: item.data.get("layer") and item.data["layer"].identifier == identifier,
                )
                if source_item:
                    break
                await ui_test.human_delay(human_delay_speed=4)
            self.assertIsNotNone(source_item)

            # Open the project-layer transfer path from the layer panel. It must use the shared transfer modal.
            _wid._layer_tree_widget._on_transfer_layer_changes(source_item, _LayerTransferTarget.PROJECT_LAYER)
            await ui_test.human_delay(human_delay_speed=8)

            self.assertIsNotNone(ui.Workspace.get_window("Transfer Layer Changes to Layer"))
            self.assertIsNone(ui.Workspace.get_window("Transfer Layer Changes"))

            # Choose an existing project layer target and transfer all authored changes from the source layer.
            await self.__confirm_transfer("Transfer Layer Changes to Layer", target_layer)
            self.assertIsNone(source_layer.GetPropertyAtPath(source_property_path))
            self.assertIsNotNone(target_layer.GetPropertyAtPath(source_property_path))

            # Undo restores the whole layer transfer as one user action.
            omni.kit.undo.undo()
            await ui_test.human_delay(human_delay_speed=4)
            self.assertEqual(source_layer.ExportToString(), source_layer_before)
            self.assertEqual(target_layer.ExportToString(), target_layer_before)
        finally:
            self.__destroy_transfer_windows()
            source_layer.ImportFromString(source_layer_before)
            target_layer.ImportFromString(target_layer_before)
            await self.__destroy(_window, _wid)

    async def test_widget_destroy_closes_open_transfer_modal(self):
        object_selection_path = "/RootNode/instances/inst_FEE1DEADF00D0001_0/reference_override/Cube_01"
        _window, _wid = await self.__setup_widget("test_widget_destroy_closes_open_transfer_modal")
        destroyed = False

        try:
            # Open a transfer modal from the property row menu.
            await self.__set_selection([object_selection_path])
            label = self.__label(_window.title, tooltip="xformOp:translate")
            self.assertIsNotNone(label)
            more_buttons = [
                image
                for image in self.__visible(
                    f"{_window.title}//Frame/**/Image[*].identifier=='override_more_menu_button'"
                )
                if abs(image.center.y - label.center.y) <= 8 and image.center.x < label.center.x
            ]
            self.assertGreater(len(more_buttons), 0)
            await min(more_buttons, key=lambda image: label.center.x - image.center.x).click()
            await ui_test.human_delay(human_delay_speed=4)
            await ui_test.select_context_menu("Transfer This Property Modification to Layer...", human_delay_speed=8)
            await ui_test.human_delay(human_delay_speed=8)

            self.assertIsNotNone(ui.Workspace.get_window("Transfer Modification to Layer"))

            # Destroying the parent property widget must close any owned transfer modal.
            await self.__destroy(_window, _wid)
            destroyed = True
            await ui_test.human_delay(human_delay_speed=8)

            self.assertIsNone(ui.Workspace.get_window("Transfer Modification to Layer"))
        finally:
            self.__destroy_transfer_windows()
            if not destroyed:
                await self.__destroy(_window, _wid)

    async def test_property_rows_keep_override_menu_disabled_without_authored_specs(self):
        mesh_path = "/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"
        _window, _wid = await self.__setup_widget("test_property_rows_keep_override_menu_disabled")

        try:
            # Select an unmodified mesh and collect the visible row more-menu buttons.
            await self.__set_selection([mesh_path])
            more_images = self.__visible(f"{_window.title}//Frame/**/Image[*].identifier=='override_more_menu_button'")

            # The button remains visible for consistency, but it is disabled when no spec can transfer.
            self.assertGreater(len(more_images), 0)
            self.assertEqual(more_images[0].widget.name, "MoreDisabled")
        finally:
            self.__destroy_transfer_windows()
            await self.__destroy(_window, _wid)

    @staticmethod
    def __get_particle_widgets(_window):
        particle_frame = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_particle_widget'")
        create_frame = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_particle_create'")
        create_button = ui_test.find(f"{_window.title}//Frame/**/Button[*].identifier=='create_particle_system_button'")
        return particle_frame, create_frame, create_button

    async def test_collapse_frames_here(self):
        # setup
        _window, _wid = await self.__setup_widget("test_collapse_frames_here")  # Keep in memory during test
        collapsable_frames = ui_test.find_all(
            f"{_window.title}//Frame/**/CollapsableFrame[*].identifier=='PropertyCollapsableFrame'"
        )
        self.assertEqual(len(collapsable_frames), NUM_COLLAPSABLE_FRAMES)
        await self.__destroy(_window, _wid)

    async def test_collapse_refresh_object_property_when_collapsed(self):
        # setup
        _window, _wid = await self.__setup_widget("test_collapse_refresh_object_property_when_collapsed")

        collapsable_frame_arrows = ui_test.find_all(
            f"{_window.title}//Frame/**/Image[*].identifier=='PropertyCollapsableFrameArrow'"
        )
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        frame_mesh_prim = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")

        self.assertEqual(len(collapsable_frame_arrows), NUM_COLLAPSABLE_FRAMES)
        self.assertIsNotNone(frame_mesh_ref)
        self.assertIsNotNone(frame_mesh_prim)

        # by default, no frame are visible
        self.assertFalse(frame_mesh_prim.widget.visible)
        self.assertFalse(frame_mesh_ref.widget.visible)

        # we close the object property frame
        await collapsable_frame_arrows[4].click()

        # we select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=3)

        # we re-open the object property frame
        await collapsable_frame_arrows[4].click()

        # no we should see the mesh property
        self.assertTrue(frame_mesh_prim.widget.visible)
        self.assertFalse(frame_mesh_ref.widget.visible)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertGreaterEqual(len(item_prims), 2)

        # we close the object property frame
        await collapsable_frame_arrows[4].click()

        # we select the mesh ref
        await item_prims[0].click()

        # we re-open the object property frame
        await collapsable_frame_arrows[4].click()

        # no we should see the ref property
        self.assertFalse(frame_mesh_prim.widget.visible)
        self.assertTrue(frame_mesh_ref.widget.visible)
        await self.__destroy(_window, _wid)

    async def test_collapse_refresh_material_property_when_collapsed(self):
        # setup
        _window, _wid = await self.__setup_widget("test_collapse_refresh_material_property_when_collapsed")

        collapsable_frame_arrows = ui_test.find_all(
            f"{_window.title}//Frame/**/Image[*].identifier=='PropertyCollapsableFrameArrow'"
        )
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")

        self.assertEqual(len(collapsable_frame_arrows), NUM_COLLAPSABLE_FRAMES)
        self.assertIsNotNone(frame_material)

        # by default, no frame are visible
        self.assertFalse(frame_material.widget.visible)

        # we close the material property frame
        await collapsable_frame_arrows[4].click()

        # we select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=20)

        # we re-open the material property frame
        collapsable_frame_arrows = ui_test.find_all(
            f"{_window.title}//Frame/**/Image[*].identifier=='PropertyCollapsableFrameArrow'"
        )
        await collapsable_frame_arrows[4].click()

        # no we should see the material property
        self.assertTrue(frame_material.widget.visible)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertGreaterEqual(len(item_prims), 2)

        # we close the material property frame
        await collapsable_frame_arrows[4].click()

        # we select the mesh ref
        await item_prims[0].click()

        # we re-open the material property frame
        # because the size of the frame change, we need to re-grab the widgets
        collapsable_frame_arrows = ui_test.find_all(
            f"{_window.title}//Frame/**/Image[*].identifier=='PropertyCollapsableFrameArrow'"
        )
        await collapsable_frame_arrows[4].click()

        # we still not see the material property
        self.assertFalse(frame_material.widget.visible)
        await self.__destroy(_window, _wid)

    async def test_object_properties_cleared_when_none_selected(self):
        # setup
        _window, _wid = await self.__setup_widget("test_object_properties_cleared_when_none_selected")

        # ensure the proper frames exist
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")

        # ensure the none frames exist and the relevant one is visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        self.assertEqual(len(none_frames), 3)
        self.assertTrue(none_frames[0].widget.visible)

        # select a mesh prim
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        await item_prims[0].click()

        # ensure the none frame is no longer visible
        self.assertFalse(none_frames[0].widget.visible)

        # ensure the mesh ref frame is visible
        self.assertTrue(frame_mesh_ref.widget.visible)

        # we un-select
        await item_prims[1].click()
        usd_context.get_selection().clear_selected_prim_paths()
        await ui_test.human_delay(human_delay_speed=10)

        # ensure the none frame is now visible and ref frame is not
        self.assertTrue(none_frames[0].widget.visible)
        self.assertFalse(frame_mesh_ref.widget.visible)

        await self.__destroy(_window, _wid)

    async def test_material_properties_cleared_when_none_selected(self):
        # setup
        _window, _wid = await self.__setup_widget("test_material_properties_cleared_when_none_selected")

        # ensure the proper frames exist
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        self.assertIsNotNone(frame_material)

        # ensure the none frames exist and the relevant one is visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        self.assertEqual(len(none_frames), 3)
        self.assertTrue(none_frames[1].widget.visible)

        # we select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)

        # ensure the none frame is no longer visible
        self.assertFalse(none_frames[1].widget.visible)

        # the material properties should be visible
        self.assertTrue(frame_material.widget.visible)

        # we un-select
        usd_context.get_selection().clear_selected_prim_paths()
        await ui_test.human_delay(human_delay_speed=10)

        # ensure the none frame is visible and material property frame is not
        self.assertTrue(none_frames[1].widget.visible)
        self.assertFalse(frame_material.widget.visible)

        await self.__destroy(_window, _wid)

    async def test_select_material_prim_populates_material_properties(self):
        # setup
        _window, _wid = await self.__setup_widget("test_select_material_prim_populates_material_properties")

        # ensure the proper frames exist
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        self.assertIsNotNone(frame_material)

        # ensure the none frames exist and all are visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        self.assertEqual(len(none_frames), 3)
        self.assertTrue(none_frames[0].widget.visible)  # selection tree
        self.assertTrue(none_frames[1].widget.visible)  # object properties
        self.assertTrue(none_frames[2].widget.visible)  # material properties

        # ensure selection tree is empty still
        selection_tree = ui_test.find(f"{_window.title}//Frame/**/TreeView[*].identifier=='LiveSelectionTreeView'")
        self.assertEqual(len(selection_tree.widget.selection), 0)

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/Looks/mat_BC868CE5A075ABB1"], False)
        await ui_test.human_delay(human_delay_speed=10)

        # ensure the respective none frames are visible/invisible and material widget is visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        self.assertTrue(none_frames[0].widget.visible)  # selection tree
        self.assertTrue(none_frames[1].widget.visible)  # object properties
        self.assertFalse(none_frames[2].widget.visible)  # material properties
        self.assertTrue(frame_material.widget.visible)  # material widget

        # ensure the selection tree is still not occupied since direct mat selection
        self.assertEqual(len(selection_tree.widget.selection), 0)

        await self.__destroy(_window, _wid)

    async def test_select_mesh_prim_populates_widgets(self):
        # setup
        _window, _wid = await self.__setup_widget("test_select_mesh_prim_populates_widgets")

        # ensure the proper frames exist
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        self.assertIsNotNone(frame_material)

        # ensure the none frames exist and all are visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        self.assertEqual(len(none_frames), 3)
        self.assertTrue(none_frames[0].widget.visible)  # selection tree
        self.assertTrue(none_frames[1].widget.visible)  # object properties
        self.assertTrue(none_frames[2].widget.visible)  # material properties

        # ensure selection tree is empty still
        selection_tree = ui_test.find(f"{_window.title}//Frame/**/TreeView[*].identifier=='LiveSelectionTreeView'")
        self.assertEqual(len(selection_tree.widget.selection), 0)

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)

        # ensure the respective none frames are not visible and material widget is visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        self.assertFalse(none_frames[0].widget.visible)  # selection tree
        self.assertFalse(none_frames[1].widget.visible)  # object properties
        self.assertFalse(none_frames[2].widget.visible)  # material properties
        self.assertTrue(frame_material.widget.visible)  # material widget

        # ensure the selection tree is occupied with the selection since mesh selection
        self.assertEqual(len(selection_tree.widget.selection), 1)

        await self.__destroy(_window, _wid)

    async def test_select_material_and_mesh_prims_populates_widgets(self):
        # setup
        _window, _wid = await self.__setup_widget("test_select_material_and_mesh_prims_populates_widgets")

        # ensure the proper frames exist
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        self.assertIsNotNone(frame_material)

        # ensure the none frames exist and all are visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        self.assertEqual(len(none_frames), 3)
        self.assertTrue(none_frames[0].widget.visible)  # selection tree
        self.assertTrue(none_frames[1].widget.visible)  # object properties
        self.assertTrue(none_frames[2].widget.visible)  # material properties

        # ensure selection tree is empty still
        selection_tree = ui_test.find(f"{_window.title}//Frame/**/TreeView[*].identifier=='LiveSelectionTreeView'")
        self.assertEqual(len(selection_tree.widget.selection), 0)

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/Looks/mat_BC868CE5A075ABB1", "/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False
        )
        await ui_test.human_delay(human_delay_speed=10)

        # ensure the respective none frames are not visible and material widget is visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        self.assertFalse(none_frames[0].widget.visible)  # selection tree
        self.assertFalse(none_frames[1].widget.visible)  # object properties
        self.assertFalse(none_frames[2].widget.visible)  # material properties
        self.assertTrue(frame_material.widget.visible)  # material widget

        # ensure the selection tree is occupied with the selection since mesh selection
        self.assertEqual(len(selection_tree.widget.selection), 1)

        await self.__destroy(_window, _wid)

    async def test_particle_create_state_visible_for_valid_non_particle_target(self):
        # Arrange
        _window, _wid = await self.__setup_widget("test_particle_create_state_visible_for_valid_non_particle_target")
        particle_frame, create_frame, create_button = self.__get_particle_widgets(_window)

        self.assertIsNotNone(particle_frame)
        self.assertIsNotNone(create_frame)
        self.assertIsNotNone(create_button)

        # Act
        await self.__set_selection([self.NON_PARTICLE_INSTANCE_MESH_PATH])

        # Assert
        self.assertFalse(particle_frame.widget.visible)
        self.assertTrue(create_frame.widget.visible)
        self.assertTrue(create_button.widget.enabled)

        await self.__destroy(_window, _wid)

    async def test_material_refresh_preserves_selection_order_after_dedupe(self):
        # Arrange
        _window, _wid = await self.__setup_widget("test_material_refresh_preserves_selection_order_after_dedupe")
        expected_paths = [self.SECOND_PARTICLE_MESH_PATH, self.PARTICLE_MESH_PATH]
        await self.__set_selection(expected_paths)

        with (
            mock.patch.object(_wid._material_properties_widget, "refresh") as refresh_mock,
        ):
            # Act
            _wid._refresh_material_properties_widget()

        # Assert
        refresh_mock.assert_called_once()
        refreshed_prims = refresh_mock.call_args.args[0]
        self.assertEqual([str(prim.GetPath()) for prim in refreshed_prims], expected_paths)

        await self.__destroy(_window, _wid)

    async def test_particle_properties_win_over_create_state_for_mixed_selection(self):
        # Arrange
        _window, _wid = await self.__setup_widget("test_particle_properties_win_over_create_state_for_mixed_selection")
        particle_frame, create_frame, _create_button = self.__get_particle_widgets(_window)

        self.assertIsNotNone(particle_frame)
        self.assertIsNotNone(create_frame)

        # Act
        await self.__set_selection([self.NON_PARTICLE_INSTANCE_MESH_PATH, self.PARTICLE_MESH_PATH])

        # Assert
        self.assertTrue(particle_frame.widget.visible)
        self.assertFalse(create_frame.widget.visible)

        await self.__destroy(_window, _wid)

    async def test_particle_mixed_attribute_uses_last_selected_value(self):
        # Arrange
        _window, _wid = await self.__setup_widget("test_particle_mixed_attribute_uses_last_selected_value")

        # Act
        await self.__set_selection([self.PARTICLE_MESH_PATH, self.SECOND_PARTICLE_MESH_PATH])

        # Assert
        all_items = _wid._particle_properties_widget.property_model.get_all_items()
        gravity_item = next(
            (
                item
                for item in all_items
                if getattr(item, "attribute_paths", None)
                and any(str(path).endswith("primvars:particle:gravityForce") for path in item.attribute_paths)
            ),
            None,
        )
        self.assertIsNotNone(gravity_item)
        self.assertTrue(gravity_item.value_models[0].is_mixed)
        self.assertAlmostEqual(gravity_item.value_models[0].get_value_as_float(), 1.0, places=5)

        await self.__destroy(_window, _wid)

    async def test_object_pinning(self):
        # setup
        _window, _wid = await self.__setup_widget("test_object_pinning")

        # ensure the mesh reference and prim frames exist
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        frame_mesh_prim = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")
        self.assertIsNotNone(frame_mesh_ref)
        self.assertIsNotNone(frame_mesh_prim)

        # select a mesh
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)

        # select the mesh reference and ensure only the reference properties are visible
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        await item_prims[0].click()
        self.assertTrue(frame_mesh_ref.widget.visible)
        self.assertFalse(frame_mesh_prim.widget.visible)

        # click the pin icons to pin
        pin_icon_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_frame_pin_icon'")
        self.assertEqual(len(pin_icon_images), NUM_PIN_ICONS)
        await pin_icon_images[0].click()
        await ui_test.human_delay()

        # ensure the pin label is accurate
        pin_labels = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='pin_label_text'")
        self.assertEqual(pin_labels[0].widget.text, "meshes/mesh_0AB745B8BEE1F16B")

        # change the selection to the mesh prim
        await item_prims[1].click()

        # ensure the property visibility hasn't changed
        self.assertTrue(frame_mesh_ref.widget.visible)
        self.assertFalse(frame_mesh_prim.widget.visible)

        # ensure the pin label is still accurate
        pin_labels = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='pin_label_text'")
        self.assertEqual(pin_labels[0].widget.text, "meshes/mesh_0AB745B8BEE1F16B")

        # click the pin icons to un-pin
        await pin_icon_images[0].click()
        await ui_test.human_delay()

        # ensure that only the mesh prim widget is now visible
        self.assertFalse(frame_mesh_ref.widget.visible)
        self.assertTrue(frame_mesh_prim.widget.visible)

        # ensure the pin label is now empty
        pin_labels = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='pin_label_text'")
        self.assertListEqual(pin_labels, [])

        await self.__destroy(_window, _wid)

    async def test_material_pinning_from_mesh_selection(self):
        # setup
        _window, _wid = await self.__setup_widget("test_material_pinning_from_mesh_selection")

        # ensure the material frame exists
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        self.assertIsNotNone(frame_material)

        # select a mesh and ensure the material properties are visible
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)
        self.assertTrue(frame_material.widget.visible)

        # click the pin icons to pin
        pin_icon_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_frame_pin_icon'")
        self.assertEqual(len(pin_icon_images), NUM_PIN_ICONS)
        await pin_icon_images[1].click()
        await ui_test.human_delay()

        # ensure the pin label is accurate
        pin_labels = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='pin_label_text'")
        self.assertEqual(pin_labels[0].widget.text, "Looks/mat_BC868CE5A075ABB1")

        # change selection to the mesh reference
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        await item_prims[0].click()
        await ui_test.human_delay()

        # material properties should still be visible since pinned
        self.assertTrue(frame_material.widget.visible)

        # ensure the pin label is accurate
        pin_labels = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='pin_label_text'")
        self.assertEqual(pin_labels[0].widget.text, "Looks/mat_BC868CE5A075ABB1")

        # click the pin icons to un-pin
        pin_icon_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_frame_pin_icon'")
        await pin_icon_images[1].click()
        await ui_test.human_delay()

        # material properties should no longer be visible since un-pinned
        self.assertFalse(frame_material.widget.visible)

        # ensure the pin label is now empty
        pin_labels = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='pin_label_text'")
        self.assertListEqual(pin_labels, [])

        await self.__destroy(_window, _wid)

    async def test_material_pinning_from_material_selection(self):
        # setup
        _window, _wid = await self.__setup_widget("test_material_pinning_from_material_selection")

        # ensure the material frame exists
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        self.assertIsNotNone(frame_material)

        # select a mesh and ensure the material properties are visible
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/Looks/mat_BC868CE5A075ABB1"], False)
        await ui_test.human_delay(human_delay_speed=10)
        self.assertTrue(frame_material.widget.visible)

        # click the pin icons to pin
        pin_icon_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_frame_pin_icon'")
        self.assertEqual(len(pin_icon_images), NUM_PIN_ICONS)
        await pin_icon_images[1].click()
        await ui_test.human_delay()

        # ensure the pin label is accurate
        pin_labels = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='pin_label_text'")
        self.assertEqual(pin_labels[0].widget.text, "Looks/mat_BC868CE5A075ABB1")

        # change selection to the mesh reference in USD context and selection tree
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        await item_prims[0].click()
        await ui_test.human_delay()

        # material properties should still be visible since pinned
        self.assertTrue(frame_material.widget.visible)

        # ensure the pin label is still accurate
        pin_labels = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='pin_label_text'")
        self.assertEqual(pin_labels[0].widget.text, "Looks/mat_BC868CE5A075ABB1")

        # click the pin icons to un-pin
        pin_icon_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_frame_pin_icon'")
        await pin_icon_images[1].click()
        await ui_test.human_delay()

        # material properties should no longer be visible since un-pinned
        self.assertFalse(frame_material.widget.visible)

        # ensure the pin label is now empty
        pin_labels = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='pin_label_text'")
        self.assertListEqual(pin_labels, [])

        await self.__destroy(_window, _wid)

    async def test_object_and_material_pin_labels_exist(self):
        # setup
        _window, _wid = await self.__setup_widget("test_object_and_material_pin_labels_exist")

        # ensure the material frame exists
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        self.assertIsNotNone(frame_material)

        # select a mesh and ensure the material properties are visible
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)
        self.assertTrue(frame_material.widget.visible)

        # click the pin icons to pin and reveal text
        pin_icon_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_frame_pin_icon'")
        self.assertEqual(len(pin_icon_images), NUM_PIN_ICONS)
        for pin_icon_image in pin_icon_images:
            await pin_icon_image.click()
            await ui_test.human_delay()

        # ensure the pin label texts are not empty
        pin_label_texts = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='pin_label_text'")
        for pin_label_text in pin_label_texts:
            self.assertNotEqual(pin_label_text, "")

        await self.__destroy(_window, _wid)

    async def test_layer_validation_new_layer(self):
        # setup
        _window, _wid = await self.__setup_widget("test_layer_validation_new_layer")

        property_pane_items = ui_test.find_all(f"{_window.title}//Frame/**/ScrollingFrame[*]=='PropertiesPaneSection'")
        await property_pane_items[1].click()
        await ui_test.human_delay(50)

        # Layers are expanded by default, select the sublayer
        layer_items = ui_test.find_all(f"{_window.title}//Frame/**/ZStack[*].identifier=='layer_item_root'")
        await layer_items[1].click()
        await ui_test.human_delay(50)

        create_button = ui_test.find(f"{_window.title}//Frame/**/Image[*].name=='CreateLayer'")
        await create_button.click()
        await ui_test.human_delay(10)

        # The create new file window should now be opened
        file_picker_window_title = "Create a new layer file"
        create_button = ui_test.find(f"{file_picker_window_title}//Frame/**/Button[*].text=='Create'")
        dir_path_field = ui_test.find(
            f"{file_picker_window_title}//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
        )
        file_name_field = ui_test.find(
            f"{file_picker_window_title}//Frame/**/StringField[*].style_type_name_override=='Field'"
        )

        self.assertIsNotNone(create_button)
        self.assertIsNotNone(dir_path_field)
        self.assertIsNotNone(file_name_field)

        dir_path = Path(self.temp_dir.name)
        dir_name = str(dir_path.resolve())
        file_name = "test.usda"

        # It takes a while for the tree to update
        await ui_test.human_delay(50)
        await dir_path_field.input(dir_name, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(50)

        await file_name_field.input(file_name, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()

        # Make sure we create the layer in the correct directory
        self.assertEqual(dir_name + "/", dir_path_field.model._path)
        self.assertEqual(file_name, file_name_field.model.get_value_as_string())

        await create_button.click()

        await ui_test.human_delay()

        layer_path = dir_path / file_name
        self.assertTrue(layer_path.exists())

        await self.__destroy(_window, _wid)

    async def test_layer_validation_import_layer(self):
        # setup
        _window, _wid = await self.__setup_widget("test_layer_validation_import_layer")

        property_pane_items = ui_test.find_all(f"{_window.title}//Frame/**/ScrollingFrame[*]=='PropertiesPaneSection'")
        await property_pane_items[1].click()
        await ui_test.human_delay(50)

        # Layers are expanded by default, select the sublayer
        layer_items = ui_test.find_all(f"{_window.title}//Frame/**/ZStack[*].identifier=='layer_item_root'")
        await layer_items[1].click()
        await ui_test.human_delay(50)

        import_layer_button = ui_test.find(f"{_window.title}//Frame/**/Image[*].name=='ImportLayer'")
        await import_layer_button.click()
        await ui_test.human_delay(50)

        # The create new file window should now be opened
        file_picker_window_title = "Select an existing layer file"
        select_button = ui_test.find(f"{file_picker_window_title}//Frame/**/Button[*].text=='Select'")
        dir_path_field = ui_test.find(
            f"{file_picker_window_title}//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
        )
        file_name_field = ui_test.find(
            f"{file_picker_window_title}//Frame/**/StringField[*].style_type_name_override=='Field'"
        )

        self.assertIsNotNone(select_button)
        self.assertIsNotNone(dir_path_field)
        self.assertIsNotNone(file_name_field)

        dir_path = Path(self.temp_dir.name)
        dir_name = str(dir_path.resolve())
        file_name = "test.usda"
        layer_path = dir_path / file_name
        layer_path.touch()
        layer_path.write_text("#usda 1.0")

        # It takes a while for the tree to update
        await ui_test.human_delay(50)
        await dir_path_field.input(dir_name, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(50)

        await file_name_field.input(file_name, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()

        await select_button.click()
        await ui_test.human_delay(50)

        layer_labels = [label.widget.text for label in self.__visible(f"{_window.title}//Frame/**/Label[*]")]
        self.assertIn(file_name, layer_labels)

        await self.__destroy(_window, _wid)

    async def test_layer_validation_import_invalid_layer(self):
        # setup
        _window, _wid = await self.__setup_widget("test_layer_validation_import_invalid_layer")

        property_pane_items = ui_test.find_all(f"{_window.title}//Frame/**/ScrollingFrame[*]=='PropertiesPaneSection'")
        await property_pane_items[1].click()
        await ui_test.human_delay(50)

        # Layers are expanded by default, select the sublayer
        layer_items = ui_test.find_all(f"{_window.title}//Frame/**/ZStack[*].identifier=='layer_item_root'")
        await layer_items[1].click()
        await ui_test.human_delay(50)

        import_layer_button = ui_test.find(f"{_window.title}//Frame/**/Image[*].name=='ImportLayer'")
        await import_layer_button.click()
        await ui_test.human_delay(50)

        # The create new file window should now be opened
        file_picker_window_title = "Select an existing layer file"
        select_button = ui_test.find(f"{file_picker_window_title}//Frame/**/Button[*].text=='Select'")
        dir_path_field = ui_test.find(
            f"{file_picker_window_title}//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
        )
        file_name_field = ui_test.find(
            f"{file_picker_window_title}//Frame/**/StringField[*].style_type_name_override=='Field'"
        )

        self.assertIsNotNone(select_button)
        self.assertIsNotNone(dir_path_field)
        self.assertIsNotNone(file_name_field)

        dir_path = Path(self.temp_dir.name)
        dir_name = str(dir_path.resolve())
        file_name = "test.usda"
        layer_path = dir_path / file_name
        layer_path.touch()

        # It takes a while for the tree to update
        await ui_test.human_delay(50)
        await dir_path_field.input(dir_name, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(50)

        await file_name_field.input(file_name, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()

        await select_button.click()
        await ui_test.human_delay(50)

        buttons = []
        for other_window in ui.Workspace.get_windows():
            button = ui_test.find(f"{other_window.title}//Frame/**/Button[*].text=='Okay'")
            if button:
                buttons.append(button)

        # Making sure that we are hitting a message dialog
        self.assertEqual(len(buttons), 1)
        await buttons[0].click()
        await ui_test.human_delay(3)

        file_browser = ui_test.find(file_picker_window_title)
        file_browser.widget.destroy()

        await self.__destroy(_window, _wid)

    async def test_layers_panel_expanded_by_default(self):
        """Test that the LAYERS panel expands root by default to show sublayers (regression test)."""
        # setup widget
        _window, _wid = await self.__setup_widget("test_layers_panel_expanded_by_default")

        await ui_test.human_delay(50)

        # Find all layer item labels in the layers panel
        layer_labels = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].name=='PropertiesPaneSectionTreeItem'")

        # Should have more than 1 layer visible (root layer should be expanded to show sublayers)
        layer_names = [label.widget.text for label in layer_labels]
        self.assertGreater(
            len(layer_labels), 1, f"Root layer should be expanded to show sublayers. Found only: {layer_names}"
        )

        await self.__destroy(_window, _wid)
