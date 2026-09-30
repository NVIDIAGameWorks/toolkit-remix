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

import omni.kit.test
import omni.usd
from pxr import Gf, Sdf, Usd, UsdShade

from ... import (
    GltfToAperturePBRConverterBuilder,
    MaterialConverterCore,
    OmniPBRToAperturePBRConverterBuilder,
    USDPreviewSurfaceToAperturePBRConverterBuilder,
)
from ...utils import SupportedShaderInputs

__all__ = ["TestMaterialConverterCoreE2E"]


class TestMaterialConverterCoreE2E(omni.kit.test.AsyncTestCase):
    """Test converter-core workflows against a live USD context."""

    async def test_find_matching_supported_material_matches_omni_pbr_with_gltf_registered(self):
        """A legacy OmniPBR shader matches when the registry also holds a non-output shader input."""
        # Arrange
        stage = Usd.Stage.CreateInMemory("material_converter_matching.usda")
        shader = stage.DefinePrim("/Material/Shader", "Shader")
        builder = OmniPBRToAperturePBRConverterBuilder()
        for attribute in builder.build(shader, "AperturePBR_Opacity").attributes:
            if not attribute.fake_attribute:
                shader.CreateAttribute(attribute.input_attr_name, Sdf.ValueTypeNames.Float)

        # Act
        converter, shader_input = await MaterialConverterCore.find_matching_supported_material(shader)

        # Assert
        self.assertIs(converter, OmniPBRToAperturePBRConverterBuilder)
        self.assertEqual(shader_input, SupportedShaderInputs.OMNI_PBR)

    async def test_convert_gltf_should_preserve_color_alpha_and_texture_channels(self):
        """Convert glTF materials without loss of color, alpha, or packed texture channels."""
        context_name = "material_converter_gltf"
        context = omni.usd.create_context(context_name)
        self.addCleanup(omni.usd.destroy_context, context_name)
        try:
            for alpha_mode, cutoff, transmission, output_name, color_name in (
                (None, None, 0, "AperturePBR_Opacity", "diffuse_color_constant"),
                (0, 0.25, 0, "AperturePBR_Opacity", "diffuse_color_constant"),
                (1, None, 0, "AperturePBR_Opacity", "diffuse_color_constant"),
                (1, 0.25, 0, "AperturePBR_Opacity", "diffuse_color_constant"),
                (2, 0.25, 0, "AperturePBR_Opacity", "diffuse_color_constant"),
                (0, None, 0.5, "AperturePBR_Translucent", "transmittance_color"),
            ):
                with self.subTest(alpha_mode=alpha_mode, cutoff=cutoff, transmission=transmission):
                    # Arrange
                    await context.new_stage_async()
                    stage = context.get_stage()
                    material = UsdShade.Material.Define(stage, "/Material")
                    shader = UsdShade.Shader.Define(stage, "/Material/Shader")
                    shader.CreateIdAttr("gltf_material")
                    material.CreateSurfaceOutput().ConnectToSource(shader.CreateOutput("out", Sdf.ValueTypeNames.Token))
                    shader.CreateInput("base_color_factor", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(0.5, 1, 0.25, 0.75))
                    shader.CreateInput("base_alpha", Sdf.ValueTypeNames.Float).Set(0.75)
                    if alpha_mode is not None:
                        shader.CreateInput("alpha_mode", Sdf.ValueTypeNames.Int).Set(alpha_mode)
                    if cutoff is not None:
                        shader.CreateInput("alpha_cutoff", Sdf.ValueTypeNames.Float).Set(cutoff)
                    shader.CreateInput("transmission_factor", Sdf.ValueTypeNames.Float).Set(transmission)
                    texture = UsdShade.Shader.Define(stage, "/Texture")
                    texture.GetPrim().CreateAttribute(
                        "info:mdl:sourceAsset:subIdentifier", Sdf.ValueTypeNames.Token
                    ).Set("gltf_texture_lookup")
                    texture.CreateInput("texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("packed.png"))
                    shader.CreateInput("metallic_roughness_texture", Sdf.ValueTypeNames.Float3).ConnectToSource(
                        texture.CreateOutput("out", Sdf.ValueTypeNames.Float3)
                    )
                    builder = GltfToAperturePBRConverterBuilder()
                    converter = builder.build(material.GetPrim(), builder.select_output(shader.GetPrim()).value)

                    # Act
                    success, message, skipped = await MaterialConverterCore.convert(context_name, converter)

                    # Assert
                    self.assertTrue(success, message)
                    self.assertFalse(skipped)
                    output = omni.usd.get_shader_from_material(stage.GetPrimAtPath("/Material"), get_prim=True)
                    self.assertEqual(output_name, output.GetAttribute("info:mdl:sourceAsset:subIdentifier").Get())
                    color = output.GetAttribute(f"inputs:{color_name}")
                    self.assertEqual(Sdf.ValueTypeNames.Color3f, color.GetTypeName())
                    self.assertEqual(Gf.Vec3f(0.5, 1, 0.25), color.Get())
                    if output_name == "AperturePBR_Opacity":
                        self.assertEqual(0.75, output.GetAttribute("inputs:opacity_constant").Get())
                        self.assertIs(False, output.GetAttribute("inputs:use_legacy_alpha_state").Get())
                        self.assertEqual(alpha_mode == 2, output.GetAttribute("inputs:blend_enabled").Get())
                        self.assertEqual(
                            7 if alpha_mode == 1 else 0, output.GetAttribute("inputs:alpha_test_type").Get()
                        )
                        self.assertEqual(
                            (0.5 if cutoff is None else cutoff) if alpha_mode == 1 else 0.0,
                            output.GetAttribute("inputs:alpha_test_reference_value").Get(),
                        )
                        self.assertFalse(output.HasAttribute("inputs:enable_opacity"))
                        roughness = output.GetAttribute("inputs:reflectionroughness_texture")
                        metallic = output.GetAttribute("inputs:metallic_texture")
                        self.assertEqual(Sdf.AssetPath("packed.png"), roughness.Get())
                        self.assertEqual("G", roughness.GetCustomDataByKey("remix:sourceChannel"))
                        self.assertEqual(Sdf.AssetPath("packed.png"), metallic.Get())
                        self.assertEqual("B", metallic.GetCustomDataByKey("remix:sourceChannel"))
        finally:
            await context.close_stage_async()

    async def test_convert_preview_surface_non_rgb_normal_should_reject_texture(self):
        """Do not use a scalar texture output as a normal map."""
        context_name = "material_converter_scalar_normal"
        context = omni.usd.create_context(context_name)
        self.addCleanup(omni.usd.destroy_context, context_name)
        try:
            # Arrange
            await context.new_stage_async()
            stage = context.get_stage()
            material = UsdShade.Material.Define(stage, "/Material")
            shader = UsdShade.Shader.Define(stage, "/Material/Shader")
            shader.CreateIdAttr("UsdPreviewSurface")
            material.CreateSurfaceOutput().ConnectToSource(shader.CreateOutput("surface", Sdf.ValueTypeNames.Token))
            texture = UsdShade.Shader.Define(stage, "/Texture")
            texture.CreateIdAttr("UsdUVTexture")
            texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("normal.png"))
            texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
            shader.CreateInput("normal", Sdf.ValueTypeNames.Normal3f).ConnectToSource(
                texture.CreateOutput("r", Sdf.ValueTypeNames.Float)
            )
            converter = USDPreviewSurfaceToAperturePBRConverterBuilder().build(
                material.GetPrim(), "AperturePBR_Opacity"
            )

            # Act
            success, message, skipped = await MaterialConverterCore.convert(context_name, converter)

            # Assert
            self.assertTrue(success, message)
            self.assertFalse(skipped)
            output = omni.usd.get_shader_from_material(stage.GetPrimAtPath("/Material"), get_prim=True)
            self.assertEqual(Sdf.AssetPath(), output.GetAttribute("inputs:normalmap_texture").Get())
        finally:
            await context.close_stage_async()
