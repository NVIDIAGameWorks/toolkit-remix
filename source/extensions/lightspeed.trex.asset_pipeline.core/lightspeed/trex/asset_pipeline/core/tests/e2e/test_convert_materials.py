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

import omni.kit.app
import omni.kit.test
from omni.flux.utils.tests.context_managers import open_test_project
from pxr import UsdShade

from lightspeed.trex.asset_pipeline.core import MaterialType, RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.steps import ConvertMaterialsStep


_OPACITY_MATERIAL = "usd/project_example/materials/AperturePBR_Opacity.usda"
_RESOURCE_CONTEXT = "asset_pipeline_resource_project"


class TestConvertMaterialsE2E(omni.kit.test.AsyncTestCase):
    """Test material conversion against authored USD resources."""

    async def test_convert_materials_should_run_for_model_items(self):
        """Material conversion lets run handle exact authored shader resolution."""
        async with open_test_project(_OPACITY_MATERIAL, context_name=_RESOURCE_CONTEXT) as project_url:
            # Ask the production step about a real authored USD material instead of recreating shader data in the test.
            item = RemixAssetItem.from_model(pathlib.Path(project_url.path), MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item])

            should_run = ConvertMaterialsStep().should_run(context)

            self.assertTrue(should_run)

    async def test_convert_materials_converts_authored_omni_pbr_materials(self):
        """Material conversion updates a real authored OmniPBR stage through the public step API."""
        fixture_path = _get_material_converter_fixture_path()

        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = pathlib.Path(temp_dir) / fixture_path.name
            shutil.copy2(fixture_path, model_path)
            item = RemixAssetItem.from_model(model_path, MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item])

            try:
                # Convert the copied production fixture with the same step used by the asset pipeline.
                await ConvertMaterialsStep().run(context)

                # Every authored material now targets the requested Remix shader in the saved USD file.
                stage = context.open_stage(model_path)
                shader_names = {
                    shader.GetPrim().GetAttribute("info:mdl:sourceAsset:subIdentifier").Get()
                    for prim in stage.Traverse()
                    if prim.IsA(UsdShade.Shader)
                    for shader in (UsdShade.Shader(prim),)
                }
                self.assertEqual(shader_names, {"AperturePBR_Opacity"})
            finally:
                context.close_stage_cache()


def _get_material_converter_fixture_path() -> pathlib.Path:
    extension_root = pathlib.Path(
        omni.kit.app.get_app()
        .get_extension_manager()
        .get_extension_path_by_module("omni.flux.utils.material_converter")
    )
    return extension_root / "data" / "tests" / "usd" / "omni_pbr.usda"
