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
from pxr import Sdf, Usd, UsdShade

from lightspeed.trex.asset_pipeline.core import RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.steps import ConvertMaterialsStep


_OPACITY_MATERIAL = "usd/project_example/materials/AperturePBR_Opacity.usda"
_RESOURCE_CONTEXT = "asset_pipeline_resource_project"


class TestConvertMaterialsE2E(omni.kit.test.AsyncTestCase):
    """Test material conversion against authored USD resources."""

    async def test_material_names_select_legacy_shader_outputs(self):
        """Preserve the legacy name rule for supported model shaders."""
        for identifier in (None, "OmniPBR", "OmniPBR_Opacity", "OmniGlass", "UsdPreviewSurface"):
            with self.subTest(identifier=identifier), tempfile.TemporaryDirectory() as temp_dir:
                model_path = _write_model_stage(temp_dir, ["M_Glass", "M_Wall"], identifier)
                item = RemixAssetItem.from_model(model_path)

                async with RemixAssetPipelineContext(items=[item]) as context:
                    await ConvertMaterialsStep().run(context)

                    stage = await context.open_stage(model_path)
                    self.assertEqual(
                        _collect_shader_subidentifiers_by_material(stage),
                        {"M_Glass": "AperturePBR_Translucent", "M_Wall": "AperturePBR_Opacity"},
                    )

    async def test_material_without_shader_receives_a_default_aperture_pbr_shader(self):
        """A material whose reference no longer resolves has no shader; conversion gives it AperturePBR_Opacity.

        A captured Remix mesh copied out of its project hits this: its material references a sibling
        ``../materials/mat_*.usda`` file that does not exist next to the copy. The legacy ``MaterialShaders``
        plugin converted such a material through the None converter, so the mesh still renders with a material.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = _write_model_stage(temp_dir, ["BodyPaint"])
            with open(model_path, "a", encoding="utf-8") as model_file:
                model_file.write(_DANGLING_MATERIAL)
            item = RemixAssetItem.from_model(model_path)

            async with RemixAssetPipelineContext(items=[item]) as context:
                await ConvertMaterialsStep().run(context)

                stage = await context.open_stage(model_path)
                subidentifiers = _collect_shader_subidentifiers_by_material(stage)
                self.assertEqual(
                    subidentifiers, {"BodyPaint": "AperturePBR_Opacity", "mat_missing": "AperturePBR_Opacity"}
                )

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


def _write_model_stage(
    temp_dir: str, material_names: list[str], shader_identifier: str | None = "OmniPBR"
) -> pathlib.Path:
    """Write a USD stage with the specified material shader."""
    model_path = pathlib.Path(temp_dir) / "model.usda"
    stage = Usd.Stage.CreateNew(str(model_path))
    stage.SetDefaultPrim(stage.DefinePrim("/World", "Xform"))
    stage.SetMetadata("metersPerUnit", 1.0)
    stage.SetMetadata("upAxis", "Y")
    stage.DefinePrim("/World/Looks", "Scope")
    for name in material_names:
        material = UsdShade.Material.Define(stage, f"/World/Looks/{name}")
        if shader_identifier is None:
            continue
        shader = UsdShade.Shader.Define(stage, f"/World/Looks/{name}/{name}")
        if shader_identifier == "UsdPreviewSurface":
            shader.CreateIdAttr(shader_identifier)
            material.CreateSurfaceOutput().ConnectToSource(shader.CreateOutput("surface", Sdf.ValueTypeNames.Token))
        else:
            shader.SetSourceAsset(Sdf.AssetPath(f"{shader_identifier}.mdl"), "mdl")
            shader.SetSourceAssetSubIdentifier(shader_identifier, "mdl")
            material.CreateSurfaceOutput("mdl").ConnectToSource(shader.CreateOutput("out", Sdf.ValueTypeNames.Token))
    stage.GetRootLayer().Save()
    return model_path


# A material that references a sibling file that does not exist, like a captured mesh copied out of its project.
_DANGLING_MATERIAL = """
def Scope "Looks"
{
    def Material "mat_missing" (
        prepend references = @../materials/mat_missing.usda@</Looks/mat_missing>
    )
    {
    }
}
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
