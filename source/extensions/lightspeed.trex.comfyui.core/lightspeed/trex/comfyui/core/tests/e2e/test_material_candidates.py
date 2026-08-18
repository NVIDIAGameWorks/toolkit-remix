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
import tempfile
from unittest.mock import AsyncMock, patch

import omni.usd
from lightspeed.trex.comfyui.core.api import ComfyUIAPI
from lightspeed.trex.comfyui.core.core import ComfyUICore
from lightspeed.trex.comfyui.core.job import ComfyUIJob
from lightspeed.trex.comfyui.core.models import ComfyUIWorkflowRequest, Workflow
from omni.kit.test import AsyncTestCase
from pxr import Sdf, UsdGeom, UsdShade


class TestUsdMaterialCandidatesE2E(AsyncTestCase):
    """Tests material discovery through the live USD context and native schemas."""

    async def setUp(self) -> None:
        """Build one native stage in the product USD context."""
        self._context = omni.usd.get_context()
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="comfyui-material-candidates-")
        root_layer = Sdf.Layer.CreateNew(str(pathlib.Path(self._temporary_directory.name) / "project.usda"))
        await self._context.open_stage_async(root_layer.identifier)
        stage = self._context.get_stage()
        UsdGeom.Xform.Define(stage, "/Asset")
        material = UsdShade.Material.Define(stage, "/Asset/Looks/Shared")
        UsdShade.Shader.Define(stage, "/Asset/Looks/Shared/Shader")

        first_mesh = UsdGeom.Mesh.Define(stage, "/Asset/First")
        UsdShade.MaterialBindingAPI(first_mesh).Bind(material)
        subset = UsdGeom.Subset.Define(stage, "/Asset/First/Subset")
        UsdShade.MaterialBindingAPI(subset).Bind(material)
        second_mesh = UsdGeom.Mesh.Define(stage, "/Asset/Second")
        UsdShade.MaterialBindingAPI(second_mesh).Bind(material)

        prototype = UsdGeom.Xform.Define(stage, "/Prototype")
        instance_material = UsdShade.Material.Define(stage, "/Prototype/Looks/InstanceMaterial")
        prototype_mesh = UsdGeom.Mesh.Define(stage, "/Prototype/Mesh")
        UsdShade.MaterialBindingAPI(prototype_mesh).Bind(instance_material)
        instance = stage.DefinePrim("/Instances/Instance")
        instance.GetReferences().AddInternalReference(prototype.GetPath())
        instance.SetInstanceable(True)
        stage.GetRootLayer().Save()

        self._core = ComfyUICore("")
        with (
            patch.object(ComfyUIAPI, "ping", new=AsyncMock()),
            patch.object(ComfyUIAPI, "get_workflow_list", new=AsyncMock(return_value=[])),
        ):
            await self._core.connect()
        self._core.set_workflow(Workflow(name="Material candidates"))

    async def tearDown(self) -> None:
        """Close the live test stage and release its core subscriptions."""
        self._core.destroy()
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()
        self._temporary_directory.cleanup()

    async def _prepare_generation_job(self, prim_path: str) -> ComfyUIJob:
        """Prepare one product graph through the public submission API.

        Args:
            prim_path: Selected prim path supplied by the user-facing submission flow.

        Returns:
            ComfyUI generation job produced for the resolved material.
        """
        submission = await self._core.prepare_submission([prim_path, prim_path])
        self.assertEqual(len(submission.graphs), 1)
        generation_job = submission.graphs[0].jobs[0]
        self.assertIsInstance(generation_job, ComfyUIJob)
        return generation_job

    async def test_parent_xform_resolves_bound_material(self) -> None:
        """A selected parent resolves each mesh owner once."""
        prim_path = "/Asset"

        # Submit the duplicated parent selection through the public product-preparation flow.
        generation_job = await self._prepare_generation_job(prim_path)

        self.assertEqual(generation_job.material_path, "/Asset/Looks/Shared")
        self.assertEqual(generation_job.prim_paths, ["/Asset/First", "/Asset/Second"])

    async def test_mesh_resolves_bound_material(self) -> None:
        """A selected mesh resolves its bound material and itself as owner."""
        prim_path = "/Asset/First"

        # Submit the repeated mesh selection through the public product-preparation flow.
        generation_job = await self._prepare_generation_job(prim_path)

        self.assertEqual(generation_job.material_path, "/Asset/Looks/Shared")
        self.assertEqual(generation_job.prim_paths, ["/Asset/First"])

    async def test_geom_subset_resolves_parent_mesh_owner(self) -> None:
        """A selected material subset records its parent mesh as owner."""
        prim_path = "/Asset/First/Subset"

        # Submit the repeated subset selection through the public product-preparation flow.
        generation_job = await self._prepare_generation_job(prim_path)

        self.assertEqual(generation_job.material_path, "/Asset/Looks/Shared")
        self.assertEqual(generation_job.prim_paths, ["/Asset/First"])

    async def test_material_resolves_itself_without_mesh_owner(self) -> None:
        """A selected material remains a candidate without inventing an owner."""
        prim_path = "/Asset/Looks/Shared"

        # Submit the directly selected material through the public product-preparation flow.
        generation_job = await self._prepare_generation_job(prim_path)

        self.assertEqual(generation_job.material_path, "/Asset/Looks/Shared")
        self.assertEqual(generation_job.prim_paths, [])

    async def test_anonymous_stage_uses_queue_owned_processed_output(self) -> None:
        """An unsaved live stage can prepare all expensive work before project Apply is available."""
        # Replace the saved fixture with a real anonymous stage and one bound material.
        await self._context.close_stage_async()
        await self._context.new_stage_async()
        stage = self._context.get_stage()
        material = UsdShade.Material.Define(stage, "/Asset/Looks/Shared")
        mesh = UsdGeom.Mesh.Define(stage, "/Asset/Mesh")
        UsdShade.MaterialBindingAPI(mesh).Bind(material)

        # Prepare the graph through the public product flow without saving the stage.
        submission = await self._core.prepare_submission([str(mesh.GetPath())])
        graph = submission.graphs[0]
        generation_job = graph.jobs[0]
        workflow_request = next(
            binding.value
            for binding in graph.literal_inputs
            if binding.job_id == generation_job.job_id and binding.port is ComfyUIJob.WORKFLOW_REQUEST
        )

        # The texture-processing child will use its durable queue job directory instead of an invalid anon URL.
        self.assertIsInstance(workflow_request, ComfyUIWorkflowRequest)
        self.assertIsNone(workflow_request.output_url)

    async def test_shader_resolves_parent_material_without_mesh_owner(self) -> None:
        """A selected shader resolves its parent material without inventing an owner."""
        prim_path = "/Asset/Looks/Shared/Shader"

        # Submit the shader selection through the public product-preparation flow.
        generation_job = await self._prepare_generation_job(prim_path)

        self.assertEqual(generation_job.material_path, "/Asset/Looks/Shared")
        self.assertEqual(generation_job.prim_paths, [])

    async def test_instance_resolves_proxy_material_and_mesh_owner(self) -> None:
        """A selected instance resolves its proxy material and proxy mesh owner."""
        prim_path = "/Instances/Instance"

        # Submit the instance through the public flow so composed instance proxies are exercised.
        generation_job = await self._prepare_generation_job(prim_path)

        self.assertEqual(generation_job.material_path, "/Instances/Instance/Looks/InstanceMaterial")
        self.assertEqual(generation_job.prim_paths, ["/Instances/Instance/Mesh"])
