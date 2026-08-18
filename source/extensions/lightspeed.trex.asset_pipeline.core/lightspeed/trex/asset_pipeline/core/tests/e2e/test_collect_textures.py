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

import omni.usd
import omni.kit.test
from lightspeed.common.constants import MATERIAL_INPUTS_NORMALMAP_ENCODING
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP, TextureTypes
from omni.flux.utils.tests.context_managers import open_test_project
from pxr import Sdf, Usd, UsdShade

from lightspeed.trex.asset_pipeline.core.steps import CollectTexturesStep
from lightspeed.trex.asset_pipeline.core import MaterialType, RemixAssetItem, RemixAssetPipelineContext


_PROJECT_STAGE = "usd/project_example/combined.usda"
_RESOURCE_CONTEXT = "asset_pipeline_resource_project"


class TestCollectTexturesE2E(omni.kit.test.AsyncTestCase):
    async def test_collect_textures_creates_texture_records_and_bindings(self):
        """Texture collection reads shader input names and records typed model bindings."""
        async with open_test_project(_PROJECT_STAGE, context_name=_RESOURCE_CONTEXT) as project_url:
            # Step 1: Use the shared Remix resource project with authored texture overrides.
            item = RemixAssetItem.from_model(pathlib.Path(project_url.path), MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item])

            try:
                # Step 2: Collect textures from the real USD shader inputs.
                await CollectTexturesStep().run(context)
            finally:
                context.close_stage_cache()

            # Step 3: Verify texture collection produced typed records from the shared project assets.
            self.assertEqual(len(item.textures), 4)
            self.assertEqual(len(item.texture_bindings), 4)
            self.assertEqual(
                {binding.input_name for binding in item.texture_bindings},
                {
                    "inputs:diffuse_texture",
                    "inputs:metallic_texture",
                    "inputs:normalmap_texture",
                    "inputs:reflectionroughness_texture",
                },
            )
            self.assertTrue(all(texture.path.exists() for texture in item.textures))

    async def test_collect_textures_uses_canonical_texture_input_map(self):
        """Texture collection iterates the shared shader-input map directly."""
        async with open_test_project(_PROJECT_STAGE, context_name=_RESOURCE_CONTEXT) as project_url:
            # Step 1: Use the shared Remix resource project with representative shader texture inputs.
            item = RemixAssetItem.from_model(pathlib.Path(project_url.path), MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item])

            try:
                # Step 2: Collect textures from the real USD shader inputs.
                await CollectTexturesStep().run(context)
            finally:
                context.close_stage_cache()

            # Step 3: Verify each collected binding type came from the shared texture input map.
            self.assertEqual(
                {binding.input_name: binding.texture.texture_type for binding in item.texture_bindings},
                {
                    TEXTURE_TYPE_INPUT_MAP[TextureTypes.DIFFUSE]: TextureTypes.DIFFUSE,
                    TEXTURE_TYPE_INPUT_MAP[TextureTypes.METALLIC]: TextureTypes.METALLIC,
                    TEXTURE_TYPE_INPUT_MAP[TextureTypes.NORMAL_DX]: TextureTypes.NORMAL_DX,
                    TEXTURE_TYPE_INPUT_MAP[TextureTypes.ROUGHNESS]: TextureTypes.ROUGHNESS,
                },
            )

    async def test_collect_textures_uses_resource_normal_input_as_directx_when_encoding_is_missing(self):
        """Normal texture type defaults to DirectX when the resource shader has no authored encoding."""
        async with open_test_project(_PROJECT_STAGE, context_name=_RESOURCE_CONTEXT) as project_url:
            # Step 1: Use the shared Remix resource project normal-map input.
            item = RemixAssetItem.from_model(pathlib.Path(project_url.path), MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item])

            try:
                # Step 2: Collect the normal texture from the real USD shader input.
                await CollectTexturesStep().run(context)
            finally:
                context.close_stage_cache()

            # Step 3: Verify normal type came from the shader encoding fallback, not from filename guessing.
            normal_binding = next(
                binding for binding in item.texture_bindings if binding.input_name == "inputs:normalmap_texture"
            )
            self.assertEqual(normal_binding.texture.texture_type, TextureTypes.NORMAL_DX)

    async def test_collect_textures_fails_on_unresolved_texture_path(self):
        """Opaque or missing imported texture references fail instead of silently skipping."""
        async with open_test_project(_PROJECT_STAGE, context_name=_RESOURCE_CONTEXT) as project_url:
            # Step 1: Open a copied shared resource project and remove one referenced source texture.
            project_path = pathlib.Path(project_url.path).parent
            (project_path / "sources" / "textures" / "T_MetalPanelWall_HeavyRust_normal.png").unlink()
            item = RemixAssetItem.from_model(pathlib.Path(project_url.path), MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item])

            try:
                # Step 2: Collecting textures from the real USD shader should fail clearly.
                with self.assertRaises(FileNotFoundError):
                    await CollectTexturesStep().run(context)
            finally:
                context.close_stage_cache()

    async def test_collect_textures_fails_on_unknown_normal_encoding(self):
        """Unknown authored normal encodings fail instead of silently defaulting to DirectX."""
        async with open_test_project(_PROJECT_STAGE, context_name=_RESOURCE_CONTEXT) as project_url:
            # Step 1: Open the copied shared resource project and corrupt the normal-map encoding.
            item = RemixAssetItem.from_model(pathlib.Path(project_url.path), MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item])
            stage = context.open_stage(item.value)
            shader_prim = _get_shader_with_normal_input(stage)
            encoding_attr = shader_prim.CreateAttribute(MATERIAL_INPUTS_NORMALMAP_ENCODING, Sdf.ValueTypeNames.Int)
            encoding_attr.Set(999)

            try:
                # Step 2: Collecting the real shader inputs should reject the unsupported encoding.
                with self.assertRaises(ValueError) as error:
                    await CollectTexturesStep().run(context)
            finally:
                context.close_stage_cache()

            # Step 3: Verify the failure explains the invalid encoding source.
            self.assertIn("Unknown normal map encoding", str(error.exception))


def _get_shader_with_normal_input(stage: Usd.Stage) -> Usd.Prim:
    for prim in stage.Traverse():
        if not prim.IsA(UsdShade.Material):
            continue

        shader_prim = omni.usd.get_shader_from_material(prim, get_prim=True)
        if shader_prim is not None and shader_prim.HasAttribute(TEXTURE_TYPE_INPUT_MAP[TextureTypes.NORMAL_OTH]):
            return shader_prim

    raise AssertionError("Expected the resource project to include a normal-map shader input")
