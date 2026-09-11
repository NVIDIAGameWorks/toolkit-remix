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
from pxr import Usd, UsdShade

from lightspeed.trex.asset_pipeline.core import RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.steps import ConvertMaterialsStep


_OPACITY_MATERIAL = "usd/project_example/materials/AperturePBR_Opacity.usda"
_RESOURCE_CONTEXT = "asset_pipeline_resource_project"


class TestConvertMaterialsE2E(omni.kit.test.AsyncTestCase):
    """Test material conversion against authored USD resources."""

    async def test_material_names_do_not_select_shader_output(self):
        """Material names do not override authored shader identifiers."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create OmniPBR materials with names that suggest different shader outputs.
            model_path = _write_model_stage(temp_dir, ["GlassMat", "TranslucentWindow", "BodyPaint"])
            item = RemixAssetItem.from_model(model_path)

            async with RemixAssetPipelineContext(items=[item]) as context:
                # Convert the model through the asset pipeline.
                await ConvertMaterialsStep().run(context)

                # Check that the authored shader identifiers take precedence over the material names.
                stage = await context.open_stage(model_path)
                subidentifiers = _collect_shader_subidentifiers_by_material(stage)
                self.assertEqual(set(subidentifiers.values()), {"AperturePBR_Opacity"})

    async def test_convert_materials_should_run_for_model_items(self):
        """Material conversion lets run handle exact authored shader resolution."""
        async with open_test_project(_OPACITY_MATERIAL, context_name=_RESOURCE_CONTEXT) as project_url:
            # Ask the production step about a real authored USD material instead of recreating shader data in the test.
            item = RemixAssetItem.from_model(pathlib.Path(project_url.path))
            context = RemixAssetPipelineContext(items=[item])

            should_run = ConvertMaterialsStep().should_run(context)

            self.assertTrue(should_run)

    async def test_convert_materials_converts_authored_omni_pbr_materials(self):
        """Material conversion updates a real authored OmniPBR stage through the public step API."""
        fixture_path = (
            pathlib.Path(
                omni.kit.app.get_app()
                .get_extension_manager()
                .get_extension_path_by_module("omni.flux.utils.material_converter")
            )
            / "data"
            / "tests"
            / "usd"
            / "omni_pbr.usda"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = pathlib.Path(temp_dir) / fixture_path.name
            shutil.copy2(fixture_path, model_path)
            item = RemixAssetItem.from_model(model_path)

            async with RemixAssetPipelineContext(items=[item]) as context:
                # Convert the copied production fixture with the same step used by the asset pipeline.
                await ConvertMaterialsStep().run(context)

                # Every authored material now targets the requested Remix shader in the saved USD file.
                stage = await context.open_stage(model_path)
                shader_names = {
                    shader.GetPrim().GetAttribute("info:mdl:sourceAsset:subIdentifier").Get()
                    for prim in stage.Traverse()
                    if prim.IsA(UsdShade.Shader)
                    for shader in (UsdShade.Shader(prim),)
                }
                self.assertTrue(
                    all(name.startswith("AperturePBR_") for name in shader_names),
                    f"Expected only AperturePBR shaders, got: {shader_names}",
                )


def _write_model_stage(temp_dir: str, material_names: list[str]) -> pathlib.Path:
    """Write a minimal on-disk USD stage with OmniPBR materials."""
    model_path = pathlib.Path(temp_dir) / "model.usda"
    materials_text = ""
    for name in material_names:
        materials_text += _MATERIAL_TEMPLATE.format(name=name)
    usda_text = _STAGE_TEMPLATE.format(materials=materials_text)
    model_path.write_text(usda_text)
    return model_path


_STAGE_TEMPLATE = """#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1.0
    upAxis = "Y"
)

def Xform "World"
{{
    def Scope "Looks"
    {{
{materials}
    }}
}}
"""

_MATERIAL_TEMPLATE = """        def Material "{name}"
        {{
            token outputs:mdl:displacement.connect = </World/Looks/{name}/{name}.outputs:out>
            token outputs:mdl:surface.connect = </World/Looks/{name}/{name}.outputs:out>
            token outputs:mdl:volume.connect = </World/Looks/{name}/{name}.outputs:out>
            def Shader "{name}"
            {{
                uniform token info:implementationSource = "sourceAsset"
                uniform asset info:mdl:sourceAsset = @OmniPBR.mdl@
                uniform token info:mdl:sourceAsset:subIdentifier = "OmniPBR"
                token outputs:out
            }}
        }}
"""


def _collect_shader_subidentifiers_by_material(stage: Usd.Stage) -> dict[str, str]:
    """Return a mapping from material prim name to its shader sub-identifier."""
    result: dict[str, str] = {}
    for prim in stage.Traverse():
        if prim.IsA(UsdShade.Material):
            mat = UsdShade.Material(prim)
            surface_source, _, _ = mat.ComputeSurfaceSource("mdl")
            if surface_source:
                sub_id: str | None = surface_source.GetPrim().GetAttribute("info:mdl:sourceAsset:subIdentifier").Get()
                if sub_id:
                    result[prim.GetName()] = sub_id
    return result
