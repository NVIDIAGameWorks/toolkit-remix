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

import asyncio
import pathlib
import tempfile
import threading
from unittest import mock

import lightspeed.trex.comfyui.core.extension as extension
import lightspeed.trex.comfyui.core.core as core_module
import lightspeed.trex.comfyui.core.settings as settings
from lightspeed.trex.asset_pipeline.core.job import TextureProcessingJob
from lightspeed.trex.asset_pipeline.core.models import TextureProcessingItem, TextureProcessingRequest
from lightspeed.trex.comfyui.core.apply_handler import ComfyUIJobApplyHandler
from lightspeed.trex.comfyui.core.connection import get_connected_endpoint, set_connected_endpoint
from lightspeed.trex.comfyui.core.core import (
    ComfyUICore,
    ComfyUIRetargetResult,
    ComfyUISubmission,
)
from lightspeed.trex.comfyui.core.enums import (
    WORKFLOW_TYPES_BY_CATEGORY,
    ComfyUIEventType,
    ComfyUIOperation,
    ComfyUIState,
    IntroducingLayer,
    RemixType,
    WorkflowCategory,
    WorkflowSourceType,
    WorkflowType,
)
from lightspeed.trex.comfyui.core.events import publish_comfyui_event, subscribe_comfyui_event
from lightspeed.trex.comfyui.core.job import ComfyUIJob
from lightspeed.trex.comfyui.core.models import (
    ComfyUIWorkflowRequest,
    Workflow,
    WorkflowInput,
    WorkflowOutput,
    WorkflowTypeCategory,
    WorkflowTypeOption,
)
from lightspeed.trex.comfyui.core.resolvers import (
    AllStageTexturesResolver,
    ConstantResolver,
    ResolverConfigurationError,
    ResolverValueError,
    StageExpandingResolver,
    ValueResolver,
)
from lightspeed.trex.comfyui.core.tests.unit.fixtures import get_test_workflow_pair
from omni import usd
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.enums import JobState
from omni.flux.job_queue.core.errors import QueueSubmissionError
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import JobGraph, JobOutputs
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd, UsdGeom, UsdShade

__all__ = ("TestComfyUICore",)


def _make_prim(path: str) -> mock.MagicMock:
    """Create a mock USD prim with a stable path.

    Args:
        path: USD path returned by the prim mock.

    Returns:
        A prim mock configured with the requested path.
    """
    prim = mock.MagicMock()
    prim.GetPath.return_value = path
    return prim


def _make_context(
    project_path: str = "/project/project.usda",
    edit_target: str = "/project/mod.usda",
) -> mock.MagicMock:
    """Create a mock USD context with root and edit-target layers.

    Args:
        project_path: Identifier exposed by the stage root layer.
        edit_target: Identifier exposed by the stage edit-target layer.

    Returns:
        A context mock with a stage configured for both layer identifiers.
    """
    context = mock.MagicMock()
    stage = context.get_stage.return_value
    stage.GetRootLayer.return_value.identifier = project_path
    stage.GetRootLayer.return_value.anonymous = False
    stage.GetEditTarget.return_value.GetLayer.return_value.identifier = edit_target
    stage.GetEditTarget.return_value.GetLayer.return_value.anonymous = False
    return context


def _make_material(path: str) -> mock.MagicMock:
    """Create a material mock with a stable prim identity.

    Args:
        path: USD path used to derive the material path and name.

    Returns:
        A material mock configured with the requested prim identity.
    """
    material = mock.MagicMock()
    material.GetPrim.return_value.GetPath.return_value = path
    material.GetPrim.return_value.GetName.return_value = path.rsplit("/", 1)[-1]
    return material


def _get_workflow_request(graph: JobGraph, job: ComfyUIJob) -> ComfyUIWorkflowRequest:
    """Return the exact typed literal request bound to a generated job.

    Args:
        graph: Graph containing the generation job and its literal inputs.
        job: Generation job whose request should be returned.

    Returns:
        Typed workflow request bound to the job.

    Raises:
        RuntimeError: If the graph does not contain exactly one matching request binding.
    """
    bindings = [
        binding
        for binding in graph.literal_inputs
        if binding.job_id == job.job_id and binding.port is ComfyUIJob.WORKFLOW_REQUEST
    ]
    if len(bindings) != 1 or type(bindings[0].value) is not ComfyUIWorkflowRequest:
        raise RuntimeError("ComfyUI job does not have exactly one typed workflow request")
    return bindings[0].value


def _workflow_input(
    port_id: str,
    value: ValueResolver,
    *,
    default=None,
    native_type: type = str,
    remix_type: RemixType | None = None,
) -> WorkflowInput:
    """Create one concise workflow input for core behavior tests.

    Args:
        port_id: Stable node-port identifier for the workflow input.
        value: Resolver or literal value assigned to the input.
        default: Fallback value exposed by the input.
        native_type: Python type expected by the ComfyUI node port.
        remix_type: Optional RTX Remix semantic type for the input.

    Returns:
        A workflow input configured with a label derived from its port identifier.
    """
    return WorkflowInput(
        port_id=port_id,
        label=port_id.rsplit(".", 1)[-1],
        native_type=native_type,
        default_value=default,
        value=value,
        remix_type=remix_type,
    )


class _MissingTextureResolver(ValueResolver[str]):
    """Report a user-facing missing texture without reading USD."""

    label = "Selected Texture"

    def __call__(self, prim) -> str:
        """Raise the user-facing missing-texture reason.

        Args:
            prim: Material prim whose missing texture is reported.

        Raises:
            ResolverValueError: Always, with guidance for resolving the missing input.
        """
        raise ResolverValueError("This material has no albedo texture.")


class TestComfyUICore(AsyncTestCase):
    """Test the public ComfyUI lifecycle and job-preparation behavior."""

    async def setUp(self) -> None:
        """Give each test an isolated extension instance registry."""
        self._settings_backend = mock.MagicMock()
        self._settings_backend.get.return_value = "http"
        self._settings_backend.get_as_string.return_value = "127.0.0.1"
        self._settings_backend.get_as_int.return_value = 8188
        self._settings_patch = mock.patch.object(
            settings,
            "get_settings",
            return_value=self._settings_backend,
        )
        self._settings_patch.start()
        self.addCleanup(self._settings_patch.stop)
        self._notice_listener = mock.MagicMock()
        self._tf_patch = mock.patch.object(core_module, "Tf")
        self._tf = self._tf_patch.start()
        self._tf.Notice.Register.return_value = self._notice_listener
        self.addCleanup(self._tf_patch.stop)
        self._saved_instances = extension._instances
        self._saved_shutting_down = extension._shutting_down
        self._saved_started = extension._started
        extension._instances = {}
        extension._shutting_down = False
        extension._started = False
        set_connected_endpoint("texturecraft", None)

    async def tearDown(self) -> None:
        """Restore extension globals after each test."""
        extension._instances.clear()
        extension._instances = self._saved_instances
        extension._shutting_down = self._saved_shutting_down
        extension._started = self._saved_started
        set_connected_endpoint("texturecraft", None)

    async def test_core_requires_explicit_context_name(self) -> None:
        """A missing context is rejected at construction."""
        # Arrange
        context_name = None

        # Act
        with self.assertRaises(ValueError) as error_context:
            ComfyUICore(context_name)

        # Assert
        self.assertIn("context_name", str(error_context.exception))

    async def test_core_accepts_explicit_default_context_name(self) -> None:
        """An explicitly supplied empty name selects Kit's default USD context."""
        # Arrange
        context_name = ""

        # Act
        core = ComfyUICore(context_name)

        # Assert
        self.assertEqual(core.context_name, "")

    async def test_visibility_notice_uses_core_context_name(self) -> None:
        """Visibility changes publish for the USD context supplied by the core's parent."""
        # Arrange
        context = mock.MagicMock()
        stage = context.get_stage.return_value
        notice = mock.MagicMock()
        notice.GetChangedInfoOnlyPaths.return_value = [Sdf.Path("/World/Object.visibility")]
        notice.GetResyncedPaths.return_value = []
        core = ComfyUICore("texturecraft")

        # Act
        with (
            mock.patch.object(core_module, "get_context", return_value=context) as get_context,
            mock.patch.object(core_module, "publish_comfyui_event") as publish_event,
        ):
            core._on_objects_changed(notice, stage)

        # Assert
        self._tf.Notice.Register.assert_called_once_with(Usd.Notice.ObjectsChanged, core._on_objects_changed, None)
        get_context.assert_called_once_with("texturecraft")
        publish_event.assert_called_once_with("texturecraft", ComfyUIEventType.STAGE_VISIBILITY_CHANGED)

    async def test_destroy_releases_context_visibility_listener(self) -> None:
        """Destroying a context core revokes its visibility listener."""
        # Arrange
        core = ComfyUICore("texturecraft")

        # Act
        core.destroy()

        # Assert
        self._notice_listener.Revoke.assert_called_once_with()
        self.assertIsNone(core._objects_changed_subscription)

    async def test_submission_block_reason_requires_only_a_live_stage(self) -> None:
        """New graph preparation needs a live stage but not a saved project or validated edit target."""
        # Arrange
        core = ComfyUICore("texturecraft")
        no_project = _make_context()
        no_project.get_stage.return_value = None
        unsaved_project = _make_context()
        unsaved_project.get_stage.return_value.GetRootLayer.return_value.anonymous = True
        invalid_edit_target = _make_context()
        invalid_edit_target.get_stage.return_value.HasLocalLayer.return_value = False
        cases = (
            (
                no_project,
                "Open a project to select materials for new ComfyUI jobs. Existing queued jobs can continue.",
            ),
            (unsaved_project, None),
            (invalid_edit_target, None),
            (_make_context(), None),
        )

        for context, expected_reason in cases:
            with self.subTest(expected_reason=expected_reason):
                # Act
                with mock.patch("lightspeed.trex.comfyui.core.core.get_context", return_value=context):
                    reason = core.get_submission_block_reason()

                # Assert
                self.assertEqual(reason, expected_reason)

    async def test_create_graphs_keeps_one_two_stage_graph_per_material_when_inputs_match(self) -> None:
        """Distinct materials become distinct generation-processing graphs."""
        # Arrange
        core = ComfyUICore("texturecraft")
        core._workflow = Workflow(
            name="Upscale",
            active_preset="Cinematic",
            api={"1": {"inputs": {"strength": 0.5}}},
            inputs=[_workflow_input("1.inputs.strength", ConstantResolver(0.75), default=0.5, native_type=float)],
            output_specs=[
                WorkflowOutput("99", "albedo", order=1),
                WorkflowOutput("100", "normal_ogl", order=2),
                WorkflowOutput("101", "roughness", order=3),
                WorkflowOutput("102", "metallic", order=4),
            ],
        )

        candidates = [
            (_make_material("/World/Looks/First"), ["/World/First"]),
            (_make_material("/World/Looks/Second"), ["/World/Second"]),
        ]

        with (
            mock.patch("lightspeed.trex.comfyui.core.core.get_context", return_value=_make_context()),
            mock.patch.object(
                core,
                "_capture_texture_targets",
                return_value={
                    "albedo": "/Shader.inputs:albedo",
                    "normal_ogl": "/Shader.inputs:normal",
                    "roughness": "/Shader.inputs:roughness",
                    "metallic": "/Shader.inputs:metallic",
                },
            ),
        ):
            # Act
            graphs = core._create_job_graphs_for_candidates(
                candidates,
                core._workflow,
                "/project/project.usda",
                "/project/mod.usda",
                ("http", "127.0.0.1", 8188),
                core._client_id,
            )

        # Assert
        self.assertEqual(len(graphs), 2)
        generation_jobs = [graph.jobs[0] for graph in graphs]
        processing_jobs = [graph.jobs[1] for graph in graphs]
        self.assertTrue(all(type(job) is ComfyUIJob for job in generation_jobs))
        self.assertTrue(all(type(job) is TextureProcessingJob for job in processing_jobs))
        self.assertEqual([job.material_path for job in generation_jobs], ["/World/Looks/First", "/World/Looks/Second"])
        self.assertEqual([job.prim_paths for job in generation_jobs], [["/World/First"], ["/World/Second"]])
        self.assertTrue(all(job.apply_binding is None for job in generation_jobs))
        self.assertTrue(all(job.apply_binding.handler_type is ComfyUIJobApplyHandler for job in processing_jobs))
        self.assertTrue(all(len(job.apply_binding.target.texture_targets) == 4 for job in processing_jobs))
        requests = [_get_workflow_request(graph, job) for graph, job in zip(graphs, generation_jobs, strict=True)]
        self.assertTrue(all(request.prompt["1"]["inputs"]["strength"] == 0.75 for request in requests))
        self.assertEqual([graph.name for graph in graphs], ["Upscale - Cinematic", "Upscale - Cinematic"])
        self.assertEqual([job.name for job in generation_jobs], ["ComfyUI generation", "ComfyUI generation"])
        self.assertEqual([job.name for job in processing_jobs], ["Texture optimization", "Texture optimization"])
        for graph, generation_job, processing_job in zip(graphs, generation_jobs, processing_jobs, strict=True):
            self.assertEqual(len(graph.connections), 1)
            connection = graph.connections[0]
            self.assertEqual(connection.source_job_id, generation_job.job_id)
            self.assertIs(connection.source_port, ComfyUIJob.GENERATED_TEXTURES)
            self.assertEqual(connection.target_job_id, processing_job.job_id)
            self.assertIs(connection.target_port, TextureProcessingJob.SOURCE_TEXTURES)

    async def test_create_jobs_marks_material_skipped_with_exact_resolver_reason(self) -> None:
        """An unresolved required texture remains visible as one skipped material job."""
        # Arrange
        core = ComfyUICore("texturecraft")
        workflow = Workflow(
            name="Upscale",
            api={"68": {"inputs": {"image": ""}}},
            inputs=[
                _workflow_input(
                    "68.inputs.image",
                    _MissingTextureResolver(),
                    remix_type=RemixType.TEXTURE_FILE_PATH,
                )
            ],
        )
        core._workflow = workflow

        material = _make_material("/World/Looks/Wall")

        with mock.patch("lightspeed.trex.comfyui.core.core.get_context", return_value=_make_context()):
            # Act
            graph = core._create_job_graphs_for_candidates(
                [(material, ["/World/Wall"])],
                core._workflow,
                "/project/project.usda",
                "/project/mod.usda",
                ("http", "127.0.0.1", 8188),
                core._client_id,
            )[0]

        # Assert
        generation_job, processing_job = graph.jobs
        self.assertEqual(generation_job.skip_reason, "This material has no albedo texture.")
        self.assertIsNone(processing_job.skip_reason)
        self.assertEqual(generation_job.material_path, "/World/Looks/Wall")
        self.assertEqual(generation_job.prim_paths, ["/World/Wall"])
        request = _get_workflow_request(graph, generation_job)
        self.assertEqual(request.input_bindings, ())
        self.assertIsNot(request.workflow, workflow)
        self.assertEqual(graph.name, "Upscale - Custom Settings")
        self.assertIsNone(generation_job.apply_binding)
        self.assertIs(processing_job.apply_binding.handler_type, ComfyUIJobApplyHandler)
        self.assertEqual(len(graph.connections), 1)

    async def test_create_jobs_captures_project_and_edit_target(self) -> None:
        """Jobs retain the project and edit target active at submission time."""
        # Arrange
        core = ComfyUICore("texturecraft")
        core._workflow = Workflow(
            api={"1": {"inputs": {"strength": 0.5}}},
            inputs=[_workflow_input("1.inputs.strength", ConstantResolver(0.5), native_type=float)],
            output_specs=[WorkflowOutput("99", "albedo")],
        )
        material = _make_material("/World/Looks/Wall")

        # Act
        with (
            mock.patch(
                "lightspeed.trex.comfyui.core.core.get_context",
                return_value=_make_context("/projects/scene.usda", "/projects/mod.usda"),
            ),
            mock.patch.object(
                core,
                "_capture_texture_targets",
                return_value={"albedo": "/World/Looks/Shader.inputs:diffuse_texture"},
            ),
        ):
            graph = core._create_job_graphs_for_candidates(
                [(material, ["/World/Mesh"])],
                core._workflow,
                "/projects/scene.usda",
                "/projects/mod.usda",
                ("http", "127.0.0.1", 8188),
                core._client_id,
            )[0]

        # Assert
        generation_job, processing_job = graph.jobs
        target = processing_job.apply_binding.target
        self.assertEqual(target.project_path, "/projects/scene.usda")
        self.assertEqual(target.edit_target_layer, "/projects/mod.usda")
        self.assertEqual(
            dict(target.texture_targets),
            {"albedo": "/World/Looks/Shader.inputs:diffuse_texture"},
        )
        request = _get_workflow_request(graph, generation_job)
        self.assertIn("/assets/ingested/comfyui/", request.output_url.replace("\\", "/"))

    async def test_submission_target_captures_live_anonymous_layers(self) -> None:
        """Submission captures the live layer identities without requiring a save operation."""
        # Arrange
        core = ComfyUICore("texturecraft")
        core._workflow = Workflow()
        context = _make_context("anon:project", "anon:edit-target")
        context.get_stage.return_value.GetRootLayer.return_value.anonymous = True
        context.get_stage.return_value.GetEditTarget.return_value.GetLayer.return_value.anonymous = True
        context.get_stage.return_value.HasLocalLayer.return_value = False

        # Act
        with mock.patch("lightspeed.trex.comfyui.core.core.get_context", return_value=context):
            stage, stage_identifier, edit_target_identifier = core._get_submission_target()

        # Assert
        self.assertIs(stage, context.get_stage.return_value)
        self.assertEqual(stage_identifier, "anon:project")
        self.assertEqual(edit_target_identifier, "anon:edit-target")

    async def test_anonymous_stage_uses_queue_owned_processed_output(self) -> None:
        """Anonymous-stage graphs never construct an invalid publication URL from the layer identifier."""
        # Arrange
        core = ComfyUICore("texturecraft")
        core._workflow = Workflow()
        context = _make_context("anon:project", "anon:edit-target")
        stage = context.get_stage.return_value
        stage.GetRootLayer.return_value.anonymous = True
        material = _make_material("/World/Looks/Wall")

        # Act
        with mock.patch("lightspeed.trex.comfyui.core.core.get_context", return_value=context):
            graph = core._create_job_graphs_for_candidates(
                [(material, ["/World/Mesh"])],
                core._workflow,
                "anon:project",
                "anon:edit-target",
                ("http", "127.0.0.1", 8188),
                core._client_id,
                stage=stage,
            )[0]

        # Assert
        generation_job = graph.jobs[0]
        self.assertIsNone(_get_workflow_request(graph, generation_job).output_url)

    async def test_create_jobs_preserves_json_value_types(self) -> None:
        """Resolved booleans, numbers, paths, and nulls retain their JSON meaning."""
        # Arrange
        core = ComfyUICore("texturecraft")
        readable_path = pathlib.Path(__file__)
        core._workflow = Workflow(
            api={"1": {"inputs": {"strength": 0.5, "enabled": True, "path": "", "optional": "x"}}},
            inputs=[
                _workflow_input("1.inputs.strength", ConstantResolver(0.75), native_type=float),
                _workflow_input("1.inputs.enabled", ConstantResolver(False), native_type=bool),
                _workflow_input("1.inputs.path", ConstantResolver(readable_path), native_type=pathlib.Path),
                _workflow_input("1.inputs.optional", ConstantResolver(None)),
            ],
        )

        # Act
        with (
            mock.patch("lightspeed.trex.comfyui.core.core.get_context", return_value=_make_context()),
            mock.patch.object(core, "_capture_texture_targets", return_value={"albedo": "/Shader.inputs:albedo"}),
        ):
            graph = core._create_job_graphs_for_candidates(
                [(_make_material("/World/Looks/Wall"), ["/World/Mesh"])],
                core._workflow,
                "/project/project.usda",
                "/project/mod.usda",
                ("http", "127.0.0.1", 8188),
                core._client_id,
            )[0]

        # Assert
        job = graph.jobs[0]
        request = _get_workflow_request(graph, job)
        self.assertEqual(
            request.prompt["1"]["inputs"],
            {"strength": 0.75, "enabled": False, "path": readable_path.as_posix(), "optional": None},
        )

    async def test_create_jobs_rejects_empty_file_path_constant_before_submission(self) -> None:
        """An empty file Constant is invalid workflow configuration, not a queued skipped material."""
        # Arrange
        core = ComfyUICore("texturecraft")
        core._workflow = Workflow(
            api={"1": {"inputs": {"path": "workflow-example.png"}}},
            inputs=[
                _workflow_input(
                    "1.inputs.path",
                    ConstantResolver(pathlib.Path(), value_type=pathlib.Path),
                    native_type=pathlib.Path,
                )
            ],
        )

        # Act
        with mock.patch("lightspeed.trex.comfyui.core.core.get_context", return_value=_make_context()):
            with self.assertRaisesRegex(ResolverConfigurationError, "Select a valid file"):
                core._create_job_graphs_for_candidates(
                    [(_make_material("/World/Looks/Wall"), ["/World/Mesh"])],
                    core._workflow,
                    "/project/project.usda",
                    "/project/mod.usda",
                    ("http", "127.0.0.1", 8188),
                    core._client_id,
                )

    async def test_create_jobs_skips_non_finite_json_values(self) -> None:
        """NaN and infinity cannot enter a JSON prompt payload."""
        # Arrange
        core = ComfyUICore("texturecraft")
        non_finite_values = (float("nan"), float("inf"), float("-inf"))

        for value in non_finite_values:
            with self.subTest(value=value):
                core._workflow = Workflow(
                    api={"1": {"inputs": {"strength": 0.5}}},
                    inputs=[_workflow_input("1.inputs.strength", ConstantResolver(value), native_type=float)],
                )

                # Act
                with mock.patch("lightspeed.trex.comfyui.core.core.get_context", return_value=_make_context()):
                    graph = core._create_job_graphs_for_candidates(
                        [(_make_material("/World/Looks/Wall"), ["/World/Mesh"])],
                        core._workflow,
                        "/project/project.usda",
                        "/project/mod.usda",
                        ("http", "127.0.0.1", 8188),
                        core._client_id,
                    )[0]

                # Assert
                job = graph.jobs[0]
                self.assertEqual(
                    job.skip_reason,
                    "strength has a value that this workflow cannot use. Choose a different value and try again.",
                )

    async def test_get_material_candidates_expands_parent_and_deduplicates_subset_owners(self) -> None:
        """A parent selection yields one shared material with each mesh owner exactly once."""
        # Arrange
        core = ComfyUICore("texturecraft")
        material = _make_material("/Asset/Looks/Shared")
        material.GetPrim.return_value.IsValid.return_value = True
        parent = _make_prim("/Asset")
        parent.IsValid.return_value = True
        first_mesh = _make_prim("/Asset/First")
        first_mesh.IsA.side_effect = lambda schema: schema is UsdGeom.Mesh
        subset = _make_prim("/Asset/First/Subset")
        subset.IsA.side_effect = lambda schema: schema is UsdGeom.Subset
        subset.GetParent.return_value = first_mesh
        second_mesh = _make_prim("/Asset/Second")
        second_mesh.IsA.side_effect = lambda schema: schema is UsdGeom.Mesh
        context = _make_context()
        context.get_stage.return_value.GetPrimAtPath.return_value = parent
        binding = mock.MagicMock()
        binding.ComputeBoundMaterial.return_value = (material, None)

        def get_materials(paths, _context_name):
            self.assertEqual(list(paths), ["/Asset"])
            return [material, material]

        with (
            mock.patch(
                "lightspeed.trex.comfyui.core.core.get_materials_from_prim_paths",
                side_effect=get_materials,
            ),
            mock.patch("lightspeed.trex.comfyui.core.core.get_context", return_value=context),
            mock.patch(
                "lightspeed.trex.comfyui.core.core.Usd.PrimRange",
                return_value=[first_mesh, subset, second_mesh],
            ),
            mock.patch("lightspeed.trex.comfyui.core.core.UsdShade.MaterialBindingAPI", return_value=binding),
        ):
            # Act
            candidates = core._get_material_candidates(iter(("/Asset",)))

        # Assert
        self.assertEqual(candidates, [(material, ["/Asset/First", "/Asset/Second"])])

    async def test_capture_texture_targets_rejects_inconsistent_texture_maps(self) -> None:
        """A missing shader-input mapping is reported as an unsupported workflow output."""
        # Arrange
        core = ComfyUICore("texturecraft")
        workflow = Workflow(output_specs=[WorkflowOutput("99", "albedo")])
        material = _make_material("/World/Looks/Wall")

        with mock.patch.dict("lightspeed.trex.comfyui.core.core.TEXTURE_TYPE_INPUT_MAP", {}, clear=True):
            # Act
            with self.assertRaisesRegex(ValueError, "unsupported texture type: albedo"):
                core._capture_texture_targets(material, workflow)

    async def test_stage_prim_paths_collects_meshes_subsets_and_materials(self) -> None:
        """Stage-expanding submissions seed candidates from every mesh, subset, and material prim."""
        # Arrange
        mesh = _make_prim("/World/Mesh")
        mesh.IsA.side_effect = lambda schema: schema is UsdGeom.Mesh
        subset = _make_prim("/World/Mesh/Subset")
        subset.IsA.side_effect = lambda schema: schema is UsdGeom.Subset
        material = _make_prim("/World/Looks/Material")
        material.IsA.side_effect = lambda schema: schema is UsdShade.Material
        camera = _make_prim("/World/Camera")
        camera.IsA.return_value = False
        stage = mock.MagicMock()

        # Act
        with mock.patch(
            "lightspeed.trex.comfyui.core.resolvers.textures.all_stage.Usd.PrimRange.Stage",
            return_value=[mesh, subset, material, camera],
        ):
            paths = list(AllStageTexturesResolver(context_name="texturecraft").iter_stage_prim_paths(stage))

        # Assert
        self.assertEqual(paths, ["/World/Mesh", "/World/Mesh/Subset", "/World/Looks/Material"])

    async def test_create_job_graphs_expands_candidates_to_all_stage_materials(self) -> None:
        """Selecting a stage-expanding getter submits one job per stage material, not the selection."""
        # Arrange
        core = ComfyUICore("texturecraft")
        resolver = AllStageTexturesResolver(context_name="texturecraft")
        core._workflow = Workflow(name="Upscale", inputs=[_workflow_input("node.inputs.image", resolver)])
        graph = mock.MagicMock()
        context = _make_context()
        stage = context.get_stage.return_value
        context.get_selection.return_value.get_selected_prim_paths.return_value = ["/World/Selected"]
        workflow = core._workflow

        with (
            mock.patch.object(core, "_get_submission_target", return_value=(stage, "/root.usda", "/edit.usda")),
            mock.patch("lightspeed.trex.comfyui.core.core.get_context", return_value=context),
            mock.patch.object(
                core, "_stage_expansion_prim_paths", return_value=["/World/A", "/World/B"]
            ) as stage_paths,
            mock.patch.object(core, "_get_material_candidates", return_value=[("material", [])]) as material_candidates,
            mock.patch.object(core, "_create_job_graphs_for_candidates", return_value=[graph]) as create_graphs,
        ):
            # Act
            graphs = await core._create_job_graphs()

        # Assert
        stage_paths.assert_called_once_with(
            stage,
            (mock.ANY,),
            report=mock.ANY,
            is_cancelled=None,
        )
        material_candidates.assert_called_once_with(["/World/A", "/World/B"])
        workflow_snapshot = create_graphs.call_args.args[1]
        self.assertIsNot(workflow_snapshot, workflow)
        self.assertEqual(workflow_snapshot, workflow)
        self.assertEqual(graphs, [graph])

    async def test_create_job_graphs_keeps_selection_without_stage_expanding_getter(self) -> None:
        """Without a stage-expanding getter the submission stays scoped to the selection."""
        # Arrange
        core = ComfyUICore("texturecraft")
        core._workflow = Workflow(name="Upscale")
        graph = mock.MagicMock()
        context = _make_context()
        stage = context.get_stage.return_value
        context.get_selection.return_value.get_selected_prim_paths.return_value = ["/World/Selected"]

        with (
            mock.patch.object(core, "_get_submission_target", return_value=(stage, "/root.usda", "/edit.usda")),
            mock.patch("lightspeed.trex.comfyui.core.core.get_context", return_value=context),
            mock.patch.object(core, "_stage_expansion_prim_paths") as stage_paths,
            mock.patch.object(core, "_get_material_candidates", return_value=[("material", [])]) as material_candidates,
            mock.patch.object(core, "_create_job_graphs_for_candidates", return_value=[graph]),
        ):
            # Act
            await core._create_job_graphs()

        # Assert
        stage_paths.assert_not_called()
        material_candidates.assert_called_once_with(["/World/Selected"])

    async def test_create_graphs_stage_expansion_resolves_each_material_once_and_filters_by_value(self) -> None:
        """Stage expansion filters the single resolved value without repeating material resolution."""
        # Arrange
        core = ComfyUICore("texturecraft")
        resolver = AllStageTexturesResolver(
            context_name="texturecraft",
            introducing_layer=IntroducingLayer.CAPTURE,
        )
        core._workflow = Workflow(
            api={"node": {"inputs": {"image": ""}}},
            inputs=[_workflow_input("node.inputs.image", resolver)],
        )
        kept_material = _make_material("/World/Looks/Kept")
        dropped_material = _make_material("/World/Looks/Dropped")

        # Act
        with (
            mock.patch("lightspeed.trex.comfyui.core.core.get_context", return_value=_make_context()),
            mock.patch.object(
                AllStageTexturesResolver,
                "__call__",
                side_effect=(pathlib.Path("/game/captured.png"), pathlib.Path("/mods/replaced.png")),
            ) as resolve,
            mock.patch(
                "lightspeed.trex.comfyui.core.resolvers.textures.all_stage.is_texture_from_capture",
                side_effect=(True, False),
            ),
            mock.patch.object(core, "_capture_texture_targets", return_value={}),
        ):
            graphs = core._create_job_graphs_for_candidates(
                [(kept_material, ["/World/A"]), (dropped_material, ["/World/B"])],
                core._workflow,
                "/project/project.usda",
                "/project/mod.usda",
                ("http", "127.0.0.1", 8188),
                core._client_id,
            )

        # Assert
        self.assertEqual(resolve.call_count, 2)
        self.assertEqual(len(graphs), 1)
        self.assertEqual(graphs[0].jobs[0].material_path, "/World/Looks/Kept")

    async def test_stage_expansion_prim_paths_stops_streaming_when_cancelled(self) -> None:
        """Cancellation stops consuming a stage-expanding getter before more paths are collected."""
        # Arrange
        resolver = mock.create_autospec(StageExpandingResolver, instance=True)
        resolver.iter_stage_prim_paths.return_value = iter(("/World/A", "/World/B"))
        is_cancelled = mock.MagicMock(side_effect=(False, True))

        # Act
        paths = list(
            ComfyUICore._stage_expansion_prim_paths(
                mock.MagicMock(),
                (resolver,),
                is_cancelled=is_cancelled,
            )
        )

        # Assert
        self.assertEqual(paths, ["/World/A"])

    async def test_capture_texture_targets_requires_exactly_one_valid_input_per_output(self) -> None:
        """Every workflow output captures one stable shader input or skips the material."""
        # Arrange
        core = ComfyUICore("texturecraft")
        core._workflow = Workflow(output_specs=[WorkflowOutput("99", "albedo")])
        material = _make_material("/World/Looks/Wall")
        replacements_core = mock.MagicMock()
        cases = (
            ([], "This material does not have a replaceable albedo texture."),
            (
                ["/ShaderA.inputs:diffuse_texture", "/ShaderB.inputs:diffuse_texture"],
                "This material has more than one albedo texture, so RTX Remix cannot choose which one to replace.",
            ),
        )

        for valid_inputs, message in cases:
            with self.subTest(valid_inputs=valid_inputs):
                replacements_core.get_valid_texture_inputs.return_value = valid_inputs
                with (
                    mock.patch.object(core, "_get_surface_shader_paths", return_value=["/ShaderA", "/ShaderB"]),
                    mock.patch(
                        "lightspeed.trex.comfyui.core.core.TextureReplacementsCore",
                        return_value=replacements_core,
                    ),
                ):
                    # Act
                    with self.assertRaises(ValueError) as error_context:
                        core._capture_texture_targets(material, core._workflow)

                # Assert
                self.assertEqual(str(error_context.exception), message)

    async def test_prepare_jobs_rejects_concurrent_preparation(self) -> None:
        """Overlapping preparation cannot race connection and graph construction."""
        # Arrange
        core = ComfyUICore("texturecraft")
        core._workflow = Workflow(name="Upscale")
        graph = JobGraph(name="Upscale")
        graph.add_job(ComfyUIJob(name="Upscale"))
        connect_started = asyncio.Event()
        release_connect = asyncio.Event()

        async def connect() -> None:
            """Hold the first connection attempt until the test releases it."""
            connect_started.set()
            await release_connect.wait()
            core._state = ComfyUIState.RUNNING
            core._connected_base_url = core.base_url

        with (
            mock.patch.object(core, "connect", side_effect=connect),
            mock.patch.object(core, "_create_job_graphs", mock.AsyncMock(return_value=[graph])),
        ):
            first = asyncio.create_task(core.prepare_jobs())
            await connect_started.wait()

            # Act
            with self.assertRaises(RuntimeError) as error_context:
                await core.prepare_jobs(prim_paths=["/World/Other"])

            # Assert
            self.assertIn("already in progress", str(error_context.exception))
            release_connect.set()
            await first

    async def test_failed_preparation_releases_concurrency_guard(self) -> None:
        """Failed preparation can be retried."""
        # Arrange
        core = ComfyUICore("texturecraft")
        core._workflow = Workflow(name="Upscale")

        # Act
        with mock.patch.object(core, "connect", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError) as error_context:
                await core.prepare_jobs()

        # Assert
        self.assertEqual(str(error_context.exception), "offline")
        self.assertIsNone(core._active_operation)

    async def test_fetch_available_workflows_publishes_typed_catalog(self) -> None:
        """A successful refresh caches and publishes the typed workflow catalog."""
        # Arrange
        core = ComfyUICore("texturecraft")
        expected = [Workflow(category=WorkflowCategory.API, source_type=WorkflowSourceType.USER, name="Material")]
        api = mock.MagicMock(base_url=core.base_url)
        api.get_workflow_list = mock.AsyncMock(return_value=expected)
        api.get_workflow_types = mock.AsyncMock(return_value=[])
        observed = []
        subscription = subscribe_comfyui_event(
            "texturecraft",
            lambda event: (
                observed.append(event.data["workflows"])
                if event.event_type == ComfyUIEventType.WORKFLOWS_LOADED
                else None
            ),
        )

        # Act
        with mock.patch.object(ComfyUICore, "api", new_callable=mock.PropertyMock, return_value=api):
            result = await core.fetch_available_workflows()

        # Assert
        self.assertEqual(result, expected)
        self.assertEqual(core.available_workflows, expected)
        self.assertEqual(observed, [expected])
        self.assertIsNotNone(subscription)

    async def test_workflow_type_categories_falls_back_to_mirror_when_unpublished(self) -> None:
        """A fresh core with no discovery falls back to the local vocabulary mirror."""
        # Arrange
        core = ComfyUICore("texturecraft")

        # Act
        categories = core.workflow_type_categories

        # Assert
        expected = [
            WorkflowTypeCategory(
                name=category_name,
                types=tuple(WorkflowTypeOption(workflow_type) for workflow_type in workflow_types),
            )
            for category_name, workflow_types in WORKFLOW_TYPES_BY_CATEGORY.items()
        ]
        self.assertEqual(categories, expected)

    async def test_workflow_type_categories_returns_published_categories_after_fetch(self) -> None:
        """The property returns the server vocabulary once discovery has published it."""
        # Arrange
        core = ComfyUICore("texturecraft")
        expected = [WorkflowTypeCategory(name="Other", types=(WorkflowTypeOption(WorkflowType.OTHER, "Misc."),))]
        api = mock.MagicMock(base_url=core.base_url)
        api.get_workflow_list = mock.AsyncMock(return_value=[])
        api.get_workflow_types = mock.AsyncMock(return_value=expected)

        # Act
        with mock.patch.object(ComfyUICore, "api", new_callable=mock.PropertyMock, return_value=api):
            await core.fetch_available_workflows()

        # Assert
        self.assertEqual(core.workflow_type_categories, expected)

    async def test_fetch_available_workflows_tolerates_type_request_failure(self) -> None:
        """A server without the types endpoint still connects and keeps its workflow catalog."""
        # Arrange
        core = ComfyUICore("texturecraft")
        expected = [Workflow(category=WorkflowCategory.API, source_type=WorkflowSourceType.USER, name="Material")]
        api = mock.MagicMock(base_url=core.base_url)
        api.get_workflow_list = mock.AsyncMock(return_value=expected)
        api.get_workflow_types = mock.AsyncMock(side_effect=RuntimeError("workflows/types not found"))

        # Act
        with mock.patch.object(ComfyUICore, "api", new_callable=mock.PropertyMock, return_value=api):
            result = await core.fetch_available_workflows()

        # Assert
        mirror = [
            WorkflowTypeCategory(
                name=category_name,
                types=tuple(WorkflowTypeOption(workflow_type) for workflow_type in workflow_types),
            )
            for category_name, workflow_types in WORKFLOW_TYPES_BY_CATEGORY.items()
        ]
        self.assertEqual(result, expected)
        self.assertEqual(core.available_workflows, expected)
        self.assertEqual(core.workflow_type_categories, mirror)

    async def test_fetch_available_workflows_publishes_after_categories_are_stored(self) -> None:
        """A subscriber handling WORKFLOWS_LOADED sees the server categories, not the mirror."""
        # Arrange
        core = ComfyUICore("texturecraft")
        expected_workflows = [
            Workflow(category=WorkflowCategory.API, source_type=WorkflowSourceType.USER, name="Material")
        ]
        expected_categories = [
            WorkflowTypeCategory(name="Other", types=(WorkflowTypeOption(WorkflowType.OTHER, "Misc."),))
        ]
        api = mock.MagicMock(base_url=core.base_url)
        api.get_workflow_list = mock.AsyncMock(return_value=expected_workflows)
        api.get_workflow_types = mock.AsyncMock(return_value=expected_categories)
        observed = []
        subscription = subscribe_comfyui_event(
            "texturecraft",
            lambda event: (
                observed.append(core.workflow_type_categories)
                if event.event_type == ComfyUIEventType.WORKFLOWS_LOADED
                else None
            ),
        )

        # Act
        with mock.patch.object(ComfyUICore, "api", new_callable=mock.PropertyMock, return_value=api):
            await core.fetch_available_workflows()

        # Assert
        self.assertEqual(observed, [expected_categories])
        self.assertIsNotNone(subscription)

    async def test_load_workflow_uses_canonical_api_full_pair(self) -> None:
        """Workflow loading requires both canonical server representations."""
        # Arrange
        core = ComfyUICore("texturecraft")
        api = mock.MagicMock(base_url=core.base_url)
        api.get_workflow_data = mock.AsyncMock(return_value=get_test_workflow_pair())

        # Act
        with mock.patch.object(ComfyUICore, "api", new_callable=mock.PropertyMock, return_value=api):
            await core.load_workflow(
                Workflow(category=WorkflowCategory.API, source_type=WorkflowSourceType.USER, name="Material")
            )

        # Assert
        api.get_workflow_data.assert_awaited_once_with(WorkflowSourceType.USER, "Material")
        self.assertEqual(core.workflow.name, "Material")
        self.assertIs(core.workflow.source_type, WorkflowSourceType.USER)
        self.assertIs(core.workflow.category, WorkflowCategory.API)

    async def test_load_workflow_preserves_catalog_metadata(self) -> None:
        """A loaded workflow keeps the catalog entry's display metadata."""
        # Arrange
        core = ComfyUICore("texturecraft")
        api = mock.MagicMock(base_url=core.base_url)
        api.get_workflow_data = mock.AsyncMock(return_value=get_test_workflow_pair())
        catalog_workflow = Workflow(
            category=WorkflowCategory.API,
            source_type=WorkflowSourceType.USER,
            name="material",
            display_name="Material Generation",
            description="Generates a PBR material.",
            workflow_type=WorkflowType.MATERIAL_GENERATION,
        )

        # Act
        with mock.patch.object(ComfyUICore, "api", new_callable=mock.PropertyMock, return_value=api):
            await core.load_workflow(catalog_workflow)

        # Assert
        self.assertIsNot(core.workflow, catalog_workflow)
        self.assertEqual(core.workflow.display_name, "Material Generation")
        self.assertEqual(core.workflow.description, "Generates a PBR material.")
        self.assertIs(core.workflow.workflow_type, WorkflowType.MATERIAL_GENERATION)
        self.assertIs(core.workflow.source_type, WorkflowSourceType.USER)
        self.assertIs(core.workflow.category, WorkflowCategory.API)

    async def test_load_workflow_failure_hides_server_details_from_status(self) -> None:
        """A workflow format failure exposes recovery guidance while retaining the technical exception."""
        # Arrange
        core = ComfyUICore("texturecraft")
        api = mock.MagicMock(base_url=core.base_url)
        api.get_workflow_data = mock.AsyncMock(side_effect=ValueError("invalid node 143 metadata"))

        # Act
        with (
            mock.patch.object(ComfyUICore, "api", new_callable=mock.PropertyMock, return_value=api),
            self.assertRaises(ValueError) as error_context,
        ):
            await core.load_workflow(
                Workflow(category=WorkflowCategory.API, source_type=WorkflowSourceType.USER, name="Material")
            )

        # Assert
        self.assertEqual(str(error_context.exception), "invalid node 143 metadata")
        self.assertEqual(
            core.status_message,
            "ComfyUI returned workflow information that RTX Remix could not read. "
            "Update the RTX Remix ComfyUI nodes and try again.",
        )

    async def test_load_workflow_rejects_mistyped_active_preset_with_status(self) -> None:
        """A mistyped active preset clears the workflow and exposes recovery guidance."""
        # Arrange
        core = ComfyUICore("texturecraft")
        core._state = ComfyUIState.RUNNING
        api_workflow, full_workflow = get_test_workflow_pair()
        full_workflow["extra"]["rtx-remix"]["presets"]["Strong"]["inputs"]["10.strength"]["value"] = "strong"
        api = mock.MagicMock(base_url=core.base_url)
        api.get_workflow_data = mock.AsyncMock(return_value=(api_workflow, full_workflow))

        # Act
        with (
            mock.patch.object(ComfyUICore, "api", new_callable=mock.PropertyMock, return_value=api),
            self.assertRaises(TypeError) as error_context,
        ):
            await core.load_workflow(
                Workflow(category=WorkflowCategory.API, source_type=WorkflowSourceType.USER, name="Material")
            )

        # Assert
        self.assertEqual(str(error_context.exception), "Workflow value must be float")
        self.assertIsNone(core.workflow)
        self.assertIs(core.state, ComfyUIState.RUNNING)
        self.assertEqual(
            core.status_message,
            "ComfyUI returned workflow information that RTX Remix could not read. "
            "Update the RTX Remix ComfyUI nodes and try again.",
        )

    async def test_set_workflow_during_load_preserves_external_workflow(self) -> None:
        """An explicit workflow selection invalidates an older in-flight load."""
        # Arrange
        core = ComfyUICore("texturecraft")
        api = mock.MagicMock(base_url=core.base_url)
        request_started = asyncio.Event()
        release_request = asyncio.Event()

        async def get_workflow_data(*_args):
            """Hold workflow loading until the test changes the selection.

            Args:
                *_args: Workflow lookup arguments ignored by the controlled response.

            Returns:
                Fresh API and full workflow fixtures after the request is released.
            """
            request_started.set()
            await release_request.wait()
            return get_test_workflow_pair()

        api.get_workflow_data = mock.AsyncMock(side_effect=get_workflow_data)
        restored = Workflow(name="Restored")

        with mock.patch.object(ComfyUICore, "api", new_callable=mock.PropertyMock, return_value=api):
            load_task = asyncio.create_task(
                core.load_workflow(
                    Workflow(category=WorkflowCategory.API, source_type=WorkflowSourceType.USER, name="Material")
                )
            )
            await request_started.wait()

            # Act
            core.set_workflow(restored)
            release_request.set()
            await load_task

        # Assert
        self.assertIs(core.workflow, restored)

    async def test_cancelled_workflow_load_restores_user_facing_state(self) -> None:
        """Cancellation rolls back the current workflow before propagating."""
        # Arrange
        core = ComfyUICore("texturecraft")
        core._state = ComfyUIState.RUNNING
        api = mock.MagicMock(base_url=core.base_url)
        request_started = asyncio.Event()

        async def get_workflow_data(*_args):
            request_started.set()
            await asyncio.Event().wait()

        api.get_workflow_data = mock.AsyncMock(side_effect=get_workflow_data)
        with mock.patch.object(ComfyUICore, "api", new_callable=mock.PropertyMock, return_value=api):
            load_task = asyncio.create_task(
                core.load_workflow(
                    Workflow(category=WorkflowCategory.API, source_type=WorkflowSourceType.USER, name="Material")
                )
            )
            await request_started.wait()

            # Act
            load_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await load_task

        # Assert
        self.assertIsNone(core.workflow)
        self.assertIs(core.state, ComfyUIState.RUNNING)
        self.assertEqual(core.status_message, "Workflow loading was canceled. Select the workflow to try again.")

    async def test_connect_sets_current_endpoint_and_catalog(self) -> None:
        """A successful connection publishes RUNNING only for its verified endpoint."""
        # Arrange
        core = ComfyUICore("texturecraft")
        expected = [Workflow(category=WorkflowCategory.API, source_type=WorkflowSourceType.RTX_REMIX, name="PBRify")]
        api = mock.MagicMock(base_url=core.base_url)
        api.ping = mock.AsyncMock(return_value={})
        api.get_workflow_list = mock.AsyncMock(return_value=expected)
        api.get_workflow_types = mock.AsyncMock(return_value=[])

        # Act
        with mock.patch.object(ComfyUICore, "api", new_callable=mock.PropertyMock, return_value=api):
            await core.connect()

        # Assert
        self.assertIs(core.state, ComfyUIState.RUNNING)
        self.assertTrue(core.is_connected)
        self.assertEqual(core.available_workflows, expected)
        self.assertEqual(get_connected_endpoint("texturecraft"), ("http", "127.0.0.1", 8188))

    async def test_connect_failure_hides_network_details_from_status(self) -> None:
        """A connection failure exposes recovery guidance while retaining the technical exception."""
        # Arrange
        core = ComfyUICore("texturecraft")
        api = mock.MagicMock(base_url=core.base_url)
        api.ping = mock.AsyncMock(side_effect=RuntimeError("connection refused by 10.20.30.40"))

        # Act
        with (
            mock.patch.object(ComfyUICore, "api", new_callable=mock.PropertyMock, return_value=api),
            self.assertRaises(RuntimeError) as error_context,
        ):
            await core.connect()

        # Assert
        self.assertEqual(str(error_context.exception), "connection refused by 10.20.30.40")
        self.assertIs(core.state, ComfyUIState.ERROR)
        self.assertEqual(
            core.status_message,
            "Could not connect to ComfyUI. Check the server address and that ComfyUI is running, then try again.",
        )
        self.assertEqual(core.last_connection_error, "connection refused by 10.20.30.40")

    async def test_connect_retry_clears_last_connection_error(self) -> None:
        """A new connection attempt cannot retain technical details from the previous failure."""
        # Arrange
        core = ComfyUICore("texturecraft")
        api = mock.MagicMock(base_url=core.base_url)
        api.ping = mock.AsyncMock(side_effect=RuntimeError("connection refused"))
        api.get_workflow_list = mock.AsyncMock(return_value=[])
        api.get_workflow_types = mock.AsyncMock(return_value=[])

        with mock.patch.object(ComfyUICore, "api", new_callable=mock.PropertyMock, return_value=api):
            with self.assertRaises(RuntimeError):
                await core.connect()

            self.assertEqual(core.last_connection_error, "connection refused")

            async def ping_after_failure() -> dict:
                self.assertIs(core.state, ComfyUIState.STARTING)
                self.assertEqual(core.last_connection_error, "")
                return {}

            api.ping.side_effect = ping_after_failure

            # Act
            await core.connect()

        # Assert
        self.assertIs(core.state, ComfyUIState.RUNNING)
        self.assertEqual(core.last_connection_error, "")

    async def test_shutdown_clears_connected_endpoint(self) -> None:
        """Disconnecting prevents persisted jobs from running against a stale instance."""
        # Arrange
        core = ComfyUICore("texturecraft")
        set_connected_endpoint("texturecraft", ("http", "comfy-a", 8188))

        # Act
        await core.shutdown()

        # Assert
        self.assertIsNone(get_connected_endpoint("texturecraft"))

    async def test_shared_event_isolates_observer_failures(self) -> None:
        """A broken observer cannot block later subscribers or producer state."""
        # Arrange
        core = ComfyUICore("texturecraft")
        observed = []

        def reject(_event) -> None:
            """Raise from one observer to test event isolation.

            Args:
                _event: Event payload ignored by the failing observer.

            Raises:
                KeyError: Always, to emulate a broken observer.
            """
            raise KeyError("observer failed")

        subscriptions = [
            subscribe_comfyui_event("texturecraft", reject),
            subscribe_comfyui_event("texturecraft", observed.append),
        ]

        # Act
        with mock.patch("lightspeed.trex.comfyui.core.events.carb.log_error") as log_error:
            core.set_workflow(Workflow(name="Material"))

        # Assert
        self.assertEqual(len(observed), 1)
        self.assertEqual(core.workflow.name, "Material")
        log_error.assert_called_once()
        self.assertEqual(len(subscriptions), 2)

    async def test_destroy_releases_settings_observer_without_displacing_shared_subscriber(self) -> None:
        """Core destruction releases owned settings state but not shared event subscriptions."""
        # Arrange
        settings_changed = mock.MagicMock()
        observed = mock.MagicMock()
        core = ComfyUICore("texturecraft", settings_changed_callback=settings_changed)
        subscription = subscribe_comfyui_event("texturecraft", observed)

        # Act
        core.destroy()
        observed.reset_mock()
        publish_comfyui_event("texturecraft", ComfyUIEventType.WORKFLOW_CHANGED)
        core.settings.set_host("comfy.example")

        # Assert
        observed.assert_called_once()
        settings_changed.assert_not_called()
        self.assertIsNotNone(subscription)

    async def test_prepare_submission_returns_opaque_counts_for_widget_rendering(self) -> None:
        """Submission preparation exposes counts without requiring widgets to inspect graphs."""
        # Arrange
        core = ComfyUICore("texturecraft")
        accepted_graph = mock.MagicMock()
        accepted_graph.jobs = [mock.MagicMock(skip_reason=None)]
        skipped_graph = mock.MagicMock()
        skipped_graph.jobs = [mock.MagicMock(skip_reason="missing input")]
        core.prepare_jobs = mock.AsyncMock(return_value=[accepted_graph, skipped_graph])

        # Act
        submission = await core.prepare_submission(["/World/Material"])

        # Assert
        self.assertEqual(len(submission.graphs), 2)
        self.assertEqual(submission.skipped_count, 1)
        core.prepare_jobs.assert_awaited_once_with(prim_paths=["/World/Material"], progress=None, is_cancelled=None)

    async def test_destroyed_core_cannot_submit_prepared_jobs(self) -> None:
        """A stale core cannot mutate the queue after extension shutdown."""
        # Arrange
        core = ComfyUICore("texturecraft")
        core.destroy()
        submission = ComfyUISubmission((), skipped_count=0)

        with mock.patch("lightspeed.trex.comfyui.core.core.get_job_queue") as get_queue:
            # Act
            with self.assertRaises(RuntimeError):
                await core.submit_prepared_submission(submission)

        # Assert
        get_queue.assert_not_called()

    async def test_destroyed_core_cannot_resolve_workflow_requests(self) -> None:
        """A stale core cannot read durable queue inputs after extension shutdown."""
        # Arrange
        core = ComfyUICore("texturecraft")
        job = ComfyUIJob(context_name="texturecraft")
        core.destroy()

        with mock.patch("lightspeed.trex.comfyui.core.core.get_job_queue") as get_queue:
            # Act
            with self.assertRaises(RuntimeError):
                core.get_workflow_request(job)

        # Assert
        get_queue.assert_not_called()

    async def test_destroyed_core_cannot_read_retarget_state(self) -> None:
        """A stale core cannot inspect queued retarget state after extension shutdown."""
        # Arrange
        core = ComfyUICore("texturecraft")
        job = ComfyUIJob(context_name="texturecraft")
        core.destroy()

        with mock.patch("lightspeed.trex.comfyui.core.core.get_job_queue") as get_queue:
            # Act
            with self.assertRaises(RuntimeError):
                core.get_retarget_state(job)

        # Assert
        get_queue.assert_not_called()

    async def test_destroyed_core_cannot_retarget_jobs(self) -> None:
        """A stale core cannot mutate a queued endpoint after extension shutdown."""
        # Arrange
        core = ComfyUICore("texturecraft")
        job = ComfyUIJob(context_name="texturecraft")
        core.destroy()

        with mock.patch("lightspeed.trex.comfyui.core.core.get_job_queue") as get_queue:
            # Act
            with self.assertRaises(RuntimeError):
                core.retarget_job(job, ("http", "127.0.0.1", 8188))

        # Assert
        get_queue.assert_not_called()

    async def test_submit_prepared_submission_adds_every_graph_in_one_batch(self) -> None:
        """Core submission adds the whole batch in one queue transaction and reports full success."""
        # Arrange
        core = ComfyUICore("texturecraft")
        graphs = (mock.MagicMock(), mock.MagicMock())
        submission = ComfyUISubmission(graphs, skipped_count=0)
        queue = mock.MagicMock()

        with mock.patch("lightspeed.trex.comfyui.core.core.get_job_queue", return_value=queue):
            # Act
            result = await core.submit_prepared_submission(submission)

        # Assert
        queue.submit_graphs.assert_called_once_with(graphs)
        self.assertEqual(result.submitted_count, 2)
        self.assertEqual(result.failed_count, 0)

    async def test_submit_prepared_submission_reports_all_or_nothing_on_failure(self) -> None:
        """A failed batch transaction reports every graph as not added rather than a partial count."""
        # Arrange
        core = ComfyUICore("texturecraft")
        graphs = (mock.MagicMock(), mock.MagicMock(), mock.MagicMock())
        submission = ComfyUISubmission(graphs, skipped_count=0)
        queue = mock.MagicMock()
        queue.submit_graphs.side_effect = QueueSubmissionError("duplicate")

        with mock.patch("lightspeed.trex.comfyui.core.core.get_job_queue", return_value=queue):
            # Act
            result = await core.submit_prepared_submission(submission)

        # Assert
        self.assertEqual(result.submitted_count, 0)
        self.assertEqual(result.failed_count, 3)
        self.assertIsNone(core._active_operation)

    async def test_submission_rejects_overlapping_preparation_and_submission(self) -> None:
        """Preparation and submission share one exception-safe ownership guard."""
        # Arrange
        core = ComfyUICore("texturecraft")
        graph = mock.MagicMock()
        submission = ComfyUISubmission((graph,), skipped_count=0)
        submit_started = threading.Event()
        release_submit = threading.Event()
        queue = mock.MagicMock()

        def submit_graphs(_graphs) -> None:
            submit_started.set()
            release_submit.wait()

        queue.submit_graphs.side_effect = submit_graphs

        with mock.patch("lightspeed.trex.comfyui.core.core.get_job_queue", return_value=queue):
            active_submission = asyncio.create_task(core.submit_prepared_submission(submission))
            await asyncio.to_thread(submit_started.wait)

            # Act
            with self.assertRaisesRegex(RuntimeError, "queue submission is already in progress"):
                await core.prepare_jobs()

            # Assert
            release_submit.set()
            result = await active_submission
        self.assertEqual(result.submitted_count, 1)
        self.assertIsNone(core._active_operation)

    async def test_cancelled_submission_settles_batch_before_releasing_operation(self) -> None:
        """Cancellation waits for the atomic queue transaction before releasing submission ownership."""
        # Arrange
        core = ComfyUICore("texturecraft")
        graph = mock.MagicMock()
        submission = ComfyUISubmission((graph,), skipped_count=0)
        submit_started = threading.Event()
        release_submit = threading.Event()
        queue = mock.MagicMock()

        def submit_graphs(_graphs) -> None:
            """Hold the batch transaction until the test releases it."""
            submit_started.set()
            release_submit.wait()

        queue.submit_graphs.side_effect = submit_graphs

        with mock.patch("lightspeed.trex.comfyui.core.core.get_job_queue", return_value=queue):
            submission_task = asyncio.create_task(core.submit_prepared_submission(submission))
            await asyncio.to_thread(submit_started.wait)
            submission_task.cancel()
            await asyncio.sleep(0)

            # Act
            operation_while_settling = core._active_operation
            release_submit.set()
            with self.assertRaises(asyncio.CancelledError):
                await submission_task

        # Assert
        self.assertIs(operation_while_settling, ComfyUIOperation.QUEUE_SUBMISSION)
        queue.submit_graphs.assert_called_once_with((graph,))
        self.assertIsNone(core._active_operation)

    async def test_settings_change_invalidates_all_endpoint_owned_state(self) -> None:
        """An endpoint setting change cannot revive an earlier connection or workflow."""
        # Arrange
        core = ComfyUICore("texturecraft")
        core._state = ComfyUIState.RUNNING
        core._connected_base_url = core.base_url
        core._workflow_base_url = core.base_url
        core._workflow = Workflow(name="Material")
        core._available_workflows = [
            Workflow(category=WorkflowCategory.API, source_type=WorkflowSourceType.USER, name="Material")
        ]
        generations = (
            core._connect_generation,
            core._workflow_discovery_generation,
            core._workflow_load_generation,
        )

        # Act
        with mock.patch("lightspeed.trex.comfyui.core.core.set_connected_endpoint") as set_connected_endpoint_mock:
            core.handle_settings_changed("host", "other.example")

        # Assert
        self.assertIs(core.state, ComfyUIState.READY)
        self.assertFalse(core.is_connected)
        set_connected_endpoint_mock.assert_called_once_with("texturecraft", None)
        self.assertIsNone(core.workflow)
        self.assertEqual(core.available_workflows, [])
        self.assertEqual(
            (
                core._connect_generation,
                core._workflow_discovery_generation,
                core._workflow_load_generation,
            ),
            tuple(generation + 1 for generation in generations),
        )

    async def test_get_workflow_request_resolves_and_validates_durable_job_input(self) -> None:
        """Core owns typed workflow-request resolution from durable queue state."""
        # Arrange
        core = ComfyUICore("texturecraft")
        job = ComfyUIJob(context_name="texturecraft")
        request = ComfyUIWorkflowRequest(
            prompt={},
            input_bindings=(),
            client_id="test-client",
            timeout=1.0,
            output_url="file:///project/output",
            workflow=Workflow(name="Test"),
        )
        queue = mock.MagicMock()
        queue.resolve_job_inputs.return_value = {ComfyUIJob.WORKFLOW_REQUEST: request}

        with mock.patch("lightspeed.trex.comfyui.core.core.get_job_queue", return_value=queue):
            # Act
            resolved = core.get_workflow_request(job)

        # Assert
        self.assertIs(resolved, request)
        queue.resolve_job_inputs.assert_called_once_with(job.job_id)

    async def test_retarget_job_persists_copy_only_for_expected_connection(self) -> None:
        """Core atomically retargets a queued copy against the expected connection."""
        # Arrange
        core = ComfyUICore("texturecraft")
        job = ComfyUIJob(context_name="texturecraft", scheme="http", host="old.example", port=8188)
        endpoint = ("https", "new.example", 443)
        set_connected_endpoint("texturecraft", endpoint)
        queue = mock.MagicMock()
        queue.try_update_queued_job.return_value = True

        with mock.patch("lightspeed.trex.comfyui.core.core.get_job_queue", return_value=queue):
            # Act
            result = core.retarget_job(job, endpoint)

        # Assert
        self.assertIs(result, ComfyUIRetargetResult.UPDATED)
        updated_job = queue.try_update_queued_job.call_args.args[0]
        self.assertIsNot(updated_job, job)
        self.assertEqual((updated_job.scheme, updated_job.host, updated_job.port), endpoint)
        self.assertEqual((job.scheme, job.host, job.port), ("http", "old.example", 8188))

    async def test_get_retarget_state_returns_queue_and_endpoint_state_for_rendering(self) -> None:
        """Core returns the domain state needed to render the Retarget action."""
        # Arrange
        core = ComfyUICore("texturecraft")
        job = ComfyUIJob(context_name="texturecraft", scheme="http", host="old.example", port=8188)
        connected = ("https", "new.example", 443)
        set_connected_endpoint("texturecraft", connected)
        queue = mock.MagicMock()
        queue.get_job_snapshot.return_value.state = JobState.QUEUED

        with mock.patch("lightspeed.trex.comfyui.core.core.get_job_queue", return_value=queue):
            # Act
            state = core.get_retarget_state(job)

        # Assert
        self.assertTrue(state.is_queued)
        self.assertEqual(state.saved_endpoint, ("http", "old.example", 8188))
        self.assertEqual(state.connected_endpoint, connected)
        self.assertTrue(state.can_retarget)

    async def test_extension_shutdown_failure_retains_state_for_retry(self) -> None:
        """Failed teardown remains owned and a later shutdown can finish it."""
        # Arrange
        first = mock.MagicMock()
        first.destroy.side_effect = [RuntimeError("destroy failed"), None]
        second = mock.MagicMock()
        extension._instances.update({"first": first, "second": second})
        extension._started = True
        registry = mock.MagicMock()
        resolver_factory = mock.MagicMock()
        event_manager = mock.MagicMock()

        with (
            mock.patch.object(extension.handlers, "unregister_plugins"),
            mock.patch.object(extension, "get_registry", return_value=registry),
            mock.patch.object(extension, "get_resolver_factory", return_value=resolver_factory),
            mock.patch.object(extension, "_get_event_manager_instance", return_value=event_manager),
        ):
            core_extension = extension.ComfyUICoreExtension()

            # Act
            with self.assertRaises(RuntimeError) as error_context:
                core_extension.on_shutdown()

            retained_instances = extension._instances.copy()
            retained_started = extension._started
            core_extension.on_shutdown()

        # Assert
        self.assertEqual(str(error_context.exception), "destroy failed")
        registry.unregister_codecs.assert_not_called()
        self.assertEqual(resolver_factory.unregister_plugins.call_count, 2)
        self.assertEqual(event_manager.unregister_global_custom_event.call_count, 2)
        self.assertEqual(retained_instances, {"first": first, "second": second})
        self.assertTrue(retained_started)
        self.assertEqual(first.destroy.call_count, 2)
        self.assertEqual(second.destroy.call_count, 2)
        self.assertEqual(extension._instances, {})
        self.assertFalse(extension._started)

    async def test_extension_registers_fixed_plugins_codecs_and_apply_handler(self) -> None:
        """Extension startup registers exact resolver plugins, persistence codecs, and Apply handler."""
        # Arrange
        registry = mock.MagicMock()
        resolver_factory = mock.MagicMock()
        event_manager = mock.MagicMock()

        # Act
        with (
            mock.patch.object(extension.handlers, "register_plugins") as register_plugins,
            mock.patch.object(extension, "get_registry", return_value=registry),
            mock.patch.object(extension, "get_resolver_factory", return_value=resolver_factory),
            mock.patch.object(extension, "_get_event_manager_instance", return_value=event_manager),
        ):
            extension.ComfyUICoreExtension().on_startup("lightspeed.trex.comfyui.core")

        # Assert
        resolver_factory.register_plugins.assert_called_once_with(extension.RESOLVER_PLUGINS)
        registry.register_codecs.assert_called_once_with(extension.COMFYUI_CODECS)
        register_plugins.assert_called_once_with([ComfyUIJobApplyHandler])
        event_manager.register_global_custom_event.assert_called_once_with(extension.COMFYUI_EVENT_NAME)
        self.assertFalse(extension._shutting_down)
        self.assertTrue(extension._started)

    async def test_extension_lifecycle_is_idempotent(self) -> None:
        """Repeated startup and shutdown retain one exact registration owner."""
        # Arrange
        registry = mock.MagicMock()
        resolver_factory = mock.MagicMock()
        event_manager = mock.MagicMock()
        core_extension = extension.ComfyUICoreExtension()

        with (
            mock.patch.object(extension.handlers, "register_plugins") as register_handlers,
            mock.patch.object(extension.handlers, "unregister_plugins") as unregister_handlers,
            mock.patch.object(extension, "get_registry", return_value=registry),
            mock.patch.object(extension, "get_resolver_factory", return_value=resolver_factory),
            mock.patch.object(extension, "_get_event_manager_instance", return_value=event_manager),
        ):
            # Act
            core_extension.on_startup("lightspeed.trex.comfyui.core")
            core_extension.on_startup("lightspeed.trex.comfyui.core")
            core_extension.on_shutdown()
            core_extension.on_shutdown()

        # Assert
        register_handlers.assert_called_once_with([ComfyUIJobApplyHandler])
        unregister_handlers.assert_called_once_with([ComfyUIJobApplyHandler])
        registry.register_codecs.assert_called_once_with(extension.COMFYUI_CODECS)
        registry.unregister_codecs.assert_not_called()
        self.assertFalse(extension._started)

    async def test_extension_shutdown_keeps_codecs_until_active_comfyui_job_completes(self) -> None:
        """Queue completion can reload an active ComfyUI job after its product extension stops."""
        # Arrange
        generation_job = ComfyUIJob(name="Generate Material", context_name="texturecraft")
        workflow_request = ComfyUIWorkflowRequest(
            prompt={},
            input_bindings=(),
            client_id="",
            timeout=300.0,
            output_url=None,
            workflow=Workflow(),
        )
        graph = JobGraph(name="Material generation")
        graph.add_job(generation_job)
        graph.bind(generation_job, ComfyUIJob.WORKFLOW_REQUEST, workflow_request)
        generation_output = TextureProcessingRequest(
            items=(
                TextureProcessingItem(
                    key="albedo",
                    path=pathlib.Path("C:/queue/albedo.png"),
                    texture_type=TextureTypes.DIFFUSE,
                ),
            ),
            source_root=pathlib.Path("C:/queue"),
            output_url=None,
        )
        extension._started = True
        set_connected_endpoint("texturecraft", ("http", "127.0.0.1", 8188))

        with tempfile.TemporaryDirectory(prefix="comfyui-shutdown-") as temp_dir:
            interface = QueueInterface(str(pathlib.Path(temp_dir) / "queue.sqlite"))
            interface.submit(graph)
            self.assertEqual(interface.claim_runnable_jobs(), [generation_job.job_id])
            self.assertTrue(interface.start_job(generation_job.job_id))

            with (
                mock.patch.object(extension.handlers, "unregister_plugins"),
                mock.patch.object(extension, "get_resolver_factory"),
                mock.patch.object(extension, "_get_event_manager_instance"),
            ):
                # Stop the product extension while queue-owned execution is still active.
                extension.ComfyUICoreExtension().on_shutdown()

            # Finish through the real queue persistence boundary after product shutdown.
            completed = interface.complete_job(
                generation_job.job_id,
                JobOutputs({ComfyUIJob.GENERATED_TEXTURES: generation_output}),
            )
            snapshot = interface.get_job_snapshot(generation_job.job_id)

        # Assert
        self.assertTrue(completed)
        self.assertEqual(snapshot.state, JobState.DONE)

    async def test_opening_a_stage_reconciles_only_pending_comfyui_apply_work(self) -> None:
        """Opening a project wakes exact ComfyUI Apply bindings that may now match their captured stage."""
        # Arrange
        comfy_job_id = mock.sentinel.comfy_job_id
        other_job_id = mock.sentinel.other_job_id
        queue = mock.MagicMock()
        queue.iter_snapshot.return_value = [
            mock.MagicMock(job_id=comfy_job_id, apply_handler_id=ComfyUIJobApplyHandler.name),
            mock.MagicMock(job_id=other_job_id, apply_handler_id="OtherHandler"),
        ]
        executor = mock.MagicMock()

        with (
            mock.patch.object(extension, "get_job_queue", return_value=queue),
            mock.patch.object(extension.handlers, "get_apply_executor", return_value=executor),
        ):
            # Act
            extension.ComfyUICoreExtension()._on_stage_event(mock.MagicMock(type=int(usd.StageEventType.OPENED)))

        # Assert
        queue.notify_schedule_conditions_changed.assert_called_once_with()
        executor.request_reconcile.assert_called_once_with(comfy_job_id)

    async def test_closed_stage_refreshes_apply_availability_without_reconciling(self) -> None:
        """A fully closed project disables stale Apply actions without starting work."""
        # Arrange
        queue = mock.MagicMock()

        with (
            mock.patch.object(extension, "get_job_queue", return_value=queue),
            mock.patch.object(extension.handlers, "get_apply_executor") as get_apply_executor,
        ):
            # Act
            extension.ComfyUICoreExtension()._on_stage_event(mock.MagicMock(type=int(usd.StageEventType.CLOSED)))

        # Assert
        queue.notify_schedule_conditions_changed.assert_called_once_with()
        get_apply_executor.assert_not_called()

    async def test_visibility_notice_from_other_stage_does_not_publish_context_event(self) -> None:
        """A context core ignores visibility notices from another USD stage."""
        # Arrange
        core = ComfyUICore("texturecraft")
        notice = mock.MagicMock()
        notice.GetChangedInfoOnlyPaths.return_value = [Sdf.Path("/World/Object.visibility")]
        notice.GetResyncedPaths.return_value = []
        context = mock.MagicMock()
        context.get_stage.return_value = mock.MagicMock()

        # Act
        with (
            mock.patch.object(core_module, "get_context", return_value=context),
            mock.patch.object(core_module, "publish_comfyui_event") as publish_event,
        ):
            core._on_objects_changed(notice, mock.MagicMock())

        # Assert
        publish_event.assert_not_called()

    async def test_unrelated_stage_notice_does_not_publish_visibility_event(self) -> None:
        """Transform and prim resync notices do not wake visibility presentation."""
        # Arrange
        core = ComfyUICore("texturecraft")
        notice = mock.MagicMock()
        notice.GetChangedInfoOnlyPaths.return_value = [Sdf.Path("/World/Object.xformOp:translate")]
        notice.GetResyncedPaths.return_value = [Sdf.Path("/World/Object")]
        context = mock.MagicMock()
        stage = mock.MagicMock()
        context.get_stage.return_value = stage

        # Act
        with (
            mock.patch.object(core_module, "get_context", return_value=context),
            mock.patch.object(core_module, "publish_comfyui_event") as publish_event,
        ):
            core._on_objects_changed(notice, stage)

        # Assert
        publish_event.assert_not_called()

    async def test_extension_startup_stays_disabled_when_resolver_registration_fails(self) -> None:
        """Resolver registration failure leaves the core factory disabled and untouched downstream."""
        # Arrange
        registry = mock.MagicMock()
        resolver_factory = mock.MagicMock()
        registration_error = RuntimeError("resolver registration failed")
        resolver_factory.register_plugins.side_effect = registration_error
        event_manager = mock.MagicMock()

        # Act
        with (
            mock.patch.object(extension.handlers, "register_plugins") as register_handlers,
            mock.patch.object(extension, "get_registry", return_value=registry),
            mock.patch.object(extension, "get_resolver_factory", return_value=resolver_factory),
            mock.patch.object(extension, "_get_event_manager_instance", return_value=event_manager),
        ):
            with self.assertRaises(RuntimeError) as error_context:
                extension.ComfyUICoreExtension().on_startup("lightspeed.trex.comfyui.core")

        # Assert
        self.assertIs(error_context.exception, registration_error)
        self.assertTrue(extension._shutting_down)
        resolver_factory.unregister_plugins.assert_not_called()
        registry.register_codecs.assert_not_called()
        register_handlers.assert_not_called()
        event_manager.register_global_custom_event.assert_not_called()

    async def test_extension_startup_stays_disabled_when_persistence_registration_fails(self) -> None:
        """Persistence registration failure rolls back resolvers while the core factory stays disabled."""
        # Arrange
        registry = mock.MagicMock()
        registration_error = RuntimeError("persistence registration failed")
        registry.register_codecs.side_effect = registration_error
        resolver_factory = mock.MagicMock()
        event_manager = mock.MagicMock()

        # Act
        with (
            mock.patch.object(extension.handlers, "register_plugins") as register_handlers,
            mock.patch.object(extension, "get_registry", return_value=registry),
            mock.patch.object(extension, "get_resolver_factory", return_value=resolver_factory),
            mock.patch.object(extension, "_get_event_manager_instance", return_value=event_manager),
        ):
            with self.assertRaises(RuntimeError) as error_context:
                extension.ComfyUICoreExtension().on_startup("lightspeed.trex.comfyui.core")

        # Assert
        self.assertIs(error_context.exception, registration_error)
        self.assertTrue(extension._shutting_down)
        resolver_factory.unregister_plugins.assert_called_once_with(extension.RESOLVER_PLUGINS)
        registry.unregister_codecs.assert_not_called()
        register_handlers.assert_not_called()
        event_manager.register_global_custom_event.assert_not_called()

    async def test_extension_startup_rolls_back_persistence_codecs_when_handler_registration_fails(self) -> None:
        """A failed handler registration cannot leave ComfyUI codecs partially registered."""
        # Arrange
        registry = mock.MagicMock()
        resolver_factory = mock.MagicMock()
        registration_error = RuntimeError("handler registration failed")
        event_manager = mock.MagicMock()

        # Act
        with (
            mock.patch.object(extension.handlers, "register_plugins", side_effect=registration_error),
            mock.patch.object(extension, "get_registry", return_value=registry),
            mock.patch.object(extension, "get_resolver_factory", return_value=resolver_factory),
            mock.patch.object(extension, "_get_event_manager_instance", return_value=event_manager),
        ):
            with self.assertRaises(RuntimeError) as error_context:
                extension.ComfyUICoreExtension().on_startup("lightspeed.trex.comfyui.core")

        # Assert
        self.assertIs(error_context.exception, registration_error)
        resolver_factory.register_plugins.assert_called_once_with(extension.RESOLVER_PLUGINS)
        resolver_factory.unregister_plugins.assert_called_once_with(extension.RESOLVER_PLUGINS)
        registry.register_codecs.assert_called_once_with(extension.COMFYUI_CODECS)
        registry.unregister_codecs.assert_called_once_with(extension.COMFYUI_CODECS)
        event_manager.register_global_custom_event.assert_not_called()
        self.assertTrue(extension._shutting_down)

    async def test_extension_startup_rolls_back_all_plugins_when_event_registration_fails(self) -> None:
        """A failed shared-event registration rolls back every earlier plugin registration."""
        # Arrange
        registry = mock.MagicMock()
        resolver_factory = mock.MagicMock()
        event_manager = mock.MagicMock()
        registration_error = RuntimeError("event registration failed")
        event_manager.register_global_custom_event.side_effect = registration_error

        # Act
        with (
            mock.patch.object(extension.handlers, "register_plugins") as register_handlers,
            mock.patch.object(extension.handlers, "unregister_plugins") as unregister_handlers,
            mock.patch.object(extension, "get_registry", return_value=registry),
            mock.patch.object(extension, "get_resolver_factory", return_value=resolver_factory),
            mock.patch.object(extension, "_get_event_manager_instance", return_value=event_manager),
        ):
            with self.assertRaises(RuntimeError) as error_context:
                extension.ComfyUICoreExtension().on_startup("lightspeed.trex.comfyui.core")

        # Assert
        self.assertIs(error_context.exception, registration_error)
        register_handlers.assert_called_once_with([ComfyUIJobApplyHandler])
        unregister_handlers.assert_called_once_with([ComfyUIJobApplyHandler])
        registry.unregister_codecs.assert_called_once_with(extension.COMFYUI_CODECS)
        resolver_factory.unregister_plugins.assert_called_once_with(extension.RESOLVER_PLUGINS)
        event_manager.unregister_global_custom_event.assert_not_called()
        self.assertTrue(extension._shutting_down)

    async def test_extension_shutdown_invalidates_instances_and_unregisters_handler(self) -> None:
        """Extension shutdown destroys cached cores and unregisters the handler."""
        # Arrange
        cleanup_order = []
        instance = mock.MagicMock()
        instance.destroy.side_effect = lambda: cleanup_order.append("instance")
        extension._instances["texturecraft"] = instance
        extension._started = True
        resolver_factory = mock.MagicMock()
        resolver_factory.unregister_plugins.side_effect = lambda _plugins: cleanup_order.append("resolvers")
        event_manager = mock.MagicMock()
        event_manager.unregister_global_custom_event.side_effect = lambda _name: cleanup_order.append("event")

        # Act
        with (
            mock.patch.object(
                extension.handlers,
                "unregister_plugins",
                side_effect=lambda _plugins: cleanup_order.append("handler"),
            ) as unregister_plugins,
            mock.patch.object(extension, "get_resolver_factory", return_value=resolver_factory),
            mock.patch.object(extension, "_get_event_manager_instance", return_value=event_manager),
        ):
            extension.ComfyUICoreExtension().on_shutdown()

        # Assert
        unregister_plugins.assert_called_once_with([ComfyUIJobApplyHandler])
        resolver_factory.unregister_plugins.assert_called_once_with(extension.RESOLVER_PLUGINS)
        event_manager.unregister_global_custom_event.assert_called_once_with(extension.COMFYUI_EVENT_NAME)
        instance.destroy.assert_called_once_with()
        self.assertEqual(cleanup_order, ["handler", "instance", "event", "resolvers"])
        self.assertEqual(extension._instances, {})
