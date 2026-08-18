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

from lightspeed.trex.asset_pipeline.core.steps import CollectTexturesStep, UpdateTexturesStep
from lightspeed.trex.asset_pipeline.core import (
    MaterialType,
    RemixAssetItem,
    RemixAssetPipelineContext,
)


_PROJECT_STAGE = "usd/project_example/combined.usda"
_RESOURCE_CONTEXT = "asset_pipeline_resource_project"


class TestUpdateTexturesE2E(omni.kit.test.AsyncTestCase):
    async def test_update_textures_writes_processed_paths(self):
        """Texture update writes processed texture paths back into model bindings."""
        async with open_test_project(_PROJECT_STAGE, context_name=_RESOURCE_CONTEXT) as project_url:
            # Step 1: Use the copied shared resource project because this step mutates the USD file.
            project_path = pathlib.Path(project_url.path).parent
            processed_path = project_path / "processed" / "metallic.dds"
            processed_path.parent.mkdir()
            processed_path.write_text("")
            item = RemixAssetItem.from_model(pathlib.Path(project_url.path), MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item], output_dir=processed_path.parent)

            try:
                # Step 2: Collect the existing resource-project bindings and point one binding at a processed texture.
                await CollectTexturesStep().run(context)
                binding = next(
                    binding for binding in item.texture_bindings if binding.input_name == "inputs:metallic_texture"
                )
                binding.texture.path = processed_path

                # Step 3: Run the texture-update step against the real USD stage.
                await UpdateTexturesStep().run(context)

                # Step 4: Verify the saved USD shader input now points at the processed texture path.
                stage = context.open_stage(pathlib.Path(project_url.path))
                attr = stage.GetPrimAtPath(binding.shader_path).GetAttribute(binding.input_name)
                self.assertEqual(attr.Get().path, "metallic.dds")
            finally:
                context.close_stage_cache()
