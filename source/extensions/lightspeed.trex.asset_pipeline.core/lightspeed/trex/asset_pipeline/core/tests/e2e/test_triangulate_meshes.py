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

import omni.kit.test
from omni.flux.utils.tests.context_managers import open_test_project
from pxr import UsdGeom

from lightspeed.trex.asset_pipeline.core.steps import TriangulateMeshesStep
from lightspeed.trex.asset_pipeline.core import MaterialType, RemixAssetItem, RemixAssetPipelineContext


_QUAD_MODEL = "usd/project_example/assets/models/cube.usda"
_RESOURCE_CONTEXT = "asset_pipeline_resource_project"
_TRIANGULATED_MODEL = "usd/project_example/assets/ingested/cube.usda"


class TestTriangulateMeshesE2E(omni.kit.test.AsyncTestCase):
    async def test_triangulate_meshes_should_run_when_model_has_quad_faces(self):
        """Triangulation detects model meshes with non-triangle faces."""
        async with open_test_project(_QUAD_MODEL, context_name=_RESOURCE_CONTEXT) as project_url:
            # Step 1: Use the shared resource model asset that still contains quad mesh faces.
            item = RemixAssetItem.from_model(pathlib.Path(project_url.path), MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item])
            step = TriangulateMeshesStep()

            try:
                # Step 2: Ask the triangulation step whether this real stage has work.
                should_run = step.should_run(context)
            finally:
                context.close_stage_cache()

            # Step 3: Verify the real USD face topology was detected as requiring triangulation.
            self.assertTrue(should_run)

    async def test_triangulate_meshes_should_not_run_when_model_has_only_triangles(self):
        """Triangulation skips model meshes that are already triangulated."""
        async with open_test_project(_TRIANGULATED_MODEL, context_name=_RESOURCE_CONTEXT) as project_url:
            # Step 1: Use the shared resource ingested model asset that already contains only triangles.
            item = RemixAssetItem.from_model(pathlib.Path(project_url.path), MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item])
            step = TriangulateMeshesStep()

            try:
                # Step 2: Ask the triangulation step whether this real stage has work.
                should_run = step.should_run(context)
            finally:
                context.close_stage_cache()

            # Step 3: Verify the real USD face topology was detected as already triangulated.
            self.assertFalse(should_run)

    async def test_triangulate_meshes_converts_quad_faces(self):
        """Triangulation matches the validation fan triangulation behavior."""
        async with open_test_project(_QUAD_MODEL, context_name=_RESOURCE_CONTEXT) as project_url:
            # Step 1: Use the copied shared resource model asset because this step mutates the USD file.
            item = RemixAssetItem.from_model(pathlib.Path(project_url.path), MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item])
            step = TriangulateMeshesStep()

            try:
                # Step 2: Run the triangulation step against the real USD stage.
                await step.run(context)

                # Step 3: Reopen the stage through the ingestion context and verify the saved mesh topology.
                stage = context.open_stage(pathlib.Path(project_url.path))
                self.assertTrue(_all_model_meshes_are_triangulated(stage))
            finally:
                context.close_stage_cache()


def _all_model_meshes_are_triangulated(stage) -> bool:
    mesh_prims = [prim for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh)]
    return bool(mesh_prims) and all(
        set(UsdGeom.Mesh(prim).GetFaceVertexCountsAttr().Get()) == {3} for prim in mesh_prims
    )
