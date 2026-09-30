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

import pathlib
import shutil
import tempfile
from typing import Any
from unittest.mock import AsyncMock, patch

import omni.usd
from carb.input import KeyboardInput
from lightspeed.common import constants
from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from lightspeed.trex.asset_pipeline.core.jobs import MeshOptimizationJob
from lightspeed.trex.comfyui.core.api import ComfyUIAPI
from lightspeed.trex.comfyui.core.core import ComfyUICore
from lightspeed.trex.comfyui.core.enums import MeshReferenceSelection, OutputApplyBehavior, RemixType
from lightspeed.trex.comfyui.core.models import ComfyUIFileResult
from lightspeed.trex.comfyui.core.resolvers import SelectedMeshResolver, SelectedTextureResolver
from lightspeed.trex.selection_tree.widget import SetupUI as SelectionPanel
from omni import ui
from omni.flux.job_queue.core import handlers
from omni.flux.job_queue.core.apply_executor import ApplyExecutor
from omni.flux.job_queue.core.enums import ApplyDisposition, JobState
from omni.flux.job_queue.core.execute import JobScheduler
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.models import QueueJob
from omni.flux.utils.tests.context_managers import get_test_data_path
from omni.flux.utils.tests.projects import copy_test_project_to_temp
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd, UsdGeom

from ...workflow.widget import WorkflowSetupWidget
from .combo import combo_labels, select_combo_item

__all__ = ("TestMeshWorkflowSelectionPanelUIE2E", "TestMeshWorkflowUIE2E")

_OWNER = f"{constants.MESH_PATH}0AB745B8BEE1F16B"
# The viewport selects an instance. RTX Remix reads replacements from the prototype mesh only.
_INSTANCE = f"{constants.INSTANCE_PATH}0AB745B8BEE1F16B_0"
_MATERIAL = f"{constants.ROOTNODE_LOOKS}/{constants.MATERIAL_NAME_PREFIX}0AB745B8BEE1F16B"
_WORKFLOW_NAME = "mesh_uplift_ui_e2e"
_WORKFLOW_DISPLAY = "Mesh Uplift UI E2E"
_EXPORT_NODE = "626"
_TEXTURE_NODE = "11"
_GENERATED_MODEL = "generated_model.usda"
# The shared quad model references this texture relative to the model file.
_MODEL_TEXTURE = pathlib.Path("textures/source_albedo.png")
_WINDOW_WIDTH = ui.Pixel(900)
_WINDOW_HEIGHT = ui.Pixel(900)


def _copy_model_fixture(destination: pathlib.Path, texture: pathlib.Path) -> None:
    """Copy the shared textured quad model and the texture it references.

    Args:
        destination: Model file path to create.
        texture: Existing texture file copied to the path the model references.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(get_test_data_path("textured_quad.usda", "lightspeed.trex.comfyui.core").path, destination)
    texture_destination = destination.parent / _MODEL_TEXTURE
    texture_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(texture, texture_destination)


_CAPTURE_USDA = f"""#usda 1.0
(
)

def Xform "RootNode"
{{
    def Scope "meshes"
    {{
        def Xform "{Sdf.Path(_OWNER).name}"
        {{
        }}
    }}

    def Scope "instances"
    {{
        def Xform "{Sdf.Path(_INSTANCE).name}" (
            prepend references = <{_OWNER}>
        )
        {{
        }}
    }}
}}
"""

_MOD_USDA = f"""#usda 1.0
(
)

over "RootNode"
{{
    over "meshes"
    {{
        over "{Sdf.Path(_OWNER).name}" (
            prepend references = @./model.usda@
        )
        {{
            rel material:binding = <{_MATERIAL}> (
                bindMaterialAs = "strongerThanDescendants"
            )
        }}
    }}

    def Scope "Looks"
    {{
        def Material "{Sdf.Path(_MATERIAL).name}"
        {{
            token outputs:mdl:surface.connect = <{_MATERIAL}/Shader.outputs:out>

            def Shader "Shader"
            {{
                uniform token info:implementationSource = "sourceAsset"
                uniform asset info:mdl:sourceAsset = @AperturePBR_Opacity.mdl@
                uniform token info:mdl:sourceAsset:subIdentifier = "AperturePBR_Opacity"
                asset inputs:diffuse_texture = @./textures/source_albedo.png@
                token outputs:out (
                    renderType = "material"
                )
            }}
        }}
    }}
}}
"""

# The API prompt the node pack ships for a mesh uplift workflow: one tagged mesh input that is also the tagged
# mesh output, and one tagged texture input.
_API_WORKFLOW: dict[str, Any] = {
    _EXPORT_NODE: {
        "inputs": {"mesh_file_path": "", "filename_prefix": "3D/n1x", "output_format": "same"},
        "class_type": "RTXRemixExportMeshNode",
        "_meta": {
            "title": "RTX Remix Export Mesh",
            "rtx-remix": {
                "output": {"name": "Upscaled Mesh", "type": "str", "remix_type": "mesh_file_path", "order": 1},
                "inputs": {
                    "mesh_file_path": {"name": "Input Mesh", "type": "str", "remix_type": "mesh_file_path", "order": 1}
                },
            },
        },
    },
    _TEXTURE_NODE: {
        "inputs": {"image": "example.png"},
        "class_type": "LoadImage",
        "_meta": {
            "title": "Load Image",
            "rtx-remix": {
                "inputs": {"image": {"name": "Input Texture", "type": "str", "remix_type": "texture_file_path"}}
            },
        },
    },
}

_CATALOG = {
    "workflows": {
        "api": {"rtx-remix": [], "user": [{"name": _WORKFLOW_NAME, "displayName": _WORKFLOW_DISPLAY}]},
        "full": {"rtx-remix": [], "user": []},
    }
}


class _ComfyUIHarness:
    """Shared ComfyUI HTTP stand-ins, isolated queue, core, and workflow widget for the mesh UI tests.

    Coverage limit: no ComfyUI server runs in CI. The ComfyUI HTTP client (ping, catalog, workflow data, upload,
    prompt submission, completion history, download) returns recorded responses. These tests do not cover that
    service path. They cover the widget, the prompt the toolkit builds, the queue, the optimization pipeline, Apply,
    Revert, and USD.
    """

    _api_workflow: dict[str, Any] = _API_WORKFLOW

    def _start_harness(self) -> None:
        """Patch the ComfyUI client, isolate the queue, and build the workflow widget in a test window."""
        self._fixture_texture = pathlib.Path(
            get_test_data_path("textures/Normal_Map_Test_DirectX.png", "omni.flux.utils.octahedral_converter").path
        )
        self._uploads: list[str] = []
        self._submitted_prompts: list[dict[str, Any]] = []
        for started_patch in (
            patch.object(ComfyUIAPI, "ping", new=AsyncMock(return_value={})),
            patch.object(ComfyUIAPI, "get_workflow_types", new=AsyncMock(return_value=[])),
            patch.object(ComfyUIAPI, "_send_request", new=AsyncMock(return_value=_CATALOG)),
            patch.object(ComfyUIAPI, "get_workflow_data", new=AsyncMock(return_value=(self._api_workflow, {}))),
            patch.object(ComfyUIAPI, "upload_file", new=AsyncMock(side_effect=self._upload_file)),
            patch.object(ComfyUIAPI, "submit_prompt", new=AsyncMock(side_effect=self._submit_prompt)),
            patch.object(ComfyUIAPI, "wait_for_prompt_completion", new=AsyncMock(side_effect=self._get_history)),
            patch.object(ComfyUIAPI, "download_file", new=AsyncMock(side_effect=self._download_file)),
        ):
            started_patch.start()
            self.addCleanup(started_patch.stop)
        self._dialogs: list[tuple[str, str]] = []
        dialog_patch = patch(
            "lightspeed.trex.comfyui.widget.workflow.widget._TrexMessageDialog", side_effect=self._capture_dialog
        )
        dialog_patch.start()
        self.addCleanup(dialog_patch.stop)

        self._interface = QueueInterface(str(self._temp_path / "queue.sqlite"))
        queue_patch = patch("lightspeed.trex.comfyui.core.core.get_job_queue", return_value=self._interface)
        queue_patch.start()
        self.addCleanup(queue_patch.stop)

        self._core = ComfyUICore("")
        self.addCleanup(self._core.destroy)
        self._window = ui.Window(type(self).__name__, visible=True, width=_WINDOW_WIDTH, height=_WINDOW_HEIGHT)
        with patch("lightspeed.trex.comfyui.widget.workflow.widget.get_comfyui_core_instance", return_value=self._core):
            with self._window.frame:
                self._widget = WorkflowSetupWidget(context_name="")
        self.addCleanup(self._widget.destroy)
        self.addCleanup(self._window.destroy)

    def _capture_dialog(self, message: str, title: str = "", **_kwargs) -> None:
        """Record every dialog the widget raises so a failed run names its exact cause."""
        self._dialogs.append((title, message))

    async def _upload_file(self, file_path: str, **_kwargs) -> dict[str, Any]:
        """Record the file the toolkit sends to the server, the way a real upload would receive it."""
        self._uploads.append(file_path)
        return {"name": pathlib.Path(file_path).name, "subfolder": "", "type": "input"}

    async def _submit_prompt(self, prompt: dict[str, Any], *_args, **_kwargs) -> str:
        """Record the exact prompt the toolkit submits."""
        self._submitted_prompts.append(prompt)
        return f"mesh-ui-e2e-prompt-{len(self._submitted_prompts)}"

    async def _get_history(self, prompt_id: str, timeout: float) -> dict[str, Any]:
        """Report the exported model under the export node, the way the node pack publishes ``3d`` results."""
        del timeout
        return {
            prompt_id: {
                "outputs": {_EXPORT_NODE: {"3d": [{"filename": _GENERATED_MODEL, "subfolder": "", "type": "output"}]}}
            }
        }

    async def _download_file(self, file_result: ComfyUIFileResult, destination: pathlib.Path) -> pathlib.Path:
        """Deliver one real textured model to the exact local path the generation job requested."""
        self.assertIs(file_result.remix_type, RemixType.MESH_FILE_PATH)
        _copy_model_fixture(destination, self._fixture_texture)
        return destination

    def _find(self, selector: str):
        """Find one widget of the test window and assert that it exists."""
        found = ui_test.find(f"{self._window.title}//Frame/**/{selector}")
        self.assertIsNotNone(found, selector)
        return found

    async def _pick_workflow(self) -> None:
        """Select the catalog workflow through the picker popup, then wait for the core to load it."""
        await self._find("SectionedComboBox[*].identifier=='ComfyWorkflowPicker'").click()
        await ui_test.human_delay()
        entries = ui_test.find_all("SectionedComboPopup//Frame/**/Label[*].name=='SectionedComboItemLabel'")
        self.assertEqual([entry.widget.text for entry in entries], [_WORKFLOW_DISPLAY])
        await entries[0].click()
        await ui_test.human_delay(5)
        if self._widget._workflow_load_task is not None:
            await self._widget._workflow_load_task
        await ui_test.human_delay(5)

    async def _run_workflow(self) -> None:
        """Press Run Workflow and wait for the submission to settle."""
        await self._find("Button[*].identifier=='ComfyWorkflowRun'").click()
        await ui_test.human_delay(5)
        if self._widget._submit_task is not None:
            await self._widget._submit_task
        await ui_test.human_delay(5)

    async def _use_all_mesh_references(self) -> None:
        """Select the mesh input row, check that Reference Selection starts at Selected, and choose All."""
        rows = ui_test.find_all(f"{self._window.title}//Frame/**/Label[*].name=='WorkflowInputName'")
        await next(candidate for candidate in rows if candidate.widget.text == "Input Mesh").click()
        await ui_test.human_delay(5)
        combo = next(
            candidate
            for candidate in ui_test.find_all(f"{self._window.title}//Frame/**/ComboBox[*]")
            if sorted(label.lower() for label in combo_labels(candidate)) == ["all", "selected"]
        )
        labels = combo_labels(combo)
        self.assertEqual(labels[combo.widget.model.get_item_value_model().as_int].lower(), "selected")
        await select_combo_item(combo, next(label for label in labels if label.lower() == "all"))
        mesh_input = next(item for item in self._core.workflow.inputs if item.remix_type is RemixType.MESH_FILE_PATH)
        self.assertIs(mesh_input.value.reference_selection, MeshReferenceSelection.ALL)


class TestMeshWorkflowUIE2E(_ComfyUIHarness, AsyncTestCase):
    """Drive a server-catalog mesh workflow through the real widget, queue, pipeline, and Apply."""

    async def setUp(self) -> None:
        """Open one saved project with a captured mesh that references a model. See the harness coverage limit."""
        self._context = omni.usd.get_context("")
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()
        self._temp_dir = tempfile.TemporaryDirectory(prefix="comfyui-mesh-ui-e2e-")
        self.addCleanup(self._temp_dir.cleanup)
        self._temp_path = pathlib.Path(self._temp_dir.name)
        self._fixture_texture = pathlib.Path(
            get_test_data_path("textures/Normal_Map_Test_DirectX.png", "omni.flux.utils.octahedral_converter").path
        )

        _copy_model_fixture(self._temp_path / "model.usda", self._fixture_texture)
        capture_layer = Sdf.Layer.CreateNew(str(self._temp_path / "capture.usda"))
        capture_layer.ImportFromString(_CAPTURE_USDA)
        capture_layer.Save()
        mod_layer = Sdf.Layer.CreateNew(str(self._temp_path / "mod.usda"))
        mod_layer.ImportFromString(_MOD_USDA)
        mod_layer.Save()
        root_layer = Sdf.Layer.CreateNew(str(self._temp_path / "project.usda"))
        root_layer.subLayerPaths = [mod_layer.identifier, capture_layer.identifier]
        root_layer.Save()
        await self._context.open_stage_async(root_layer.identifier)
        self._stage = self._context.get_stage()
        self._mod_layer = next(
            layer
            for layer in self._stage.GetLayerStack(includeSessionLayers=False)
            if layer.identifier == mod_layer.identifier
        )
        self._stage.SetEditTarget(self._mod_layer)
        self._start_harness()

    async def tearDown(self) -> None:
        """Close the live stage. Patches, the core, the widget, and the temporary directory stop through cleanups."""
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()

    async def _set_mesh_output_behavior(self, label: str) -> None:
        """Select the mesh output row by its export name and choose one Apply behavior through its combo box popup."""
        rows = ui_test.find_all(f"{self._window.title}//Frame/**/Label[*].name=='WorkflowInputName'")
        row = next(candidate for candidate in rows if candidate.widget.text == "Upscaled Mesh")
        scroll = self._find("ScrollingFrame[*].identifier=='ComfyWorkflowItemsScroll'")
        scroll.widget.scroll_y += row.center.y - scroll.center.y
        await ui_test.human_delay()
        await row.click()
        await ui_test.human_delay(5)
        combo = self._find("ComboBox[*].identifier=='NativePropertyValue'")
        self.assertEqual(combo_labels(combo), ["Replace", "Append", "Do Nothing"])
        await select_combo_item(combo, label)

    def _remix_ref_children(self) -> list[Usd.Prim]:
        """Return the Remix reference children under the selected mesh."""
        owner = self._stage.GetPrimAtPath(_OWNER)
        return [child for child in owner.GetChildren() if child.GetAttribute(constants.IS_REMIX_REF_ATTR).Get()]

    async def test_catalog_mesh_workflow_appends_generated_model_on_selected_mesh(self) -> None:
        """The user picks a mesh workflow, sets Append, runs the selected mesh, and Apply adds the model beside it."""
        await self._core.connect()
        await ui_test.human_delay(5)
        await self._pick_workflow()

        # The server tags resolve to the Remix mesh and texture getters, and the export node is the mesh output.
        workflow = self._core.workflow
        self.assertEqual(
            {workflow_input.port_id: type(workflow_input.value) for workflow_input in workflow.inputs},
            {
                f"{_EXPORT_NODE}.inputs.mesh_file_path": SelectedMeshResolver,
                f"{_TEXTURE_NODE}.inputs.image": SelectedTextureResolver,
            },
        )
        mesh_output = next(output for output in workflow.output_specs if output.remix_type is RemixType.MESH_FILE_PATH)
        self.assertEqual(mesh_output.node_id, _EXPORT_NODE)

        # The Apply combo box drives the output behavior. End on Append.
        await self._set_mesh_output_behavior("Replace")
        self.assertIs(mesh_output.apply_behavior, OutputApplyBehavior.REPLACE)
        await self._set_mesh_output_behavior("Append")
        self.assertIs(mesh_output.apply_behavior, OutputApplyBehavior.APPEND)

        # Select the mesh the way the viewport does, through its instance, and press Run Workflow.
        self._context.get_selection().set_selected_prim_paths([_INSTANCE], True)
        await ui_test.human_delay()
        original_layer_text = self._mod_layer.ExportToString()
        await self._run_workflow()

        self.assertEqual(self._dialogs, [])
        snapshots = list(self._interface.iter_snapshot())
        self.assertEqual(
            [snapshot.job_name for snapshot in snapshots],
            ["ComfyUI generation", "Optimization preparation", "Texture optimization", "Mesh optimization"],
        )
        terminal = snapshots[-1]

        # The scheduler runs the mocked generation and the real optimization pipeline.
        scheduler = JobScheduler(self._interface)
        scheduler.start()
        try:
            await QueueJob(self._interface, terminal.graph_id, terminal.job_id).outputs(timeout=600)
        finally:
            await scheduler.stop()
        self.assertEqual(
            {snapshot.job_name: snapshot.state for snapshot in self._interface.iter_snapshot()},
            {snapshot.job_name: JobState.DONE for snapshot in snapshots},
        )

        # The toolkit uploaded the referenced model and its diffuse texture and wired both into the prompt.
        upload_names = sorted(pathlib.Path(upload).name for upload in self._uploads)
        self.assertEqual(upload_names, ["model.usda", "source_albedo.png"])
        self.assertEqual(len(self._submitted_prompts), 1)
        prompt = self._submitted_prompts[0]
        self.assertTrue(prompt[_EXPORT_NODE]["inputs"]["mesh_file_path"].endswith("model.usda"))
        self.assertTrue(prompt[_TEXTURE_NODE]["inputs"]["image"].endswith("source_albedo.png"))

        # Apply appends one Remix reference child that composes the optimized model beside the original reference.
        self.assertEqual(self._remix_ref_children(), [])
        executor = ApplyExecutor(self._interface, handlers.get_registry())
        try:
            await executor.apply(terminal.job_id)
            self.assertIs(self._interface.get_job_snapshot(terminal.job_id).apply_disposition, ApplyDisposition.APPLIED)
            self.assertEqual(
                list(self._mod_layer.GetPrimAtPath(_OWNER).referenceList.prependedItems),
                [Sdf.Reference("./model.usda")],
            )
            children = self._remix_ref_children()
            self.assertEqual(len(children), 1)
            child = children[0]
            self.assertEqual(child.GetTypeName(), "Xform")
            references = omni.usd.get_composed_references_from_prim(child)
            self.assertEqual(len(references), 1)
            reference, layer = references[0]
            self.assertIs(layer, self._mod_layer)
            generated = pathlib.Path(Sdf.ComputeAssetPathRelativeToLayer(layer, reference.assetPath))
            self.assertTrue(generated.is_file())
            self.assertEqual(generated.parent.parent.parent.name, "comfyui")
            self.assertTrue(any(prim.IsA(UsdGeom.Mesh) for prim in Usd.PrimRange(child)))
            # The instance shows the generated model through its prototype. Nothing is authored on the instance.
            instance_children = [
                prim
                for prim in self._stage.GetPrimAtPath(_INSTANCE).GetChildren()
                if prim.GetAttribute(constants.IS_REMIX_REF_ATTR).Get()
            ]
            self.assertEqual(len(instance_children), 1)
            self.assertIsNone(self._mod_layer.GetPrimAtPath(_INSTANCE))

            # Revert restores the project exactly.
            await executor.revert(terminal.job_id)
            self.assertEqual(self._mod_layer.ExportToString(), original_layer_text)
            self.assertEqual(self._remix_ref_children(), [])
        finally:
            await executor.shutdown()


_MESH_ONLY_API_WORKFLOW: dict[str, Any] = {_EXPORT_NODE: _API_WORKFLOW[_EXPORT_NODE]}
_PROJECT_MESH = "/RootNode/meshes/mesh_0AB745B8BEE1F16B"
_PROJECT_CAPTURED_MODEL = "./meshes/mesh_0AB745B8BEE1F16B.usda"
_ADDED_MODEL = "ingested_assets/output/good/cube.usda"
_FILE_PICKER = "Select a reference file"


class TestMeshWorkflowSelectionPanelUIE2E(_ComfyUIHarness, AsyncTestCase):
    """Add a reference in the Selection panel, then run a mesh workflow on a prim picked there."""

    _api_workflow = _MESH_ONLY_API_WORKFLOW

    async def setUp(self) -> None:
        """Open a copy of the example project in a Selection panel and the workflow widget."""
        self._context = omni.usd.get_context("")
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()
        temp_dir, project_url = await copy_test_project_to_temp(
            "usd/project_example/combined.usda", "lightspeed.trex.app.resources"
        )
        self.addCleanup(temp_dir.cleanup)
        self._temp_path = pathlib.Path(project_url.path).parent
        await self._context.open_stage_async(project_url.path)
        self._stage = self._context.get_stage()
        LayerManagerCore().set_edit_target_layer_of_type(LayerType.replacement)
        self._start_harness()
        self._panel_window = ui.Window("SelectionPanelE2E", visible=True, width=400, height=800)
        panel_height_patch = patch.object(SelectionPanel, "DEFAULT_TREE_FRAME_HEIGHT", 700)
        panel_height_patch.start()
        self.addCleanup(panel_height_patch.stop)
        with self._panel_window.frame:
            self._panel = SelectionPanel("")
            self._panel.show(True)
        self.addCleanup(self._panel.destroy)
        self.addCleanup(self._panel_window.destroy)
        await ui_test.human_delay(5)

    async def tearDown(self) -> None:
        """Close the file picker if a failed step left it open, then close the live stage."""
        picker = ui_test.find(_FILE_PICKER)
        if picker is not None:
            picker.widget.destroy()
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()

    def _panel_items(self, identifier: str) -> list:
        """Return the Selection panel rows with one identifier."""
        return ui_test.find_all(f"{self._panel_window.title}//Frame/**/Label[*].identifier=='{identifier}'")

    def _composed_models(self) -> set[pathlib.Path]:
        """Return the model files that the mesh prim and its marked reference children compose."""
        mesh = self._stage.GetPrimAtPath(_PROJECT_MESH)
        owners = [
            mesh,
            *(child for child in mesh.GetChildren() if child.GetAttribute(constants.IS_REMIX_REF_ATTR).Get()),
        ]
        return {
            pathlib.Path(Sdf.ComputeAssetPathRelativeToLayer(layer, reference.assetPath)).resolve()
            for owner in owners
            for reference, layer in omni.usd.get_composed_references_from_prim(owner)
        }

    async def _add_reference_through_panel(self, model_path: pathlib.Path) -> Usd.Prim:
        """Click Add new reference in the Selection panel, pick one project model, and return the new child."""
        await self._panel_items("item_add_button")[0].click()
        await ui_test.human_delay(50)
        select_button = ui_test.find(f"{_FILE_PICKER}//Frame/**/Button[*].text=='Select'")
        path_field = ui_test.find(f"{_FILE_PICKER}//Frame/**/StringField[*].identifier=='filepicker_directory_path'")
        self.assertIsNotNone(select_button)
        self.assertIsNotNone(path_field)
        await path_field.input(model_path.as_posix(), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(50)
        await select_button.click()
        await ui_test.human_delay(10)
        for title in (constants.ASSET_NEED_INGEST_WINDOW_TITLE, constants.ASSET_OUTSIDE_OF_PROJ_DIR_TITLE):
            self.assertIsNone(ui_test.find(f"{title}//Frame/**/Button[*].name=='confirm_button'"), title)
        children = [
            child
            for child in self._stage.GetPrimAtPath(_PROJECT_MESH).GetChildren()
            if child.GetAttribute(constants.IS_REMIX_REF_ATTR).Get()
        ]
        self.assertEqual(len(children), 1)
        return children[0]

    async def test_reference_added_in_the_selection_panel_gets_its_own_job_beside_the_captured_one(self) -> None:
        """Pick the captured mesh, add a reference in the panel, run: one job per reference, each in place."""
        # Arrange: select the captured geometry the way the viewport does, so the panel lists the mesh.
        self._context.get_selection().set_selected_prim_paths([f"{_PROJECT_MESH}/mesh"], True)
        await ui_test.human_delay(10)
        self.assertEqual(len(self._panel_items("item_add_button")), 2)
        added_child = await self._add_reference_through_panel(self._temp_path / _ADDED_MODEL)
        # The panel selects a prim of the new reference through the instance, the way the viewport does. Keep it:
        # it is one prim under one of the two references.
        selection = self._context.get_selection().get_selected_prim_paths()
        self.assertEqual(len(selection), 1, selection)
        self.assertIn(f"/{added_child.GetName()}/", selection[0])
        self.assertTrue(selection[0].startswith(constants.INSTANCE_PATH), selection)

        await self._core.connect()
        await ui_test.human_delay(5)
        await self._pick_workflow()
        await self._use_all_mesh_references()
        mesh_output = next(
            output for output in self._core.workflow.output_specs if output.remix_type is RemixType.MESH_FILE_PATH
        )
        self.assertIs(mesh_output.apply_behavior, OutputApplyBehavior.REPLACE)

        # Act
        await self._run_workflow()

        # Assert: two graphs, one per reference of the mesh, each targeting exactly the reference it came from.
        self.assertEqual(self._dialogs, [])
        snapshots = list(self._interface.iter_snapshot())
        self.assertEqual([snapshot.job_name for snapshot in snapshots].count("ComfyUI generation"), 2)
        terminal_snapshots = [snapshot for snapshot in snapshots if snapshot.job_name == "Mesh optimization"]
        terminal_jobs = [self._interface.get_job(snapshot.job_id) for snapshot in terminal_snapshots]
        self.assertEqual(len(terminal_jobs), 2)
        targets = []
        for job in terminal_jobs:
            reference_targets = job.apply_binding.target.reference_targets
            self.assertEqual(len(reference_targets), 1)
            targets.append((reference_targets[0].owner_prim_path, reference_targets[0].source_reference.assetPath))
        self.assertEqual(
            sorted(targets),
            sorted(
                [
                    (_PROJECT_MESH, _PROJECT_CAPTURED_MODEL),
                    (str(added_child.GetPath()), f"./{_ADDED_MODEL}"),
                ]
            ),
        )

        # Run both graphs through the real scheduler and the real optimization pipeline.
        scheduler = JobScheduler(self._interface)
        scheduler.start()
        try:
            outputs = [
                await QueueJob(self._interface, snapshot.graph_id, snapshot.job_id).outputs(timeout=600)
                for snapshot in terminal_snapshots
            ]
        finally:
            await scheduler.stop()
        generated = {pathlib.Path(output[MeshOptimizationJob.OPTIMIZED_MESH].asset_url).resolve() for output in outputs}
        self.assertEqual(len(generated), 2)
        self.assertEqual(
            {snapshot.state for snapshot in self._interface.iter_snapshot()}, {JobState.DONE}, list(self._dialogs)
        )

        # Apply each job: it replaces only the reference it was created from.
        captured = (self._temp_path / "deps" / "captures" / _PROJECT_CAPTURED_MODEL).resolve()
        added = (self._temp_path / _ADDED_MODEL).resolve()
        by_owner = {job.apply_binding.target.reference_targets[0].owner_prim_path: job for job in terminal_jobs}
        executor = ApplyExecutor(self._interface, handlers.get_registry())
        try:
            self.assertEqual(self._composed_models(), {captured, added})
            await executor.apply(by_owner[_PROJECT_MESH].job_id)
            self.assertNotIn(captured, self._composed_models())
            self.assertIn(added, self._composed_models())
            await executor.apply(by_owner[str(added_child.GetPath())].job_id)
            self.assertEqual(self._composed_models(), generated)
            # Exactly two Remix reference children: the added one, replaced in place, and one new marked child for
            # the mesh prim's own reference. No empty prim remains.
            mesh = self._stage.GetPrimAtPath(_PROJECT_MESH)
            children = [child for child in mesh.GetChildren() if child.GetAttribute(constants.IS_REMIX_REF_ATTR).Get()]
            self.assertEqual(len(children), 2)
            self.assertIn(added_child, children)
            self.assertEqual(omni.usd.get_composed_references_from_prim(mesh), [])
            for child in children:
                self.assertEqual(len(omni.usd.get_composed_references_from_prim(child)), 1)
        finally:
            await executor.shutdown()
