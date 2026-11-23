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

__all__ = ["TestAlphaCardToMeshSubmissionE2E"]

import asyncio
from pathlib import Path

import numpy as np
import omni.usd
from carb.settings import get_settings
from lightspeed.common import constants
from lightspeed.trex.alpha_cutout.core import ALPHA_TEST_ALWAYS
from lightspeed.trex.alpha_cutout.modifier.job import AlphaCardToMeshJob
from lightspeed.trex.alpha_cutout.modifier.modifier import AlphaCardToMesh
from lightspeed.trex.alpha_cutout.modifier.values import MATERIAL_KEY, MESHES_KEY, PRIM_PATH_KEY
from lightspeed.trex.asset_modifiers.core import AssetModifiersCore
from lightspeed.trex.asset_modifiers.core.settings import AssetModifierSettings
from lightspeed.trex.asset_pipeline.core.jobs import MeshOptimizationJob
from omni.flux.job_queue.core import get_job_queue
from omni.flux.job_queue.core.enums import ApplyDisposition, JobState
from omni.flux.job_queue.core.handlers import get_apply_executor
from omni.flux.job_queue.core.models import QueueJob, UsageSnapshot
from omni.flux.job_queue.core.settings import JobQueueSettings
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from PIL import Image
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

_RESOURCES_EXT = "lightspeed.trex.app.resources"
_PROJECT = "usd/project_example/combined.usda"
_OWNER = "/RootNode/meshes/mesh_0AB745B8BEE1F16B"
_MESH = f"{_OWNER}/mesh"
_SHADER_TEXTURE_ATTR = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:diffuse_texture"


def _write_disc_texture(path: Path) -> str:
    size = 64
    rows, cols = np.mgrid[0:size, 0:size]
    alpha = ((((rows - 31.5) ** 2 + (cols - 31.5) ** 2) <= 24**2).astype(np.uint8)) * 255
    rgba = np.dstack([np.full_like(alpha, 90)] * 3 + [alpha])
    Image.fromarray(rgba, "RGBA").save(path)
    return str(path)


def _remix_reference_urls(owner: Usd.Prim) -> list[Path]:
    return [
        Path(Sdf.ComputeAssetPathRelativeToLayer(layer, reference.assetPath)).resolve()
        for child in owner.GetChildren()
        if child.GetAttribute(constants.IS_REMIX_REF_ATTR).Get() is True
        for reference, layer in omni.usd.get_composed_references_from_prim(child)
    ]


class TestAlphaCardToMeshSubmissionE2E(AsyncTestCase):
    """Run the registered modifier against the example project."""

    async def setUp(self) -> None:
        self._core = AssetModifiersCore("")
        AssetModifierSettings().set_active_modifier_name(AlphaCardToMesh.name)

    async def tearDown(self) -> None:
        get_settings().destroy_item(AssetModifierSettings.get_modifier_key(AlphaCardToMesh))
        AssetModifierSettings().set_active_modifier_name("")

    @staticmethod
    def _prepare_project(project_url: OmniUrl) -> Usd.Stage:
        """Give the fixture material a texture with transparency and target the replacement layer."""
        stage = omni.usd.get_context("").get_stage()
        project_dir = OmniUrl(project_url.parent_url)
        texture = _write_disc_texture(Path(project_dir.path) / "disc.png")
        replacement_layer = Sdf.Layer.FindOrOpen(str(project_dir / "replacements.usda"))
        stage.SetEditTarget(Usd.EditTarget(replacement_layer))
        stage.GetAttributeAtPath(_SHADER_TEXTURE_ATTR).Set(Sdf.AssetPath(texture))
        return stage

    async def test_prepare_submission_lists_the_capture_mesh_with_a_material_snapshot(self) -> None:
        async with open_test_project(_PROJECT, ext_name=_RESOURCES_EXT) as project_url:
            # Arrange
            stage = self._prepare_project(project_url)

            # Act
            graphs, skipped = await self._core.prepare_submission([_MESH])

            # Assert
            self.assertEqual(skipped, {})
            (job,) = [job for job in graphs[0].jobs if isinstance(job, AlphaCardToMeshJob)]
            (entry,) = job.values[MESHES_KEY]
            self.assertTrue(entry[PRIM_PATH_KEY].endswith("/mesh"))
            self.assertIsNotNone(entry[MATERIAL_KEY])
            self.assertEqual(job.values["alpha_threshold"], 128)

            # A mesh without a diffuse texture is reported instead of submitted.
            stage.GetAttributeAtPath(_SHADER_TEXTURE_ATTR).Set(Sdf.AssetPath(""))
            graphs, skipped = await self._core.prepare_submission([_MESH])
            self.assertEqual(graphs, [])
            self.assertIn("diffuse texture", skipped[_MESH])

    async def test_queue_run_cuts_the_mesh_publishes_it_and_replaces_the_capture_reference(self) -> None:
        queue = get_job_queue()
        queue_settings = JobQueueSettings()
        original_queue_settings = (queue_settings.scheduler_enabled, queue_settings.auto_apply)
        original_graph_ids = {snapshot.graph_id for snapshot in queue.get_graph_snapshots()}
        queue_settings.set_scheduler_enabled(True)
        queue_settings.set_auto_apply(True)
        try:
            async with open_test_project(_PROJECT, ext_name=_RESOURCES_EXT) as project_url:
                # Arrange
                stage = self._prepare_project(project_url)
                owner = stage.GetPrimAtPath(_OWNER)
                graphs, skipped = await self._core.prepare_submission([_MESH])
                self.assertEqual(skipped, {})
                (graph,) = graphs

                # Act
                queue.submit_graphs(graphs)
                async with asyncio.timeout(120):
                    for job in graph.jobs:
                        await QueueJob(queue, graph.graph_id, job.job_id).outputs()
                    await get_apply_executor().wait_idle()
                await ui_test.wait_n_updates(4)

                # Assert
                for job in graph.jobs:
                    snapshot = queue.get_job_snapshot(job.job_id)
                    self.assertIs(snapshot.state, JobState.DONE, snapshot.error or snapshot.state_reason)
                (cutout_job,) = [job for job in graph.jobs if isinstance(job, AlphaCardToMeshJob)]
                cutout_outputs = queue.get_job_outputs(cutout_job.job_id)
                (report_item,) = cutout_outputs[AlphaCardToMeshJob.REPORT].meshes
                self.assertIsNone(report_item.skip_reason)
                self.assertGreater(report_item.source_faces, 0)
                self.assertGreater(report_item.faces, 2)
                self.assertTrue(
                    AlphaCardToMesh()
                    .summarize_result(cutout_outputs)
                    .startswith("Alpha Card to Mesh: Converted 1 of 1 mesh\nmesh: ")
                )
                (mesh_job,) = [job for job in graph.jobs if isinstance(job, MeshOptimizationJob)]
                applied = queue.get_job_snapshot(mesh_job.job_id)
                self.assertIs(applied.apply_disposition, ApplyDisposition.APPLIED, applied.apply_error)
                result = queue.get_job_outputs(mesh_job.job_id)[MeshOptimizationJob.OPTIMIZED_MESH]
                output = Path(result.asset_url).resolve()
                self.assertEqual(_remix_reference_urls(owner), [output])
                output_stage = Usd.Stage.Open(str(output))
                (output_mesh,) = [prim for prim in output_stage.Traverse() if prim.IsA(UsdGeom.Mesh)]
                self.assertGreater(len(UsdGeom.Mesh(output_mesh).GetFaceVertexCountsAttr().Get()), 2)
                # The published cutout keeps the scale of the capture mesh it replaces.
                source_stage = Usd.Stage.Open(cutout_job.source_url)
                source_mesh = source_stage.GetPrimAtPath(cutout_job.values[MESHES_KEY][0][PRIM_PATH_KEY])
                self.assertTrue(
                    Gf.IsClose(
                        UsdGeom.XformCache().GetLocalToWorldTransform(output_mesh),
                        UsdGeom.XformCache().GetLocalToWorldTransform(source_mesh),
                        1e-6,
                    )
                )
                material, _ = UsdShade.MaterialBindingAPI(output_mesh).ComputeBoundMaterial()
                shader = UsdShade.Shader(material.GetPrim().GetChild("Shader"))
                self.assertEqual(shader.GetInput("alpha_test_type").Get(), ALPHA_TEST_ALWAYS)
                self.assertEqual(shader.GetSourceAssetSubIdentifier("mdl"), "AperturePBR_Opacity")
                texture = shader.GetInput("diffuse_texture").Get().path
                self.assertFalse(Path(texture).is_absolute())

                # Revert restores the capture source.
                await asyncio.wait_for(get_apply_executor().revert(mesh_job.job_id), 10)
                self.assertNotEqual(_remix_reference_urls(owner), [output])
        finally:
            try:
                await asyncio.wait_for(get_apply_executor().wait_idle(), 30)
                added = [
                    snapshot.graph_id
                    for snapshot in queue.get_graph_snapshots()
                    if snapshot.graph_id not in original_graph_ids
                ]
                if added:
                    queue.delete_graphs(added, UsageSnapshot())
            finally:
                queue_settings.set_scheduler_enabled(original_queue_settings[0])
                queue_settings.set_auto_apply(original_queue_settings[1])
