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
from unittest.mock import AsyncMock, patch

import omni.usd
from omni.kit.test import AsyncTestCase
from pxr import Sdf, UsdShade

from ...api import ComfyUIAPI
from ...core import ComfyUICore
from ...enums import OutputApplyBehavior, RemixType
from ...models import Workflow, WorkflowInput, WorkflowOutput
from ...resolvers import SelectedMeshResolver, SelectedTextureResolver
from .test_job_apply import (
    _OWNER_A,
    _OWNER_B,
    _copy_model_fixture,
    _get_normal_fixture_path,
    _make_capture_usda,
    _make_project_usda,
    _material_path,
    _workflow_request,
)

__all__ = ("TestComfyUIJobCandidatesE2E",)


class TestComfyUIJobCandidatesE2E(AsyncTestCase):
    """Check mesh Append destinations and texture inputs through real USD submission.

    Coverage limit: no ComfyUI server runs in CI. The ComfyUI HTTP client (ping, catalog) returns recorded responses
    so the core connects. These tests do not cover that service path. They cover job preparation on real USD.
    """

    async def setUp(self) -> None:
        """Create a project with two reference owners and a texture-only workflow."""
        self._context = omni.usd.get_context("")
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()
        temporary_directory = tempfile.TemporaryDirectory(prefix="comfyui-job-candidates-")
        self.addCleanup(temporary_directory.cleanup)
        self._temp_path = pathlib.Path(temporary_directory.name)
        _copy_model_fixture(self._temp_path / "model.usda", _get_normal_fixture_path())
        shutil.copy2(_get_normal_fixture_path(), self._temp_path / "textures" / "other_albedo.png")
        owner_paths = (_OWNER_A, _OWNER_B)
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
        self._stage = self._context.get_stage()
        self._stage.SetEditTarget(edit_layer)
        for owner_path in owner_paths:
            material = UsdShade.Material(self._stage.GetPrimAtPath(_material_path(owner_path)))
            UsdShade.MaterialBindingAPI.Apply(self._stage.GetPrimAtPath(owner_path)).Bind(material)
            shader = UsdShade.Shader(self._stage.GetPrimAtPath(f"{_material_path(owner_path)}/Shader"))
            shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset).Set(
                Sdf.AssetPath("./textures/source_albedo.png")
            )
        for api_patch in (
            patch.object(ComfyUIAPI, "ping", new=AsyncMock(return_value={})),
            patch.object(ComfyUIAPI, "get_workflow_list", new=AsyncMock(return_value=[])),
            patch.object(ComfyUIAPI, "get_workflow_types", new=AsyncMock(return_value=[])),
        ):
            api_patch.start()
            self.addCleanup(api_patch.stop)
        self._core = ComfyUICore("")
        self.addCleanup(self._core.destroy)
        await self._core.connect()
        self._core.set_workflow(
            Workflow(
                name="Texture to mesh",
                api={"1": {"class_type": "LoadImage", "inputs": {"image": ""}}},
                inputs=[
                    WorkflowInput(
                        port_id="1.inputs.image",
                        label="Image",
                        native_type=pathlib.Path,
                        default_value=pathlib.Path(),
                        value=SelectedTextureResolver(context_name=""),
                        remix_type=RemixType.TEXTURE_FILE_PATH,
                    )
                ],
                output_specs=[
                    WorkflowOutput(
                        node_id="2",
                        remix_type=RemixType.MESH_FILE_PATH,
                        apply_behavior=OutputApplyBehavior.APPEND,
                    )
                ],
            )
        )

    async def tearDown(self) -> None:
        """Close the stage before the temporary project is removed."""
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()
        self._stage = None

    async def test_selected_child_mesh_supplies_texture_to_mesh_workflow(self):
        """A selected child's material supplies the texture, not its unbound reference owner."""
        owner = self._stage.GetPrimAtPath(_OWNER_A)
        UsdShade.MaterialBindingAPI(owner).UnbindAllBindings()
        child_path = f"{_OWNER_A}/Quad"
        child = self._stage.GetPrimAtPath(child_path)
        self.assertTrue(UsdShade.MaterialBindingAPI(child).ComputeBoundMaterial()[0])
        self.assertFalse(UsdShade.MaterialBindingAPI(owner).ComputeBoundMaterial()[0])
        mesh_and_texture = Workflow(
            name="Selected mesh and texture",
            api={
                "1": {"class_type": "LoadImage", "inputs": {"image": ""}},
                "3": {"class_type": "RTXRemixImportMeshNode", "inputs": {"mesh_file_path": ""}},
            },
            inputs=[
                WorkflowInput(
                    port_id="1.inputs.image",
                    label="Image",
                    native_type=pathlib.Path,
                    default_value=pathlib.Path(),
                    value=SelectedTextureResolver(context_name=""),
                    remix_type=RemixType.TEXTURE_FILE_PATH,
                ),
                WorkflowInput(
                    port_id="3.inputs.mesh_file_path",
                    label="Mesh",
                    native_type=pathlib.Path,
                    default_value=pathlib.Path(),
                    value=SelectedMeshResolver(context_name=""),
                    remix_type=RemixType.MESH_FILE_PATH,
                ),
            ],
            output_specs=[
                WorkflowOutput(
                    node_id="2", remix_type=RemixType.MESH_FILE_PATH, apply_behavior=OutputApplyBehavior.APPEND
                )
            ],
        )
        # The setUp workflow is the texture-only (image-to-mesh) shape, which has no mesh input.
        for workflow in (self._core.workflow, mesh_and_texture):
            with self.subTest(workflow=workflow.name):
                self._core.set_workflow(workflow)

                submission = await self._core.prepare_submission([child_path])

                self.assertEqual(len(submission.graphs), 1)
                graph = submission.graphs[0]
                self.assertIsNone(graph.jobs[0].skip_reason)
                request = _workflow_request(graph)
                textures = [
                    pathlib.Path(binding.source).resolve()
                    for binding in request.input_bindings
                    if binding.remix_type == RemixType.TEXTURE_FILE_PATH
                ]
                self.assertEqual(textures, [self._temp_path / "textures" / "source_albedo.png"])
                target = next(job for job in graph.jobs if job.apply_binding).apply_binding.target
                self.assertEqual([owner.owner_prim_path for owner in target.reference_targets], [_OWNER_A])

    async def test_texture_only_mesh_output_deduplicates_owner_references(self):
        """One owner with two source references receives one generated model."""
        shutil.copy2(self._temp_path / "model.usda", self._temp_path / "second_model.usda")
        owner = self._stage.GetPrimAtPath(_OWNER_A)
        owner.GetReferences().AddReference("./second_model.usda")
        self.assertEqual(len(omni.usd.get_composed_references_from_prim(owner)), 2)

        submission = await self._core.prepare_submission([_OWNER_A])

        self.assertEqual(len(submission.graphs), 1)
        graph = submission.graphs[0]
        self.assertIsNone(graph.jobs[0].skip_reason)
        target = next(job for job in graph.jobs if job.apply_binding).apply_binding.target
        self.assertEqual([owner.owner_prim_path for owner in target.reference_targets], [_OWNER_A])

    async def test_texture_only_mesh_output_keeps_distinct_texture_bindings(self):
        """Owners with different textures receive separate generation requests."""
        shader = UsdShade.Shader(self._stage.GetPrimAtPath(f"{_material_path(_OWNER_B)}/Shader"))
        shader.GetInput("diffuse_texture").Set(Sdf.AssetPath("./textures/other_albedo.png"))

        submission = await self._core.prepare_submission([_OWNER_A, _OWNER_B])

        self.assertEqual(len(submission.graphs), 2)
        owners_and_textures = []
        for graph in submission.graphs:
            self.assertIsNone(graph.jobs[0].skip_reason)
            request = _workflow_request(graph)
            target = next(job for job in graph.jobs if job.apply_binding).apply_binding.target
            owners_and_textures.append(
                (
                    [owner.owner_prim_path for owner in target.reference_targets],
                    [pathlib.Path(binding.source).resolve() for binding in request.input_bindings],
                )
            )
        self.assertEqual(
            owners_and_textures,
            [
                ([_OWNER_A], [self._temp_path / "textures" / "source_albedo.png"]),
                ([_OWNER_B], [self._temp_path / "textures" / "other_albedo.png"]),
            ],
        )

    async def test_texture_only_mesh_output_merges_equal_texture_bindings(self):
        """Owners with the same texture share a graph with both destinations."""
        submission = await self._core.prepare_submission([_OWNER_A, _OWNER_B])

        self.assertEqual(len(submission.graphs), 1)
        graph = submission.graphs[0]
        self.assertIsNone(graph.jobs[0].skip_reason)
        target = next(job for job in graph.jobs if job.apply_binding).apply_binding.target
        self.assertEqual([owner.owner_prim_path for owner in target.reference_targets], [_OWNER_A, _OWNER_B])
        self.assertEqual(
            [pathlib.Path(binding.source).resolve() for binding in _workflow_request(graph).input_bindings],
            [self._temp_path / "textures" / "source_albedo.png"],
        )
