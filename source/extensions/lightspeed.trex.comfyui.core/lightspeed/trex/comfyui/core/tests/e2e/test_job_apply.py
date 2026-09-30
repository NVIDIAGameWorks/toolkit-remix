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
from lightspeed.common import constants
from lightspeed.trex.asset_pipeline.core.constants import VALIDATION_PASSED_KEY
from lightspeed.trex.asset_pipeline.core.jobs import MeshOptimizationJob, TextureOptimizationJob
from omni.flux.job_queue.core import handlers
from lightspeed.trex.asset_replacements.core.shared import Setup
from omni.flux.job_queue.core.apply_executor import ApplyExecutor
from omni.flux.job_queue.core.enums import ApplyDisposition, ApplyOperation, JobState
from omni.flux.job_queue.core.errors import ApplyExecutionError
from omni.flux.job_queue.core.execute import JobScheduler
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.models import QueueJob
from omni.flux.utils.common.path_utils import read_metadata
from omni.flux.utils.tests.context_managers import get_test_data_path
from omni.kit import undo
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd, UsdGeom, UsdShade

from ...api import ComfyUIAPI
from ...core import ComfyUICore
from ...enums import MeshReferenceSelection, OutputApplyBehavior, RemixType
from ...job import ComfyUIJob
from ...models import ComfyUIFileResult, Workflow, WorkflowInput, WorkflowOutput
from ...resolvers import ConstantResolver, SelectedMeshResolver, SelectedTextureResolver

_ALBEDO_OUTPUT = "albedo_output"
_ROUGHNESS_OUTPUT = "roughness_output"
_MESH_OUTPUT = "mesh_output"
_PROMPT_ID = "comfyui-e2e-prompt"
_MODEL_TEXTURE = pathlib.Path("textures/source_albedo.png")
_MODEL_FILENAME = "generated_model.usda"
_OWNER_A = f"{constants.MESH_PATH}0AB745B8BEE1F16B"
_OWNER_B = f"{constants.MESH_PATH}1BC856C9CFF2027C"
_UNSUPPORTED_MODEL_FILENAME = "generated_model.blend"


def _get_normal_fixture_path() -> pathlib.Path:
    """Return the repository's real DirectX normal-map fixture.

    Returns:
        Absolute fixture path.
    """
    return pathlib.Path(
        get_test_data_path("textures/Normal_Map_Test_DirectX.png", "omni.flux.utils.octahedral_converter").path
    )


def _copy_model_fixture(destination: pathlib.Path, texture: pathlib.Path) -> None:
    """Copy the shared textured quad model and the texture it references.

    The model is the same real fixture the asset pipeline E2E suite feeds to the optimization pipeline. Its shader
    references ``_MODEL_TEXTURE`` relative to the model file.

    Args:
        destination: Model file path to create.
        texture: Existing texture file copied to the path the model references.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(get_test_data_path("textured_quad.usda", "lightspeed.trex.comfyui.core").path, destination)
    texture_destination = destination.parent / _MODEL_TEXTURE
    texture_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(texture, texture_destination)


def _material_path(owner_path: str) -> str:
    """Return the project material bound onto one captured mesh."""
    mesh_hash = Sdf.Path(owner_path).name.removeprefix(constants.MESH_NAME_PREFIX)
    return f"{constants.ROOTNODE_LOOKS}/{constants.MATERIAL_NAME_PREFIX}{mesh_hash}"


_ALBEDO_INPUT_A = f"{_material_path(_OWNER_A)}/Shader.inputs:diffuse_texture"


def _instance_path(owner_path: str) -> str:
    """Return the first captured instance of one prototype mesh."""
    return f"{constants.INSTANCE_PATH}{Sdf.Path(owner_path).name.removeprefix(constants.MESH_NAME_PREFIX)}_0"


def _make_capture_usda(owner_paths: tuple[str, ...]) -> str:
    """Build one capture layer that defines each captured mesh prim and one instance of it, like a Remix capture.

    Args:
        owner_paths: Absolute ``/RootNode/meshes/mesh_<hash>`` prim paths.

    Returns:
        USDA content for the capture layer.
    """
    meshes = "\n".join(
        f'        def Xform "{Sdf.Path(owner_path).name}"\n        {{\n        }}' for owner_path in owner_paths
    )
    instances = "\n".join(
        f"""        def Xform "{Sdf.Path(_instance_path(owner_path)).name}" (
            prepend references = <{owner_path}>
        )
        {{
        }}"""
        for owner_path in owner_paths
    )
    return f"""#usda 1.0
(
)

def Xform "RootNode"
{{
    def Scope "meshes"
    {{
{meshes}
    }}

    def Scope "instances"
    {{
{instances}
    }}
}}
"""


def _make_project_usda(owner_paths: tuple[str, ...]) -> str:
    """Build one mod layer that references the fixture model on each captured mesh and replaces its material.

    Each owner is an ``over`` on a captured mesh that prepends the model reference. The replacement material and
    its AperturePBR shader live under ``/RootNode/Looks`` and bind onto the captured mesh prim itself, the way a
    Remix capture binds materials.

    Args:
        owner_paths: Absolute ``/RootNode/meshes/mesh_<hash>`` prim paths.

    Returns:
        USDA content for the project's edit layer.
    """
    owners = "\n".join(
        f"""        over "{Sdf.Path(owner_path).name}" (
            prepend references = @./model.usda@
        )
        {{
            rel material:binding = <{_material_path(owner_path)}> (
                bindMaterialAs = "strongerThanDescendants"
            )
        }}"""
        for owner_path in owner_paths
    )
    materials = "\n".join(
        f"""        def Material "{Sdf.Path(_material_path(owner_path)).name}"
        {{
            token outputs:mdl:surface.connect = <{_material_path(owner_path)}/Shader.outputs:out>

            def Shader "Shader"
            {{
                uniform token info:implementationSource = "sourceAsset"
                uniform asset info:mdl:sourceAsset = @AperturePBR_Opacity.mdl@
                uniform token info:mdl:sourceAsset:subIdentifier = "AperturePBR_Opacity"
                token outputs:out (
                    renderType = "material"
                )
            }}
        }}"""
        for owner_path in owner_paths
    )
    return f"""#usda 1.0
(
)

over "RootNode"
{{
    over "meshes"
    {{
{owners}
    }}

    def Scope "Looks"
    {{
{materials}
    }}
}}
"""


def _texture_output(node_id: str, texture_type: str, behavior: OutputApplyBehavior, order: int) -> WorkflowOutput:
    """Describe one tagged ComfyUI texture output.

    Args:
        node_id: Workflow node key the server reports results under.
        texture_type: ComfyUI texture semantic published by the node pack.
        behavior: Apply behavior the user configured for this output.
        order: Stable output order inside the workflow.

    Returns:
        One validated workflow output specification.
    """
    return WorkflowOutput(
        node_id=node_id,
        remix_type=RemixType.TEXTURE_FILE_PATH,
        texture_type=texture_type,
        apply_behavior=behavior,
        order=order,
    )


def _resolved_asset_path(layer: Sdf.Layer, value: Sdf.AssetPath | None) -> pathlib.Path | None:
    """Resolve one authored asset value against the layer that owns it.

    Args:
        layer: Layer holding the authored opinion.
        value: Authored asset value, or None when nothing is authored.

    Returns:
        Absolute resolved path, or None when nothing is authored.
    """
    if value is None:
        return None
    return pathlib.Path(Sdf.ComputeAssetPathRelativeToLayer(layer, value.path)).resolve()


def _workflow_request(graph) -> Any:
    """Return the workflow request literal bound to one prepared graph's generation job."""
    return next(literal.value for literal in graph.literal_inputs if literal.port is ComfyUIJob.WORKFLOW_REQUEST)


class TestComfyUIJobApplyE2E(AsyncTestCase):
    """Exercise ComfyUI Apply through real generation graphs, real pipelines, and the real Apply lane.

    Coverage limit: no ComfyUI server runs in CI. The ComfyUI HTTP client (ping, catalog, upload, prompt submission,
    completion history, download) returns recorded responses. These tests do not cover that service path. They cover
    the path after the download: queue, scheduler, optimization pipeline, Apply, Revert, and USD.
    """

    async def setUp(self) -> None:
        """Connect one core to a recorded ComfyUI HTTP boundary and prepare a temporary project directory."""
        self._context = omni.usd.get_context("")
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()
        self._temp_dir = tempfile.TemporaryDirectory(prefix="comfyui-job-apply-")
        self.addCleanup(self._temp_dir.cleanup)
        self._temp_path = pathlib.Path(self._temp_dir.name)
        self._fixture_texture = _get_normal_fixture_path()
        self._deliver_unsupported_mesh = False
        undo.clear_stack()

        # Every ComfyUI HTTP call returns a recorded response. See the class docstring for the coverage limit.
        # Each patch registers its own stop so a setUp or tearDown failure cannot leak a mock into the next test.
        for started_patch in (
            patch.object(ComfyUIAPI, "ping", new=AsyncMock(return_value={})),
            patch.object(ComfyUIAPI, "get_workflow_list", new=AsyncMock(return_value=[])),
            patch.object(ComfyUIAPI, "get_workflow_types", new=AsyncMock(return_value=[])),
            patch.object(ComfyUIAPI, "submit_prompt", new=AsyncMock(return_value=_PROMPT_ID)),
            patch.object(ComfyUIAPI, "wait_for_prompt_completion", new=AsyncMock(side_effect=self._get_history)),
            patch.object(ComfyUIAPI, "download_file", new=AsyncMock(side_effect=self._download_file)),
            patch.object(
                ComfyUIAPI,
                "upload_file",
                new=AsyncMock(return_value={"name": _MODEL_FILENAME, "subfolder": "", "type": "input"}),
            ),
        ):
            started_patch.start()
            self.addCleanup(started_patch.stop)

        self._core = ComfyUICore("")
        self.addCleanup(self._core.destroy)
        await self._core.connect()

    async def tearDown(self) -> None:
        """Release the live stage. Patches, the core, and the temporary directory stop through cleanups."""
        undo.clear_stack()
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()

    async def _get_history(self, prompt_id: str, timeout: float) -> dict[str, Any]:
        """Report one final server file for every processable output the active workflow declares.

        Args:
            prompt_id: Prompt identifier the generation job submitted.
            timeout: Unused generation timeout.

        Returns:
            ComfyUI execution history for the completed prompt.
        """
        del timeout
        outputs: dict[str, Any] = {}
        for output in self._core.workflow.output_specs:
            if output.remix_type is RemixType.TEXTURE_FILE_PATH:
                channel, filename = "images", f"{output.node_id}.png"
            else:
                channel = "3d"
                filename = _UNSUPPORTED_MODEL_FILENAME if self._deliver_unsupported_mesh else _MODEL_FILENAME
            outputs[output.node_id] = {channel: [{"filename": filename, "subfolder": "", "type": "output"}]}
        return {prompt_id: {"outputs": outputs}}

    async def _download_file(self, file_result: ComfyUIFileResult, destination: pathlib.Path) -> pathlib.Path:
        """Deliver one real generated file to the exact local path the job requested.

        Args:
            file_result: Server file metadata parsed from the prompt history.
            destination: Local artifact path owned by the generation job.

        Returns:
            The written destination path.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        if file_result.remix_type is RemixType.TEXTURE_FILE_PATH:
            shutil.copy2(self._fixture_texture, destination)
        elif self._deliver_unsupported_mesh:
            destination.write_bytes(b"not a model format RTX Remix imports")
        else:
            _copy_model_fixture(destination, self._fixture_texture)
        return destination

    async def _open_project(self, owner_paths: tuple[str, ...]) -> tuple[Usd.Stage, Sdf.Layer]:
        """Open one saved project whose captured meshes reference the real fixture model.

        The capture layer defines the mesh prims. The mod layer, the edit target, adds the model reference
        and the replacement material, the way RTX Remix authors replacements.

        Args:
            owner_paths: Captured mesh prim paths that each reference the fixture model.

        Returns:
            The live stage and its edit layer.
        """
        _copy_model_fixture(self._temp_path / "model.usda", self._fixture_texture)

        capture_layer = Sdf.Layer.CreateNew(str(self._temp_path / "capture.usda"))
        capture_layer.ImportFromString(_make_capture_usda(owner_paths))
        capture_layer.Save()
        edit_layer = Sdf.Layer.CreateNew(str(self._temp_path / "edit.usda"))
        edit_layer.ImportFromString(_make_project_usda(owner_paths))
        edit_layer.Save()

        root_layer = Sdf.Layer.CreateNew(str(self._temp_path / "project.usda"))
        root_layer.subLayerPaths = [edit_layer.identifier, capture_layer.identifier]
        root_layer.Save()
        await self._context.open_stage_async(root_layer.identifier)
        stage = self._context.get_stage()
        live_edit_layer = next(
            layer
            for layer in stage.GetLayerStack(includeSessionLayers=False)
            if layer.identifier == edit_layer.identifier
        )
        stage.SetEditTarget(live_edit_layer)
        return stage, live_edit_layer

    def _set_texture_workflow(self) -> None:
        """Select a workflow that generates one Replace texture and one Do Nothing texture."""
        self._core.set_workflow(
            Workflow(
                name="Texture generation",
                output_specs=[
                    _texture_output(_ALBEDO_OUTPUT, "albedo", OutputApplyBehavior.REPLACE, 0),
                    _texture_output(_ROUGHNESS_OUTPUT, "roughness", OutputApplyBehavior.NONE, 1),
                ],
            )
        )

    def _set_asset_workflow(
        self,
        mesh_behavior: OutputApplyBehavior,
        texture_behavior: OutputApplyBehavior = OutputApplyBehavior.REPLACE,
        reference_selection: MeshReferenceSelection = MeshReferenceSelection.ALL,
    ) -> None:
        """Select a workflow that generates one model and one texture.

        Args:
            mesh_behavior: Apply behavior configured for the generated model.
            texture_behavior: Apply behavior configured for the generated texture.
            reference_selection: Source references selected by the mesh input.
        """
        self._core.set_workflow(
            Workflow(
                name="Asset generation",
                api={"1": {"inputs": {"model": ""}}},
                inputs=[
                    WorkflowInput(
                        port_id="1.inputs.model",
                        label="Model",
                        native_type=pathlib.Path,
                        default_value=pathlib.Path(),
                        value=SelectedMeshResolver(context_name="", reference_selection=reference_selection),
                        remix_type=RemixType.MESH_FILE_PATH,
                    ),
                ],
                output_specs=[
                    _texture_output(_ALBEDO_OUTPUT, "albedo", texture_behavior, 0),
                    WorkflowOutput(
                        node_id=_MESH_OUTPUT,
                        remix_type=RemixType.MESH_FILE_PATH,
                        apply_behavior=mesh_behavior,
                        order=1,
                    ),
                ],
            )
        )

    async def _submit_generation_graph(
        self,
        prim_paths: list[str],
    ) -> tuple[QueueInterface, QueueJob, Any]:
        """Prepare one real submission through the core and persist it in an isolated queue.

        Args:
            prim_paths: Selected prim paths the user submits.

        Returns:
            The queue, the terminal Apply job handle, and its persisted Apply target.
        """
        submission = await self._core.prepare_submission(prim_paths)
        self.assertEqual(len(submission.graphs), 1)
        graph = submission.graphs[0]
        apply_jobs = [job for job in graph.jobs if job.apply_binding is not None]
        self.assertEqual(len(apply_jobs), 1)
        terminal_job = apply_jobs[0]
        interface = QueueInterface(str(self._temp_path / "queue.sqlite"))
        queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}
        return interface, queue_jobs[terminal_job.job_id], terminal_job.apply_binding.target

    async def _run_queue(self, interface: QueueInterface, queue_job: QueueJob) -> Any:
        """Run the real scheduler until the terminal job settles.

        Args:
            interface: Queue holding the submitted graph.
            queue_job: Terminal job to wait for.

        Returns:
            Durable typed outputs of the terminal job.
        """
        scheduler = JobScheduler(interface)
        scheduler.start()
        try:
            return await queue_job.outputs(timeout=600)
        finally:
            await scheduler.stop()

    @staticmethod
    def _apply_keys_written(output_url: str) -> bool:
        """Return whether Apply's own metadata keys are present for one output.

        Args:
            output_url: Published output URL to inspect.

        Returns:
            Whether the sidecar records a validation result.
        """
        return read_metadata(output_url, VALIDATION_PASSED_KEY) is not None

    @staticmethod
    def _remix_reference_children(stage: Usd.Stage, owner_path: str) -> list[Usd.Prim]:
        """Return the Remix reference children that Apply created under one owner."""
        owner = stage.GetPrimAtPath(owner_path)
        return [child for child in owner.GetChildren() if child.GetAttribute(constants.IS_REMIX_REF_ATTR).Get()]

    @staticmethod
    def _composed_reference_paths(prim: Usd.Prim) -> list[pathlib.Path]:
        """Return the resolved asset paths that one prim's composed references introduce."""
        return [
            pathlib.Path(Sdf.ComputeAssetPathRelativeToLayer(layer, reference.assetPath)).resolve()
            for reference, layer in omni.usd.get_composed_references_from_prim(prim)
        ]

    def _assert_generated_child(self, stage: Usd.Stage, owner_path: str, mesh_output: pathlib.Path) -> Usd.Prim:
        """Assert that one owner has exactly one Remix reference child that composes the generated model."""
        children = self._remix_reference_children(stage, owner_path)
        self.assertEqual(len(children), 1)
        child = children[0]
        self.assertEqual(child.GetTypeName(), "Xform")
        self.assertEqual(self._composed_reference_paths(child), [mesh_output.resolve()])
        self.assertTrue(any(prim.IsA(UsdGeom.Mesh) for prim in Usd.PrimRange(child)))
        return child

    async def test_texture_workflow_replaces_configured_output_and_revert_restores_project(self) -> None:
        """A texture workflow replaces only its Replace output, tolerates Reapply, and Reverts exactly."""
        _stage, edit_layer = await self._open_project((_OWNER_A,))
        self._set_texture_workflow()
        original_layer_text = edit_layer.ExportToString()
        interface, queue_job, target = await self._submit_generation_graph([_OWNER_A])

        # Generation and texture optimization run in the real queue. The texture job is the terminal Apply job.
        outputs = await self._run_queue(interface, queue_job)

        result = outputs[TextureOptimizationJob.PROCESSED_TEXTURES]
        processed = {item.key: item for item in result.items}
        self.assertEqual(set(processed), {_ALBEDO_OUTPUT, _ROUGHNESS_OUTPUT})
        albedo_output = pathlib.Path(processed[_ALBEDO_OUTPUT].asset_url)
        roughness_output = pathlib.Path(processed[_ROUGHNESS_OUTPUT].asset_url)
        self.assertEqual({albedo_output.suffix, roughness_output.suffix}, {".dds"})
        self.assertEqual(dict(target.texture_targets), {_ALBEDO_OUTPUT: _ALBEDO_INPUT_A})
        roughness_input = f"{_material_path(_OWNER_A)}/Shader.inputs:reflectionroughness_texture"

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            # The user applies the completed output through the Apply lane.
            await executor.apply(queue_job.job_id)

            self.assertIs(interface.get_job_snapshot(queue_job.job_id).apply_disposition, ApplyDisposition.APPLIED)
            self.assertEqual(
                _resolved_asset_path(edit_layer, edit_layer.GetAttributeAtPath(_ALBEDO_INPUT_A).default),
                albedo_output.resolve(),
            )
            # The Do Nothing output is published with metadata, but it never reaches the project.
            self.assertIsNone(edit_layer.GetAttributeAtPath(roughness_input))
            for output_path in (albedo_output, roughness_output):
                self.assertIs(read_metadata(str(output_path), VALIDATION_PASSED_KEY), True)

            # Retrying an acknowledged Apply changes nothing in the project.
            applied_layer_text = edit_layer.ExportToString()
            await executor.apply(queue_job.job_id)
            self.assertEqual(edit_layer.ExportToString(), applied_layer_text)

            # Revert restores the exact project text and drops every sidecar key Apply published.
            await executor.revert(queue_job.job_id)

            self.assertIs(interface.get_job_snapshot(queue_job.job_id).apply_disposition, ApplyDisposition.DECLINED)
            self.assertEqual(edit_layer.ExportToString(), original_layer_text)
            self.assertFalse(self._apply_keys_written(str(albedo_output)))
            self.assertFalse(self._apply_keys_written(str(roughness_output)))
        finally:
            await executor.shutdown()

    async def test_asset_workflow_appends_generated_reference_and_replaces_texture(self) -> None:
        """An Append asset workflow adds the optimized model beside the original and Reverts exactly."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        self._set_asset_workflow(OutputApplyBehavior.APPEND)
        original_layer_text = edit_layer.ExportToString()
        interface, queue_job, target = await self._submit_generation_graph([_OWNER_A])

        self.assertEqual(
            [snapshot.job_name for snapshot in interface.iter_snapshot()],
            ["ComfyUI generation", "Optimization preparation", "Texture optimization", "Mesh optimization"],
        )
        outputs = await self._run_queue(interface, queue_job)

        value = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
        mesh_output = pathlib.Path(value.asset_url)
        self.assertTrue(mesh_output.is_file())
        albedo_output = pathlib.Path(
            next(item.asset_url for item in value.texture_result.items if item.key == _ALBEDO_OUTPUT)
        )
        self.assertTrue(albedo_output.is_file())
        self.assertEqual(albedo_output.parent, mesh_output.parent)
        self.assertEqual([reference.owner_prim_path for reference in target.reference_targets], [_OWNER_A])

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)

            self.assertIs(interface.get_job_snapshot(queue_job.job_id).apply_disposition, ApplyDisposition.APPLIED)
            # Append keeps the original reference and adds one Remix reference child that composes the model.
            self.assertEqual(
                list(edit_layer.GetPrimAtPath(_OWNER_A).referenceList.prependedItems),
                [Sdf.Reference("./model.usda")],
            )
            self._assert_generated_child(stage, _OWNER_A, mesh_output)
            self.assertEqual(
                _resolved_asset_path(edit_layer, edit_layer.GetAttributeAtPath(_ALBEDO_INPUT_A).default),
                albedo_output.resolve(),
            )
            for output_path in (mesh_output, albedo_output):
                self.assertIs(read_metadata(str(output_path), VALIDATION_PASSED_KEY), True)

            # Revert removes the generated child and the texture opinion Apply authored.
            await executor.revert(queue_job.job_id)

            self.assertEqual(edit_layer.ExportToString(), original_layer_text)
            self.assertEqual(self._remix_reference_children(stage, _OWNER_A), [])
            self.assertFalse(self._apply_keys_written(str(mesh_output)))
            self.assertFalse(self._apply_keys_written(str(albedo_output)))
        finally:
            await executor.shutdown()

    async def test_asset_workflow_from_viewport_instance_appends_on_the_prototype_mesh(self) -> None:
        """Selecting an instance in the viewport targets its prototype mesh, the only place Remix reads replacements."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        self._set_asset_workflow(OutputApplyBehavior.APPEND, texture_behavior=OutputApplyBehavior.NONE)
        instance_mesh = f"{_instance_path(_OWNER_A)}/Quad"
        self.assertTrue(stage.GetPrimAtPath(instance_mesh).IsValid())

        interface, queue_job, target = await self._submit_generation_graph([instance_mesh])

        # The owner is the prototype, and its source is the real model reference, not a synthetic instance one.
        self.assertEqual([reference.owner_prim_path for reference in target.reference_targets], [_OWNER_A])
        self.assertEqual(target.reference_targets[0].source_reference, Sdf.Reference("./model.usda"))
        outputs = await self._run_queue(interface, queue_job)
        mesh_output = pathlib.Path(outputs[MeshOptimizationJob.OPTIMIZED_MESH].asset_url)

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)

            self.assertIs(interface.get_job_snapshot(queue_job.job_id).apply_disposition, ApplyDisposition.APPLIED)
            self._assert_generated_child(stage, _OWNER_A, mesh_output)
            # The instance composes the generated child through its prototype. Nothing is authored on the instance.
            self.assertEqual(len(self._remix_reference_children(stage, _instance_path(_OWNER_A))), 1)
            self.assertIsNone(edit_layer.GetPrimAtPath(_instance_path(_OWNER_A)))
        finally:
            await executor.shutdown()

    async def test_asset_workflow_replace_swaps_source_reference_with_one_undo_and_composed_revert(self) -> None:
        """A Replace asset workflow swaps the authored reference. One Undo restores the project. Revert restores
        the source model as a Remix reference child, and a second Apply/Revert cycle keeps one model composed."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        self._set_asset_workflow(OutputApplyBehavior.REPLACE)
        original_layer_text = edit_layer.ExportToString()
        interface, queue_job, _target = await self._submit_generation_graph([_OWNER_A])
        outputs = await self._run_queue(interface, queue_job)
        value = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
        mesh_output = pathlib.Path(value.asset_url)
        albedo_output = pathlib.Path(
            next(item.asset_url for item in value.texture_result.items if item.key == _ALBEDO_OUTPUT)
        )
        source_model = (self._temp_path / "model.usda").resolve()

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)

            # Replace removes the captured reference from the layer that authored it.
            self.assertEqual(list(edit_layer.GetPrimAtPath(_OWNER_A).referenceList.prependedItems), [])
            self._assert_generated_child(stage, _OWNER_A, mesh_output)
            self.assertEqual(
                _resolved_asset_path(edit_layer, edit_layer.GetAttributeAtPath(_ALBEDO_INPUT_A).default),
                albedo_output.resolve(),
            )

            # Apply authors both the reference swap and the texture in one undoable group.
            self.assertTrue(undo.undo())

            self.assertEqual(edit_layer.ExportToString(), original_layer_text)
            self.assertEqual(self._remix_reference_children(stage, _OWNER_A), [])

            # The user applies again and then Reverts through the Apply lane.
            await executor.apply(queue_job.job_id)
            self._assert_generated_child(stage, _OWNER_A, mesh_output)

            for _cycle in range(2):
                await executor.revert(queue_job.job_id)

                # Revert is composed-equivalent: the source model returns as a Remix reference child of its owner.
                children = self._remix_reference_children(stage, _OWNER_A)
                self.assertEqual(len(children), 1)
                self.assertEqual(self._composed_reference_paths(children[0]), [source_model])
                self.assertTrue(any(prim.IsA(UsdGeom.Mesh) for prim in Usd.PrimRange(children[0])))
                self.assertIsNone(edit_layer.GetAttributeAtPath(_ALBEDO_INPUT_A))
                self.assertFalse(self._apply_keys_written(str(mesh_output)))
                self.assertFalse(self._apply_keys_written(str(albedo_output)))

                # Apply after Revert replaces the restored source child: exactly one model stays composed.
                await executor.apply(queue_job.job_id)
                children = self._remix_reference_children(stage, _OWNER_A)
                self.assertEqual(len(children), 1)
                self.assertEqual(self._composed_reference_paths(children[0]), [mesh_output.resolve()])
                self._assert_generated_child(stage, _OWNER_A, mesh_output)
        finally:
            await executor.shutdown()

    async def test_asset_workflow_replace_distinguishes_same_file_prim_paths(self) -> None:
        """Selected on a prim of one same-file reference preserves the other prim path through Apply and Revert."""
        stage, _edit_layer = await self._open_project((_OWNER_A,))
        model_layer = Sdf.Layer.FindOrOpen(str(self._temp_path / "model.usda"))
        geometry_layer = Sdf.Layer.CreateNew(str(self._temp_path / "geometry.usda"))
        geometry_layer.TransferContent(model_layer)
        geometry_layer.Save()
        model_layer.Clear()
        model_layer.defaultPrim = geometry_layer.defaultPrim
        model_layer.subLayerPaths = ["geometry.usda"]
        Sdf.CreatePrimInLayer(model_layer, "/Other").specifier = Sdf.SpecifierDef
        model_layer.Save()
        owner = stage.GetPrimAtPath(_OWNER_A)
        owner.GetReferences().SetReferences(
            [Sdf.Reference("./model.usda", "/Quad"), Sdf.Reference("./model.usda", "/Other")]
        )
        self._set_asset_workflow(
            OutputApplyBehavior.REPLACE,
            texture_behavior=OutputApplyBehavior.NONE,
            reference_selection=MeshReferenceSelection.SELECTED,
        )
        # /Quad composes the Quad mesh under the owner; /Other composes nothing named Quad. Pick the Quad mesh.
        interface, queue_job, _target = await self._submit_generation_graph([f"{_OWNER_A}/Quad"])
        outputs = await self._run_queue(interface, queue_job)
        mesh_output = pathlib.Path(outputs[MeshOptimizationJob.OPTIMIZED_MESH].asset_url)
        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)
            self.assertEqual(
                [reference.primPath for reference, _layer in omni.usd.get_composed_references_from_prim(owner)],
                [Sdf.Path("/Other")],
            )
            self._assert_generated_child(stage, _OWNER_A, mesh_output)
            await executor.apply(queue_job.job_id)
            self._assert_generated_child(stage, _OWNER_A, mesh_output)
            await executor.revert(queue_job.job_id)
            children = self._remix_reference_children(stage, _OWNER_A)
            self.assertEqual(len(children), 1)
            self.assertEqual(self._composed_reference_paths(children[0]), [(self._temp_path / "model.usda").resolve()])
            self.assertEqual(
                [reference.primPath for reference, _layer in omni.usd.get_composed_references_from_prim(children[0])],
                [Sdf.Path("/Quad")],
            )
            self.assertEqual(
                [reference.primPath for reference, _layer in omni.usd.get_composed_references_from_prim(owner)],
                [Sdf.Path("/Other")],
            )
            await executor.apply(queue_job.job_id)
            self._assert_generated_child(stage, _OWNER_A, mesh_output)
        finally:
            await executor.shutdown()

    async def test_asset_workflow_replace_all_capture_references(self) -> None:
        """Replace removes both capture references even after the first replacement moves the second."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        source_model = (self._temp_path / "model.usda").resolve()
        model_layer = Sdf.Layer.FindOrOpen(str(source_model))
        Sdf.CreatePrimInLayer(model_layer, "/Other").specifier = Sdf.SpecifierDef
        model_layer.Save()
        owner = stage.GetPrimAtPath(_OWNER_A)
        owner.GetReferences().ClearReferences()
        capture_layer = next(layer for layer in stage.GetLayerStack() if layer.identifier.endswith("capture.usda"))
        with Usd.EditContext(stage, capture_layer):
            owner.GetReferences().SetReferences(
                [Sdf.Reference("./model.usda", "/Quad"), Sdf.Reference("./model.usda", "/Other")]
            )
        stage.SetEditTarget(edit_layer)
        self._set_asset_workflow(OutputApplyBehavior.REPLACE, texture_behavior=OutputApplyBehavior.NONE)
        interface, queue_job, target = await self._submit_generation_graph([_OWNER_A])
        self.assertEqual(len(target.reference_targets), 2)
        outputs = await self._run_queue(interface, queue_job)
        mesh_output = pathlib.Path(outputs[MeshOptimizationJob.OPTIMIZED_MESH].asset_url)
        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)
            self.assertEqual(self._composed_reference_paths(owner), [])
            self._assert_generated_child(stage, _OWNER_A, mesh_output)
            await executor.apply(queue_job.job_id)
            self._assert_generated_child(stage, _OWNER_A, mesh_output)
            await executor.revert(queue_job.job_id)
            children = self._remix_reference_children(stage, _OWNER_A)
            self.assertEqual(len(children), 2)
            self.assertEqual(
                [path for child in children for path in self._composed_reference_paths(child)],
                [source_model, source_model],
            )
            self.assertEqual(
                {
                    reference.primPath
                    for child in children
                    for reference, _layer in omni.usd.get_composed_references_from_prim(child)
                },
                {Sdf.Path("/Quad"), Sdf.Path("/Other")},
            )
            await executor.apply(queue_job.job_id)
            self.assertEqual(self._composed_reference_paths(owner), [])
            self._assert_generated_child(stage, _OWNER_A, mesh_output)
        finally:
            await executor.shutdown()

    async def test_asset_workflow_do_nothing_publishes_metadata_without_changing_project(self) -> None:
        """A Do Nothing asset workflow publishes every output but authors nothing in the project."""
        _stage, edit_layer = await self._open_project((_OWNER_A,))
        self._set_asset_workflow(OutputApplyBehavior.NONE, texture_behavior=OutputApplyBehavior.NONE)
        original_layer_text = edit_layer.ExportToString()
        interface, queue_job, target = await self._submit_generation_graph([_OWNER_A])
        outputs = await self._run_queue(interface, queue_job)
        value = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
        self.assertEqual(target.texture_targets, ())
        undo_depth = len(undo.get_undo_stack())

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)

            self.assertIs(interface.get_job_snapshot(queue_job.job_id).apply_disposition, ApplyDisposition.APPLIED)
            self.assertEqual(edit_layer.ExportToString(), original_layer_text)
            self.assertEqual(len(undo.get_undo_stack()), undo_depth)
            published = [value.asset_url, *(item.asset_url for item in value.texture_result.items)]
            for output_url in published:
                self.assertIs(read_metadata(output_url, VALIDATION_PASSED_KEY), True)
        finally:
            await executor.shutdown()

    async def test_asset_workflow_external_reference_edit_refuses_revert_and_keeps_the_edit(self) -> None:
        """An external edit after Apply makes Revert report a conflict and keeps the user's edit."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        self._set_asset_workflow(OutputApplyBehavior.APPEND)
        interface, queue_job, _target = await self._submit_generation_graph([_OWNER_A])
        await self._run_queue(interface, queue_job)

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)

            # The user adds another reference to the generated child after Apply finished.
            child_path = self._remix_reference_children(stage, _OWNER_A)[0].GetPath()
            destination_spec = edit_layer.GetPrimAtPath(child_path)
            reference_list_op = destination_spec.GetInfo(Sdf.PrimSpec.ReferencesKey)
            reference_list_op.appendedItems = [*reference_list_op.appendedItems, Sdf.Reference("./model.usda")]
            destination_spec.SetInfo(Sdf.PrimSpec.ReferencesKey, reference_list_op)
            externally_edited_text = edit_layer.ExportToString()

            with self.assertRaises(ApplyExecutionError) as error_context:
                await executor.revert(queue_job.job_id)

            self.assertIn("changed outside", error_context.exception.reason)
            self.assertEqual(edit_layer.ExportToString(), externally_edited_text)
            snapshot = interface.get_job_snapshot(queue_job.job_id)
            self.assertIs(snapshot.apply_operation, ApplyOperation.REVERT_FAILED)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.APPLIED)
        finally:
            await executor.shutdown()

    async def test_asset_workflow_replace_selected_first_source_preserves_the_other(self) -> None:
        """Selected on a prim of the first source replaces only that source through Apply, Revert, and Reapply."""
        await self._assert_replace_preserves_unselected_reference("Quad")

    async def test_asset_workflow_replace_selected_second_source_preserves_the_other(self) -> None:
        """Selected on a prim of the second source replaces only that source through Apply, Revert, and Reapply."""
        await self._assert_replace_preserves_unselected_reference("QuadB")

    async def test_asset_workflow_replace_all_creates_one_job_per_reference_and_replaces_each_in_place(self) -> None:
        """Picking one reference child in the Selection panel upscales every reference of the mesh, each in place."""
        # Arrange
        stage, _edit_layer = await self._open_project((_OWNER_A,))
        source_a = (self._temp_path / "model.usda").resolve()
        source_b = (self._temp_path / "model_b.usda").resolve()
        shutil.copy2(source_a, source_b)
        owner = stage.GetPrimAtPath(_OWNER_A)
        owner.GetReferences().SetReferences([Sdf.Reference("./model.usda"), Sdf.Reference("./model_b.usda")])
        self._set_asset_workflow(OutputApplyBehavior.REPLACE, texture_behavior=OutputApplyBehavior.NONE)
        # The Selection panel lists the reference children, not the mesh prim. Pick a child of one reference.
        reference_child = f"{_OWNER_A}/Quad"
        self.assertTrue(stage.GetPrimAtPath(reference_child).IsValid())

        # Act
        submission = await self._core.prepare_submission([reference_child])
        interface = QueueInterface(str(self._temp_path / "queue.sqlite"))
        jobs_by_source = {}
        for graph in submission.graphs:
            terminal = next(job for job in graph.jobs if job.apply_binding is not None)
            queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}
            source = pathlib.Path(terminal.apply_binding.target.reference_targets[0].source_reference.assetPath)
            jobs_by_source[(self._temp_path / source).resolve()] = queue_jobs[terminal.job_id]

        # Assert
        self.assertEqual(set(jobs_by_source), {source_a, source_b})
        outputs = {source: await self._run_queue(interface, job) for source, job in jobs_by_source.items()}
        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(jobs_by_source[source_a].job_id)
            self.assertEqual(self._composed_reference_paths(owner), [source_b])
            mesh_a = pathlib.Path(outputs[source_a][MeshOptimizationJob.OPTIMIZED_MESH].asset_url)
            self._assert_generated_child(stage, _OWNER_A, mesh_a)

            await executor.apply(jobs_by_source[source_b].job_id)
            self.assertEqual(self._composed_reference_paths(owner), [])
            mesh_b = pathlib.Path(outputs[source_b][MeshOptimizationJob.OPTIMIZED_MESH].asset_url)
            children = self._remix_reference_children(stage, _OWNER_A)
            self.assertEqual(
                {path for child in children for path in self._composed_reference_paths(child)},
                {mesh_a.resolve(), mesh_b.resolve()},
            )
        finally:
            await executor.shutdown()

    async def test_asset_workflow_replace_targets_the_replacement_when_the_captured_mesh_was_replaced(self) -> None:
        """A mesh whose captured reference the mod layer replaced yields one job that targets the replacement."""
        # Arrange: the capture layer references the captured mesh; the mod layer replaces the whole list.
        stage, edit_layer = await self._open_project((_OWNER_A,))
        captured = (self._temp_path / "captured.usda").resolve()
        replacement = (self._temp_path / "model.usda").resolve()
        shutil.copy2(replacement, captured)
        owner = stage.GetPrimAtPath(_OWNER_A)
        capture_layer = next(layer for layer in stage.GetLayerStack() if layer.identifier.endswith("capture.usda"))
        with Usd.EditContext(stage, capture_layer):
            owner.GetReferences().AddReference("./captured.usda")
        stage.SetEditTarget(edit_layer)
        owner.GetReferences().SetReferences([Sdf.Reference("./model.usda")])
        self.assertEqual(self._composed_reference_paths(owner), [replacement])
        self._set_asset_workflow(OutputApplyBehavior.REPLACE, texture_behavior=OutputApplyBehavior.NONE)

        # Act
        submission = await self._core.prepare_submission([f"{_OWNER_A}/Quad"])

        # Assert
        self.assertEqual(len(submission.graphs), 1)
        terminal = next(job for job in submission.graphs[0].jobs if job.apply_binding is not None)
        targets = terminal.apply_binding.target.reference_targets
        self.assertEqual([target.owner_prim_path for target in targets], [_OWNER_A])
        self.assertEqual(
            [(self._temp_path / target.source_reference.assetPath).resolve() for target in targets], [replacement]
        )
        interface = QueueInterface(str(self._temp_path / "queue.sqlite"))
        queue_job = {job.job_id: job for job in interface.submit(submission.graphs[0])}[terminal.job_id]
        outputs = await self._run_queue(interface, queue_job)
        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)
            self.assertEqual(self._composed_reference_paths(owner), [])
            self._assert_generated_child(
                stage, _OWNER_A, pathlib.Path(outputs[MeshOptimizationJob.OPTIMIZED_MESH].asset_url)
            )
        finally:
            await executor.shutdown()

    async def _assert_replace_preserves_unselected_reference(self, selected_child: str) -> None:
        """Check that Replace changes only the source reference that composes the picked prim.

        Args:
            selected_child: ``Quad`` picks a prim of ``model.usda``; ``QuadB`` picks a prim of ``model_b.usda``.
        """
        stage, edit_layer = await self._open_project((_OWNER_A,))
        source_a = (self._temp_path / "model.usda").resolve()
        source_b = (self._temp_path / "model_b.usda").resolve()
        # The second model names its mesh QuadB, so each composed child belongs to exactly one source.
        source_b.write_text(
            source_a.read_text(encoding="utf-8").replace('def Mesh "Quad"', 'def Mesh "QuadB"'), "utf-8"
        )
        owner = stage.GetPrimAtPath(_OWNER_A)
        owner.GetReferences().SetReferences([Sdf.Reference("./model.usda"), Sdf.Reference("./model_b.usda")])
        self._set_asset_workflow(
            OutputApplyBehavior.REPLACE,
            texture_behavior=OutputApplyBehavior.NONE,
            reference_selection=MeshReferenceSelection.SELECTED,
        )
        original_layer_text = edit_layer.ExportToString()
        interface, queue_job, target = await self._submit_generation_graph([f"{_OWNER_A}/{selected_child}"])
        self.assertEqual(len(target.reference_targets), 1)
        outputs = await self._run_queue(interface, queue_job)
        mesh_output = pathlib.Path(outputs[MeshOptimizationJob.OPTIMIZED_MESH].asset_url)
        unselected = source_b if selected_child == "Quad" else source_a
        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)
            self.assertEqual(set(self._composed_reference_paths(owner)), {unselected})
            self._assert_generated_child(stage, _OWNER_A, mesh_output)
            self.assertTrue(undo.undo())
            self.assertEqual(edit_layer.ExportToString(), original_layer_text)
            await executor.apply(queue_job.job_id)
            for _cycle in range(2):
                await executor.revert(queue_job.job_id)
                children = self._remix_reference_children(stage, _OWNER_A)
                self.assertEqual(len(children), 1)
                self.assertEqual(set(self._composed_reference_paths(owner)), {unselected})
                self.assertEqual(
                    set(self._composed_reference_paths(owner) + self._composed_reference_paths(children[0])),
                    {source_a, source_b},
                )
                await executor.apply(queue_job.job_id)
                self.assertEqual(set(self._composed_reference_paths(owner)), {unselected})
                self._assert_generated_child(stage, _OWNER_A, mesh_output)
        finally:
            await executor.shutdown()

    async def test_asset_workflow_changed_generated_reference_prim_path_refuses_revert_and_reapply(self) -> None:
        """A same-file reference edit preserves the edited child and blocks Apply and Revert."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        self._set_asset_workflow(OutputApplyBehavior.REPLACE, texture_behavior=OutputApplyBehavior.NONE)
        interface, queue_job, _target = await self._submit_generation_graph([_OWNER_A])
        await self._run_queue(interface, queue_job)
        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)
            child_path = self._remix_reference_children(stage, _OWNER_A)[0].GetPath()
            child_spec = edit_layer.GetPrimAtPath(child_path)
            reference, _layer = omni.usd.get_composed_references_from_prim(stage.GetPrimAtPath(child_path))[0]
            child_spec.SetInfo(
                Sdf.PrimSpec.ReferencesKey,
                Sdf.ReferenceListOp.Create([Sdf.Reference(reference.assetPath, "/Quad")]),
            )
            edited_layer_text = edit_layer.ExportToString()
            for operation in (executor.revert, executor.apply):
                with self.assertRaises(ApplyExecutionError) as error_context:
                    await operation(queue_job.job_id)
                self.assertIn("changed outside this job", error_context.exception.reason)
                self.assertEqual(edit_layer.ExportToString(), edited_layer_text)
                self.assertTrue(stage.GetPrimAtPath(child_path).IsValid())
        finally:
            await executor.shutdown()

    async def test_asset_workflow_replaced_generated_reference_url_refuses_revert_and_reapply(self) -> None:
        """After a mesh-only Replace, a generated child whose reference was swapped by hand is an external edit."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        self._set_asset_workflow(OutputApplyBehavior.REPLACE, texture_behavior=OutputApplyBehavior.NONE)
        interface, queue_job, _target = await self._submit_generation_graph([_OWNER_A])
        await self._run_queue(interface, queue_job)

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)

            # The user points the generated child at another model. The source model is still gone.
            child_path = self._remix_reference_children(stage, _OWNER_A)[0].GetPath()
            child_spec = edit_layer.GetPrimAtPath(child_path)
            child_spec.SetInfo(Sdf.PrimSpec.ReferencesKey, Sdf.ReferenceListOp.Create([Sdf.Reference("./model.usda")]))
            externally_edited_text = edit_layer.ExportToString()

            for operation in (executor.revert, executor.apply):
                with self.assertRaises(ApplyExecutionError) as error_context:
                    await operation(queue_job.job_id)
                self.assertIn("changed outside", error_context.exception.reason)
                self.assertEqual(edit_layer.ExportToString(), externally_edited_text)
        finally:
            await executor.shutdown()

    async def test_asset_workflow_on_existing_remix_reference_owner_appends_beside_it_and_reverts(self) -> None:
        """Selected on the existing Remix reference child gets the generated model as its sibling."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        # The project already has one Remix reference child under the mesh, the way Append leaves one.
        source_model = (self._temp_path / "model.usda").resolve()
        _added, existing_path = Setup("").add_new_reference(
            stage, Sdf.Path(_OWNER_A), str(source_model), Setup.get_ref_default_prim_tag(), edit_layer
        )
        self.assertEqual(self._composed_reference_paths(stage.GetPrimAtPath(existing_path)), [source_model])
        # All would also target the mesh prim's own reference; Selected keeps only the picked child.
        self._set_asset_workflow(
            OutputApplyBehavior.APPEND,
            texture_behavior=OutputApplyBehavior.NONE,
            reference_selection=MeshReferenceSelection.SELECTED,
        )
        original_layer_text = edit_layer.ExportToString()
        interface, queue_job, target = await self._submit_generation_graph([existing_path])
        outputs = await self._run_queue(interface, queue_job)
        mesh_output = pathlib.Path(outputs[MeshOptimizationJob.OPTIMIZED_MESH].asset_url)
        self.assertEqual([owner.owner_prim_path for owner in target.reference_targets], [existing_path])

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)
            await executor.apply(queue_job.job_id)

            # Setup creates the generated model as a sibling of the selected Remix reference, once.
            children = self._remix_reference_children(stage, _OWNER_A)
            self.assertEqual(len(children), 2)
            generated = [child for child in children if str(child.GetPath()) != existing_path]
            self.assertEqual(len(generated), 1)
            self.assertEqual(self._composed_reference_paths(generated[0]), [mesh_output.resolve()])
            self.assertEqual(self._composed_reference_paths(stage.GetPrimAtPath(existing_path)), [source_model])

            await executor.revert(queue_job.job_id)

            self.assertEqual(edit_layer.ExportToString(), original_layer_text)
        finally:
            await executor.shutdown()

    def _add_remix_reference_child(self, stage: Usd.Stage, edit_layer: Sdf.Layer, source: Sdf.Reference) -> str:
        """Author one Remix reference child under the fixture mesh that composes exactly ``source``.

        Args:
            stage: Live stage.
            edit_layer: Edit layer that authors the child.
            source: Reference to author on the child, relative to the edit layer.

        Returns:
            The child prim path.
        """
        _added, child_path = Setup("").add_new_reference(
            stage,
            Sdf.Path(_OWNER_A),
            str((self._temp_path / source.assetPath).resolve()),
            Setup.get_ref_default_prim_tag(),
            edit_layer,
        )
        edit_layer.GetPrimAtPath(child_path).SetInfo(Sdf.PrimSpec.ReferencesKey, Sdf.ReferenceListOp.Create([source]))
        composed = omni.usd.get_composed_references_from_prim(stage.GetPrimAtPath(child_path))
        self.assertEqual([reference for reference, _layer in composed], [source])
        return child_path

    async def test_replace_jobs_on_one_remix_owner_reapply_and_revert_independently(self) -> None:
        """Two Replace jobs retain their own state on the same Remix reference owner."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        source_a = (self._temp_path / "model.usda").resolve()
        source_b = (self._temp_path / "model_b.usda").resolve()
        shutil.copy2(source_a, source_b)
        owner_path = self._add_remix_reference_child(stage, edit_layer, Sdf.Reference("./model.usda"))
        owner = stage.GetPrimAtPath(owner_path)
        owner.GetReferences().SetReferences([Sdf.Reference("./model.usda"), Sdf.Reference("./model_b.usda")])
        self._set_asset_workflow(OutputApplyBehavior.REPLACE, texture_behavior=OutputApplyBehavior.NONE)
        submission = await self._core.prepare_submission([owner_path])
        interface = QueueInterface(str(self._temp_path / "queue.sqlite"))
        jobs = {}
        for graph in submission.graphs:
            terminal = next(job for job in graph.jobs if job.apply_binding is not None)
            submitted = {job.job_id: job for job in interface.submit(graph)}
            source = terminal.apply_binding.target.reference_targets[0].source_reference.assetPath
            jobs[(self._temp_path / source).resolve()] = submitted[terminal.job_id]
        self.assertEqual(set(jobs), {source_a, source_b})
        outputs = {source: await self._run_queue(interface, job) for source, job in jobs.items()}
        mesh_a = pathlib.Path(outputs[source_a][MeshOptimizationJob.OPTIMIZED_MESH].asset_url).resolve()
        mesh_b = pathlib.Path(outputs[source_b][MeshOptimizationJob.OPTIMIZED_MESH].asset_url).resolve()
        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(jobs[source_a].job_id)
            self.assertEqual(self._composed_reference_paths(owner), [mesh_a, source_b])
            await executor.apply(jobs[source_b].job_id)
            self.assertEqual(self._composed_reference_paths(owner), [mesh_a, mesh_b])
            await executor.apply(jobs[source_a].job_id)
            await executor.revert(jobs[source_a].job_id)
            self.assertEqual(self._composed_reference_paths(owner), [source_a, mesh_b])
            await executor.apply(jobs[source_a].job_id)
            self.assertEqual(self._composed_reference_paths(owner), [mesh_a, mesh_b])
            await executor.revert(jobs[source_b].job_id)
            self.assertEqual(self._composed_reference_paths(owner), [mesh_a, source_b])
            await executor.revert(jobs[source_a].job_id)
            self.assertEqual(self._composed_reference_paths(owner), [source_a, source_b])
        finally:
            await executor.shutdown()

    async def test_asset_workflow_replace_on_remix_reference_owner_swaps_it_in_place_and_reverts(self) -> None:
        """Replace on a ``ref_<id>`` owner swaps its reference on that prim. No sibling and no empty prim remain.
        Undo restores the layer. Revert restores the exact source on the same prim. Reapply cycles work."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        source = Sdf.Reference("./model.usda", Sdf.Path("/Quad"), Sdf.LayerOffset(2.0, 3.0), {"origin": "test"})
        source_model = (self._temp_path / "model.usda").resolve()
        owner_path = self._add_remix_reference_child(stage, edit_layer, source)
        self._set_asset_workflow(
            OutputApplyBehavior.REPLACE,
            texture_behavior=OutputApplyBehavior.NONE,
            reference_selection=MeshReferenceSelection.SELECTED,
        )
        original_layer_text = edit_layer.ExportToString()
        interface, queue_job, target = await self._submit_generation_graph([owner_path])
        self.assertEqual([owner.owner_prim_path for owner in target.reference_targets], [owner_path])
        outputs = await self._run_queue(interface, queue_job)
        mesh_output = pathlib.Path(outputs[MeshOptimizationJob.OPTIMIZED_MESH].asset_url).resolve()
        owner = stage.GetPrimAtPath(owner_path)

        def assert_replaced_in_place() -> None:
            # The owner is the only Remix reference child, it composes the generated model, and the mesh prim's
            # own reference is untouched.
            self.assertEqual(
                [str(child.GetPath()) for child in self._remix_reference_children(stage, _OWNER_A)], [owner_path]
            )
            self.assertEqual(self._composed_reference_paths(owner), [mesh_output])
            self.assertEqual(omni.usd.get_composed_references_from_prim(owner)[0][0].primPath, Sdf.Path.emptyPath)
            self.assertEqual(self._composed_reference_paths(stage.GetPrimAtPath(_OWNER_A)), [source_model])
            self.assertTrue(any(prim.IsA(UsdGeom.Mesh) for prim in Usd.PrimRange(owner)))

        def assert_source_restored() -> None:
            self.assertEqual(
                [str(child.GetPath()) for child in self._remix_reference_children(stage, _OWNER_A)], [owner_path]
            )
            composed = omni.usd.get_composed_references_from_prim(owner)
            self.assertEqual(len(composed), 1)
            restored, layer = composed[0]
            self.assertEqual(
                pathlib.Path(Sdf.ComputeAssetPathRelativeToLayer(layer, restored.assetPath)).resolve(), source_model
            )
            self.assertEqual(
                (restored.primPath, restored.layerOffset, restored.customData),
                (source.primPath, source.layerOffset, source.customData),
            )
            self.assertTrue(any(prim.IsA(UsdGeom.Mesh) for prim in Usd.PrimRange(owner)))

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)
            await executor.apply(queue_job.job_id)
            assert_replaced_in_place()

            self.assertTrue(undo.undo())
            self.assertEqual(edit_layer.ExportToString(), original_layer_text)
            assert_source_restored()

            await executor.apply(queue_job.job_id)
            assert_replaced_in_place()
            for _cycle in range(2):
                await executor.revert(queue_job.job_id)
                assert_source_restored()
                await executor.apply(queue_job.job_id)
                assert_replaced_in_place()
        finally:
            await executor.shutdown()

    async def test_asset_workflow_replace_all_replaces_the_mesh_reference_by_a_child_and_the_child_in_place(
        self,
    ) -> None:
        """One job per reference: the mesh prim's own reference becomes a marked child, the ``ref_<id>`` owner is
        swapped in place. Revert of each restores its source where Apply found it."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        source_a = (self._temp_path / "model.usda").resolve()
        source_b = (self._temp_path / "model_b.usda").resolve()
        shutil.copy2(source_a, source_b)
        child_owner = self._add_remix_reference_child(stage, edit_layer, Sdf.Reference("./model_b.usda"))
        self._set_asset_workflow(OutputApplyBehavior.REPLACE, texture_behavior=OutputApplyBehavior.NONE)
        mesh = stage.GetPrimAtPath(_OWNER_A)

        submission = await self._core.prepare_submission([f"{_OWNER_A}/Quad"])
        interface = QueueInterface(str(self._temp_path / "queue.sqlite"))
        jobs_by_owner = {}
        for graph in submission.graphs:
            terminal = next(job for job in graph.jobs if job.apply_binding is not None)
            queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}
            jobs_by_owner[terminal.apply_binding.target.reference_targets[0].owner_prim_path] = queue_jobs[
                terminal.job_id
            ]
        self.assertEqual(set(jobs_by_owner), {_OWNER_A, child_owner})
        outputs = {owner: await self._run_queue(interface, job) for owner, job in jobs_by_owner.items()}
        mesh_a = pathlib.Path(outputs[_OWNER_A][MeshOptimizationJob.OPTIMIZED_MESH].asset_url).resolve()
        mesh_b = pathlib.Path(outputs[child_owner][MeshOptimizationJob.OPTIMIZED_MESH].asset_url).resolve()

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(jobs_by_owner[_OWNER_A].job_id)
            await executor.apply(jobs_by_owner[child_owner].job_id)

            # Exactly two children: the pre-existing owner, swapped in place, and one new child for the mesh's
            # own reference. No empty prim.
            children = self._remix_reference_children(stage, _OWNER_A)
            self.assertEqual(len(children), 2)
            generated_child = next(child for child in children if str(child.GetPath()) != child_owner)
            self.assertEqual(self._composed_reference_paths(mesh), [])
            self.assertEqual(self._composed_reference_paths(generated_child), [mesh_a])
            self.assertEqual(self._composed_reference_paths(stage.GetPrimAtPath(child_owner)), [mesh_b])

            await executor.revert(jobs_by_owner[child_owner].job_id)
            await executor.revert(jobs_by_owner[_OWNER_A].job_id)

            children = self._remix_reference_children(stage, _OWNER_A)
            self.assertEqual(len(children), 2)
            self.assertEqual(self._composed_reference_paths(stage.GetPrimAtPath(child_owner)), [source_b])
            restored_child = next(child for child in children if str(child.GetPath()) != child_owner)
            self.assertEqual(self._composed_reference_paths(restored_child), [source_a])
        finally:
            await executor.shutdown()

    async def test_select_references_selected_uses_model_layer_stack(self) -> None:
        """Select references through root layers, sublayers, and nested assets."""
        for composition in ("root", "sublayer", "nested"):
            with self.subTest(composition=composition):
                # Arrange
                directory = self._temp_path / f"{composition}_selection"
                directory.mkdir()
                geometry = Usd.Stage.CreateNew(str(directory / "geometry.usda"))
                geometry.DefinePrim("/Model", "Xform")
                geometry.DefinePrim("/Model/Mesh", "Mesh")
                geometry.DefinePrim("/Other", "Xform")
                geometry.DefinePrim("/Other/Outside", "Mesh")
                geometry.GetRootLayer().Save()
                model = Sdf.Layer.CreateNew(str(directory / "model.usda"))
                if composition == "sublayer":
                    model.subLayerPaths = ["geometry.usda"]
                elif composition == "nested":
                    nested = Usd.Stage.Open(model)
                    nested.DefinePrim("/Model", "Xform").GetReferences().AddReference("geometry.usda", "/Model")
                    nested.DefinePrim("/Other", "Xform").GetReferences().AddReference("geometry.usda", "/Other")
                else:
                    model.TransferContent(geometry.GetRootLayer())
                model.defaultPrim = "Model"
                model.Save()
                stage = Usd.Stage.CreateNew(str(directory / "stage.usda"))
                owner = stage.DefinePrim("/Owner", "Xform")
                reference = Sdf.Reference("model.usda")
                owner.GetReferences().AddReference(reference)
                other = stage.DefinePrim("/OtherOwner", "Xform")
                other_reference = Sdf.Reference("model.usda", "/Other")
                other.GetReferences().AddReference(other_reference)
                child = stage.DefinePrim("/Owner/ref_1", "Xform")
                child.CreateAttribute(constants.IS_REMIX_REF_ATTR, Sdf.ValueTypeNames.Bool).Set(True)
                child.GetReferences().AddReference(reference)
                local = stage.DefinePrim("/Local", "Xform")
                references = [
                    (owner, reference, stage.GetRootLayer()),
                    (other, other_reference, stage.GetRootLayer()),
                    (child, reference, stage.GetRootLayer()),
                ]
                cases = (
                    (stage.GetPrimAtPath("/Owner/Mesh"), [0]),
                    (stage.GetPrimAtPath("/Owner/ref_1/Mesh"), [2]),
                    (local, []),
                    (stage.GetPrimAtPath("/OtherOwner/Outside"), [1]),
                )

                # Act
                selected = [
                    SelectedMeshResolver.select_references(references, MeshReferenceSelection.SELECTED, prim)
                    for prim, _expected in cases
                ]
                all_references = SelectedMeshResolver.select_references(
                    references, MeshReferenceSelection.ALL, cases[0][0]
                )

                # Assert
                for chosen, (_prim, expected) in zip(selected, cases):
                    self.assertEqual([references.index(item) for item in chosen], expected)
                self.assertEqual(all_references, tuple(references))

    async def test_asset_workflow_apply_preserves_edited_source_custom_data(self) -> None:
        """Reject a source metadata edit after Revert without changing the layer."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        self._set_asset_workflow(OutputApplyBehavior.REPLACE, texture_behavior=OutputApplyBehavior.NONE)
        interface, queue_job, _target = await self._submit_generation_graph([_OWNER_A])
        await self._run_queue(interface, queue_job)
        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)
            await executor.revert(queue_job.job_id)
            restored = self._remix_reference_children(stage, _OWNER_A)
            self.assertEqual(len(restored), 1)
            source, _layer = omni.usd.get_composed_references_from_prim(restored[0])[0]
            edited = Sdf.Reference(source.assetPath, source.primPath, source.layerOffset, {"external": "edit"})
            edit_layer.GetPrimAtPath(restored[0].GetPath()).SetInfo(
                Sdf.PrimSpec.ReferencesKey, Sdf.ReferenceListOp.Create([edited])
            )
            edited_layer = edit_layer.ExportToString()

            with self.assertRaises(ApplyExecutionError) as error_context:
                await executor.apply(queue_job.job_id)

            self.assertIn("changed outside", error_context.exception.reason)
            self.assertEqual(edit_layer.ExportToString(), edited_layer)
        finally:
            await executor.shutdown()

    async def test_asset_workflow_in_place_apply_preserves_edited_source_custom_data(self) -> None:
        """Reject a source metadata edit on a Remix reference owner before Apply."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        source = Sdf.Reference("./model.usda", customData={"origin": "test"})
        owner_path = self._add_remix_reference_child(stage, edit_layer, source)
        self._set_asset_workflow(
            OutputApplyBehavior.REPLACE,
            texture_behavior=OutputApplyBehavior.NONE,
            reference_selection=MeshReferenceSelection.SELECTED,
        )
        interface, queue_job, _target = await self._submit_generation_graph([owner_path])
        await self._run_queue(interface, queue_job)
        edited = Sdf.Reference(source.assetPath, source.primPath, source.layerOffset, {"origin": "external"})
        edit_layer.GetPrimAtPath(owner_path).SetInfo(Sdf.PrimSpec.ReferencesKey, Sdf.ReferenceListOp.Create([edited]))
        edited_layer = edit_layer.ExportToString()
        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            with self.assertRaises(ApplyExecutionError) as error_context:
                await executor.apply(queue_job.job_id)

            self.assertIn("changed outside", error_context.exception.reason)
            self.assertEqual(edit_layer.ExportToString(), edited_layer)
        finally:
            await executor.shutdown()

    async def test_asset_workflow_swapped_in_place_reference_refuses_revert_and_reapply(self) -> None:
        """A ``ref_<id>`` owner whose in-place generated reference was swapped by hand is an external edit."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        owner_path = self._add_remix_reference_child(stage, edit_layer, Sdf.Reference("./model.usda"))
        self._set_asset_workflow(
            OutputApplyBehavior.REPLACE,
            texture_behavior=OutputApplyBehavior.NONE,
            reference_selection=MeshReferenceSelection.SELECTED,
        )
        interface, queue_job, _target = await self._submit_generation_graph([owner_path])
        await self._run_queue(interface, queue_job)

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)

            generated, _layer = omni.usd.get_composed_references_from_prim(stage.GetPrimAtPath(owner_path))[0]
            external_references = (
                Sdf.Reference("./model.usda"),
                Sdf.Reference(generated.assetPath, layerOffset=Sdf.LayerOffset(10, 2)),
                Sdf.Reference(generated.assetPath, customData={"user_note": "preserve"}),
            )
            for reference in external_references:
                with self.subTest(reference=reference):
                    edit_layer.GetPrimAtPath(owner_path).SetInfo(
                        Sdf.PrimSpec.ReferencesKey, Sdf.ReferenceListOp.Create([reference])
                    )
                    externally_edited_text = edit_layer.ExportToString()
                    for operation in (executor.revert, executor.apply):
                        with self.assertRaises(ApplyExecutionError) as error_context:
                            await operation(queue_job.job_id)
                        self.assertIn("changed outside", error_context.exception.reason)
                        self.assertEqual(edit_layer.ExportToString(), externally_edited_text)
        finally:
            await executor.shutdown()

    async def test_asset_workflow_two_append_jobs_on_one_owner_keep_both_results_and_revert_independently(
        self,
    ) -> None:
        """Two Append jobs for one owner each own their generated child. Reapply and Revert touch only their own."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        self._set_asset_workflow(OutputApplyBehavior.APPEND, texture_behavior=OutputApplyBehavior.NONE)
        original_layer_text = edit_layer.ExportToString()
        interface, job_a, _target = await self._submit_generation_graph([_OWNER_A])
        mesh_a = pathlib.Path((await self._run_queue(interface, job_a))[MeshOptimizationJob.OPTIMIZED_MESH].asset_url)
        interface, job_b, _target = await self._submit_generation_graph([_OWNER_A])
        mesh_b = pathlib.Path((await self._run_queue(interface, job_b))[MeshOptimizationJob.OPTIMIZED_MESH].asset_url)
        self.assertNotEqual(mesh_a, mesh_b)

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(job_a.job_id)
            await executor.apply(job_b.job_id)
            await executor.apply(job_a.job_id)

            composed = [
                self._composed_reference_paths(child) for child in self._remix_reference_children(stage, _OWNER_A)
            ]
            self.assertEqual(sorted(composed), sorted([[mesh_a.resolve()], [mesh_b.resolve()]]))

            await executor.revert(job_a.job_id)

            composed = [
                self._composed_reference_paths(child) for child in self._remix_reference_children(stage, _OWNER_A)
            ]
            self.assertEqual(composed, [[mesh_b.resolve()]])
            self.assertIs(interface.get_job_snapshot(job_b.job_id).apply_disposition, ApplyDisposition.APPLIED)

            await executor.revert(job_b.job_id)

            self.assertEqual(edit_layer.ExportToString(), original_layer_text)
        finally:
            await executor.shutdown()

    async def test_asset_workflow_gives_every_owner_of_one_model_its_own_generated_reference(self) -> None:
        """Two prims that share one model receive one job and one generated reference each."""
        stage, edit_layer = await self._open_project((_OWNER_A, _OWNER_B))
        self._set_asset_workflow(OutputApplyBehavior.APPEND, texture_behavior=OutputApplyBehavior.NONE)
        original_layer_text = edit_layer.ExportToString()
        interface, queue_job, target = await self._submit_generation_graph([_OWNER_A, _OWNER_B])
        outputs = await self._run_queue(interface, queue_job)
        mesh_output = pathlib.Path(outputs[MeshOptimizationJob.OPTIMIZED_MESH].asset_url)
        self.assertEqual(
            [reference.owner_prim_path for reference in target.reference_targets],
            [_OWNER_A, _OWNER_B],
        )

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)

            for owner_path in (_OWNER_A, _OWNER_B):
                self.assertEqual(
                    list(edit_layer.GetPrimAtPath(owner_path).referenceList.prependedItems),
                    [Sdf.Reference("./model.usda")],
                )
                self._assert_generated_child(stage, owner_path, mesh_output)

            await executor.revert(queue_job.job_id)

            self.assertEqual(edit_layer.ExportToString(), original_layer_text)
        finally:
            await executor.shutdown()

    async def test_asset_workflow_with_unsupported_generated_mesh_skips_apply_and_keeps_project_unchanged(self) -> None:
        """A generated model in a format the pipeline cannot import skips the terminal Apply and touches nothing."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        self._set_asset_workflow(OutputApplyBehavior.APPEND)
        self._deliver_unsupported_mesh = True
        original_layer_text = edit_layer.ExportToString()
        interface, queue_job, _target = await self._submit_generation_graph([_OWNER_A])

        # The real optimization pipeline rejects the delivered file, so the coordinator never completes.
        with self.assertRaises(RuntimeError):
            await self._run_queue(interface, queue_job)

        snapshot = interface.get_job_snapshot(queue_job.job_id)
        self.assertIs(snapshot.state, JobState.SKIPPED)
        self.assertIs(snapshot.apply_disposition, ApplyDisposition.NOT_APPLICABLE)
        self.assertEqual(edit_layer.ExportToString(), original_layer_text)
        self.assertEqual(self._remix_reference_children(stage, _OWNER_A), [])

    async def test_asset_workflow_mesh_do_nothing_replaces_texture_and_never_touches_references(self) -> None:
        """A mesh Do Nothing workflow with a Replace texture authors only the texture. Revert restores only it."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        self._set_asset_workflow(OutputApplyBehavior.NONE)
        original_layer_text = edit_layer.ExportToString()
        interface, queue_job, _target = await self._submit_generation_graph([_OWNER_A])
        outputs = await self._run_queue(interface, queue_job)
        value = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
        albedo_output = pathlib.Path(
            next(item.asset_url for item in value.texture_result.items if item.key == _ALBEDO_OUTPUT)
        )

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)

            self.assertEqual(
                _resolved_asset_path(edit_layer, edit_layer.GetAttributeAtPath(_ALBEDO_INPUT_A).default),
                albedo_output.resolve(),
            )
            self.assertEqual(self._remix_reference_children(stage, _OWNER_A), [])
            self.assertEqual(
                list(edit_layer.GetPrimAtPath(_OWNER_A).referenceList.prependedItems),
                [Sdf.Reference("./model.usda")],
            )

            await executor.revert(queue_job.job_id)

            self.assertEqual(edit_layer.ExportToString(), original_layer_text)
            self.assertEqual(self._remix_reference_children(stage, _OWNER_A), [])
        finally:
            await executor.shutdown()

    async def test_asset_workflow_replace_revert_restores_source_prim_path_and_layer_offset(self) -> None:
        """Revert of a Replace composes the source reference with its captured primPath and layerOffset."""
        stage, edit_layer = await self._open_project((_OWNER_A,))
        source_prim_path = Sdf.Path("/Quad")
        source_offset = Sdf.LayerOffset(2.0, 3.0)
        edit_layer.GetPrimAtPath(_OWNER_A).referenceList.prependedItems = [
            Sdf.Reference("./model.usda", source_prim_path, source_offset)
        ]
        self._set_asset_workflow(OutputApplyBehavior.REPLACE, texture_behavior=OutputApplyBehavior.NONE)
        interface, queue_job, _target = await self._submit_generation_graph([_OWNER_A])
        outputs = await self._run_queue(interface, queue_job)
        mesh_output = pathlib.Path(outputs[MeshOptimizationJob.OPTIMIZED_MESH].asset_url)
        source_model = (self._temp_path / "model.usda").resolve()

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)
            self._assert_generated_child(stage, _OWNER_A, mesh_output)

            await executor.revert(queue_job.job_id)

            children = self._remix_reference_children(stage, _OWNER_A)
            self.assertEqual(len(children), 1)
            composed = omni.usd.get_composed_references_from_prim(children[0])
            self.assertEqual(len(composed), 1)
            restored, layer = composed[0]
            self.assertEqual(
                pathlib.Path(Sdf.ComputeAssetPathRelativeToLayer(layer, restored.assetPath)).resolve(), source_model
            )
            self.assertEqual(restored.primPath, source_prim_path)
            self.assertEqual(restored.layerOffset, source_offset)
            self.assertTrue(any(prim.IsA(UsdGeom.Mesh) for prim in Usd.PrimRange(children[0])))
        finally:
            await executor.shutdown()

    async def test_constant_asset_workflow_has_one_apply_that_writes_sidecars_and_leaves_project_unchanged(
        self,
    ) -> None:
        """A constant-only asset workflow has one Apply. It writes mesh and texture sidecars and touches no prim."""
        _stage, edit_layer = await self._open_project((_OWNER_A,))
        model_input = WorkflowInput(
            port_id="1.inputs.model",
            label="model",
            native_type=pathlib.Path,
            default_value=pathlib.Path(),
            value=ConstantResolver(self._temp_path / "model.usda", value_type=pathlib.Path),
            remix_type=RemixType.MESH_FILE_PATH,
        )
        self._core.set_workflow(
            Workflow(
                name="Constant asset generation",
                api={"1": {"inputs": {"model": ""}}},
                inputs=[model_input],
                output_specs=[
                    _texture_output(_ALBEDO_OUTPUT, "albedo", OutputApplyBehavior.REPLACE, 0),
                    WorkflowOutput(
                        node_id=_MESH_OUTPUT,
                        remix_type=RemixType.MESH_FILE_PATH,
                        apply_behavior=OutputApplyBehavior.APPEND,
                        order=1,
                    ),
                ],
            )
        )
        original_layer_text = edit_layer.ExportToString()
        interface, queue_job, _target = await self._submit_generation_graph([])
        outputs = await self._run_queue(interface, queue_job)
        value = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
        published = [value.asset_url, *(item.asset_url for item in value.texture_result.items)]

        executor = ApplyExecutor(interface, handlers.get_registry())
        try:
            await executor.apply(queue_job.job_id)

            self.assertIs(interface.get_job_snapshot(queue_job.job_id).apply_disposition, ApplyDisposition.APPLIED)
            for output_url in published:
                self.assertIs(read_metadata(output_url, VALIDATION_PASSED_KEY), True)
            self.assertEqual(edit_layer.ExportToString(), original_layer_text)

            await executor.revert(queue_job.job_id)

            for output_url in published:
                self.assertFalse(self._apply_keys_written(output_url))
            self.assertEqual(edit_layer.ExportToString(), original_layer_text)
        finally:
            await executor.shutdown()

    async def test_asset_workflow_merges_shared_model_owners_only_when_every_input_matches(self) -> None:
        """Two owners of one model share a job only while their Selected Texture inputs resolve the same file."""
        stage, _edit_layer = await self._open_project((_OWNER_A, _OWNER_B))
        textures_directory = self._temp_path / "textures"
        shutil.copy2(self._fixture_texture, textures_directory / "other_albedo.png")
        # Selected Texture reads the material bound on the owner prim itself. Bind each owner's replacement
        # material there and give its shader an albedo input.
        albedo_inputs = {}
        for owner in (_OWNER_A, _OWNER_B):
            material = UsdShade.Material(stage.GetPrimAtPath(_material_path(owner)))
            UsdShade.MaterialBindingAPI.Apply(stage.GetPrimAtPath(owner)).Bind(material)
            albedo_inputs[owner] = UsdShade.Shader(stage.GetPrimAtPath(f"{_material_path(owner)}/Shader")).CreateInput(
                "diffuse_texture", Sdf.ValueTypeNames.Asset
            )
            albedo_inputs[owner].Set(Sdf.AssetPath("./textures/source_albedo.png"))
        self._core.set_workflow(
            Workflow(
                name="Asset generation with texture input",
                api={"1": {"inputs": {"model": "", "image": ""}}},
                inputs=[
                    WorkflowInput(
                        port_id="1.inputs.model",
                        label="model",
                        native_type=pathlib.Path,
                        default_value=pathlib.Path(),
                        value=SelectedMeshResolver(context_name=""),
                        remix_type=RemixType.MESH_FILE_PATH,
                    ),
                    WorkflowInput(
                        port_id="1.inputs.image",
                        label="image",
                        native_type=pathlib.Path,
                        default_value=pathlib.Path(),
                        value=SelectedTextureResolver(context_name=""),
                        remix_type=RemixType.TEXTURE_FILE_PATH,
                    ),
                ],
                output_specs=[
                    WorkflowOutput(
                        node_id=_MESH_OUTPUT,
                        remix_type=RemixType.MESH_FILE_PATH,
                        apply_behavior=OutputApplyBehavior.REPLACE,
                    ),
                ],
            )
        )

        # Same model, same texture: one job with both owners.
        shared = await self._core.prepare_submission([_OWNER_A, _OWNER_B])
        self.assertEqual(len(shared.graphs), 1)
        self.assertIsNone(shared.graphs[0].jobs[0].skip_reason)
        shared_target = next(job for job in shared.graphs[0].jobs if job.apply_binding).apply_binding.target
        self.assertEqual([owner.owner_prim_path for owner in shared_target.reference_targets], [_OWNER_A, _OWNER_B])
        shared_request = _workflow_request(shared.graphs[0])
        self.assertEqual(
            [pathlib.Path(binding.source).name for binding in shared_request.input_bindings],
            ["model.usda", "source_albedo.png"],
        )

        # Same model, different texture on the second owner: two jobs, each bound to its own owner and texture.
        albedo_inputs[_OWNER_B].Set(Sdf.AssetPath("./textures/other_albedo.png"))
        split = await self._core.prepare_submission([_OWNER_A, _OWNER_B])
        self.assertEqual(len(split.graphs), 2)
        owners_and_textures = []
        for graph in split.graphs:
            request = _workflow_request(graph)
            target = next(job for job in graph.jobs if job.apply_binding).apply_binding.target
            texture = next(b.source for b in request.input_bindings if b.remix_type is RemixType.TEXTURE_FILE_PATH)
            owners_and_textures.append(
                ([owner.owner_prim_path for owner in target.reference_targets], pathlib.Path(texture).name)
            )
        self.assertEqual(
            owners_and_textures,
            [([_OWNER_A], "source_albedo.png"), ([_OWNER_B], "other_albedo.png")],
        )
