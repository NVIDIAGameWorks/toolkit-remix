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

from unittest.mock import patch

import omni.kit.test
from .... import (
    GltfToAperturePBRConverterBuilder,
    NoneToAperturePBRConverterBuilder,
    get_converter_builder,
)
from pxr import Gf, Sdf, Usd, UsdShade


__all__ = ["TestGltfToAperturePBRConverterBuilderUnit"]


class TestGltfToAperturePBRConverterBuilderUnit(omni.kit.test.AsyncTestCase):
    """Test material attribute conversion to AperturePBR."""

    async def test_select_output_should_follow_transmission(self):
        """Use alpha blending for coverage and translucency for transmission."""
        builder = GltfToAperturePBRConverterBuilder()
        cases = (
            (None, None, "AperturePBR_Opacity"),
            (0, None, "AperturePBR_Opacity"),
            (2, None, "AperturePBR_Opacity"),
            (0, 0.5, "AperturePBR_Translucent"),
        )
        for alpha_mode, transmission_factor, expected in cases:
            with self.subTest(alpha_mode=alpha_mode, transmission_factor=transmission_factor):
                stage = Usd.Stage.CreateInMemory()
                shader = UsdShade.Shader.Define(stage, "/Shader")
                if alpha_mode is not None:
                    shader.CreateInput("alpha_mode", Sdf.ValueTypeNames.Int).Set(alpha_mode)
                if transmission_factor is not None:
                    shader.CreateInput("transmission_factor", Sdf.ValueTypeNames.Float).Set(transmission_factor)

                self.assertEqual(expected, builder.select_output(shader.GetPrim()).value)

    async def test_convert_connection_should_resolve_supported_texture_lookups(self):
        """Resolve supported texture nodes and reject unknown nodes."""
        builder = GltfToAperturePBRConverterBuilder()
        for identifier in ("gltf_texture_lookup", "gltf_normal_texture_lookup", "unsupported_texture_lookup"):
            with self.subTest(identifier=identifier):
                stage = Usd.Stage.CreateInMemory()
                shader = UsdShade.Shader.Define(stage, "/Shader")
                texture = UsdShade.Shader.Define(stage, "/Texture")
                texture.GetPrim().CreateAttribute("info:mdl:sourceAsset:subIdentifier", Sdf.ValueTypeNames.Token).Set(
                    identifier
                )
                texture.CreateInput("texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("texture.png"))
                output = texture.CreateOutput("out", Sdf.ValueTypeNames.Float3)
                texture_input = shader.CreateInput("base_color_texture", Sdf.ValueTypeNames.Float3)
                texture_input.ConnectToSource(output)

                output_type, output_value = builder._convert_connection_to_texture(None, texture_input.GetAttr())

                expected = (
                    Sdf.AssetPath() if identifier == "unsupported_texture_lookup" else Sdf.AssetPath("texture.png")
                )
                self.assertEqual(Sdf.ValueTypeNames.Asset, output_type)
                self.assertEqual(expected, output_value)

    async def test_convert_connection_should_return_empty_asset_for_unconnected_input(self):
        """Return an empty asset when the texture input has no source."""
        stage = Usd.Stage.CreateInMemory()
        shader = UsdShade.Shader.Define(stage, "/Shader")
        texture_input = shader.CreateInput("base_color_texture", Sdf.ValueTypeNames.Float3)
        texture_input.Set(Gf.Vec3f(1, 1, 1))

        output_type, output_value = GltfToAperturePBRConverterBuilder()._convert_connection_to_texture(
            None, texture_input.GetAttr()
        )

        self.assertEqual(Sdf.ValueTypeNames.Asset, output_type)
        self.assertEqual(Sdf.AssetPath(), output_value)

    async def test_build_should_mark_textures_with_nonunit_factors(self):
        """Carry non-unit glTF factors on the texture inputs and omit unit factors."""
        stage = Usd.Stage.CreateInMemory()
        material = UsdShade.Material.Define(stage, "/Material")
        shader = UsdShade.Shader.Define(stage, "/Material/Shader")
        material.CreateSurfaceOutput().ConnectToSource(shader.CreateOutput("out", Sdf.ValueTypeNames.Token))
        shader.CreateInput("base_color_factor", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(0.5, 1, 0.25, 0.75))
        shader.CreateInput("emissive_factor", Sdf.ValueTypeNames.Float3).Set(Gf.Vec3f(1, 1, 1))
        shader.CreateInput("roughness_factor", Sdf.ValueTypeNames.Float).Set(0.25)
        shader.CreateInput("metallic_factor", Sdf.ValueTypeNames.Float).Set(1.0)
        builder = GltfToAperturePBRConverterBuilder()

        converter = builder.build(material.GetPrim(), "AperturePBR_Opacity")
        attributes = {attr.output_attr_name: attr for attr in converter.attributes}

        def factor(name):
            custom_data = attributes[name].output_custom_data or {}
            value = custom_data.get("remix:sourceFactor")
            return None if value is None else tuple(value)

        self.assertEqual((0.5, 1.0, 0.25, 0.75), factor("inputs:diffuse_texture"))
        self.assertEqual((0.25,), factor("inputs:reflectionroughness_texture"))
        roughness_custom_data = attributes["inputs:reflectionroughness_texture"].output_custom_data
        self.assertEqual("G", roughness_custom_data["remix:sourceChannel"])
        self.assertIsNone(factor("inputs:metallic_texture"))
        self.assertIsNone(factor("inputs:emissive_mask_texture"))
        self.assertIsNone(factor("inputs:normalmap_texture"))

    async def test_build_translucent_should_keep_emissive_factor_in_color_only(self):
        """Keep the emissive factor in emissive_color and off the emissive texture for translucent output."""
        stage = Usd.Stage.CreateInMemory()
        material = UsdShade.Material.Define(stage, "/Material")
        shader = UsdShade.Shader.Define(stage, "/Material/Shader")
        material.CreateSurfaceOutput().ConnectToSource(shader.CreateOutput("out", Sdf.ValueTypeNames.Token))
        shader.CreateInput("emissive_factor", Sdf.ValueTypeNames.Float3).Set(Gf.Vec3f(0.5, 0.25, 1))
        builder = GltfToAperturePBRConverterBuilder()

        for output, expected in (("AperturePBR_Translucent", None), ("AperturePBR_Opacity", (0.5, 0.25, 1.0))):
            with self.subTest(output=output):
                converter = builder.build(material.GetPrim(), output)
                attributes = {attr.output_attr_name: attr for attr in converter.attributes}
                custom_data = attributes["inputs:emissive_mask_texture"].output_custom_data or {}
                value = custom_data.get("remix:sourceFactor")
                self.assertEqual(expected, None if value is None else tuple(value))
        translucent = builder.build(material.GetPrim(), "AperturePBR_Translucent")
        emission_color = next(
            attr for attr in translucent.attributes if attr.output_attr_name == "inputs:emissive_color"
        )
        self.assertEqual("inputs:emissive_factor", emission_color.input_attr_name)

    async def test_build_opaque_should_select_packed_roughness_and_metallic_channels(self):
        """Select the correct channels from packed textures."""
        stage = Usd.Stage.CreateInMemory()
        builder = GltfToAperturePBRConverterBuilder()

        converter = builder.build(stage.DefinePrim("/Material"), "AperturePBR_Opacity")
        attributes = {attr.output_attr_name: attr for attr in converter.attributes}
        roughness = attributes["inputs:reflectionroughness_texture"]
        metallic = attributes["inputs:metallic_texture"]

        self.assertEqual("inputs:metallic_roughness_texture", roughness.input_attr_name)
        self.assertEqual({"remix:sourceChannel": "G"}, roughness.output_custom_data)
        self.assertEqual("inputs:metallic_roughness_texture", metallic.input_attr_name)
        self.assertEqual({"remix:sourceChannel": "B"}, metallic.output_custom_data)

    async def test_build_translucent_should_map_transmittance_texture(self):
        """Map the base color texture to transmittance."""
        stage = Usd.Stage.CreateInMemory()
        builder = GltfToAperturePBRConverterBuilder()

        converter = builder.build(stage.DefinePrim("/Material"), "AperturePBR_Translucent")
        transmittance = next(
            attr for attr in converter.attributes if attr.output_attr_name == "inputs:transmittance_texture"
        )

        self.assertEqual("inputs:base_color_texture", transmittance.input_attr_name)

    async def test_build_should_enable_emission_only_for_nonzero_emissive_factor(self):
        """Enable emission only for nonzero factors."""
        stage = Usd.Stage.CreateInMemory()
        builder = GltfToAperturePBRConverterBuilder()

        for output, color_input in (
            ("AperturePBR_Opacity", "inputs:emissive_color_constant"),
            ("AperturePBR_Translucent", "inputs:emissive_color"),
        ):
            with self.subTest(output=output):
                converter = builder.build(stage.DefinePrim("/Material"), output)
                enable_emission = next(
                    attr for attr in converter.attributes if attr.output_attr_name == "inputs:enable_emission"
                )

                for factor, expected in (
                    (Gf.Vec3f(0, 0, 0), False),
                    (Gf.Vec3f(0, 0.01, 0), True),
                    (Gf.Vec3f(1, 1, 1), True),
                ):
                    with self.subTest(factor=factor):
                        self.assertEqual(
                            (Sdf.ValueTypeNames.Bool, expected), enable_emission.translate_fn(factor, None)
                        )
                emission_color = next(attr for attr in converter.attributes if attr.output_attr_name == color_input)
                self.assertEqual("inputs:emissive_factor", emission_color.input_attr_name)

    async def test_registry_should_select_gltf_none_and_unknown_builders(self):
        """Select registered converters and reject unknown shaders."""
        self.assertIsInstance(get_converter_builder("gltf_material"), GltfToAperturePBRConverterBuilder)
        self.assertIsInstance(get_converter_builder(None), NoneToAperturePBRConverterBuilder)
        self.assertIsNone(get_converter_builder("unknown_material"))

    async def test_texture_transform_should_warn_once_only_for_nondefault_values(self):
        """Warn once for unsupported texture transforms."""
        stage = Usd.Stage.CreateInMemory()
        shader = UsdShade.Shader.Define(stage, "/Shader")
        texture = UsdShade.Shader.Define(stage, "/Texture")
        texture.GetPrim().CreateAttribute("info:mdl:sourceAsset:subIdentifier", Sdf.ValueTypeNames.Token).Set(
            "gltf_texture_lookup"
        )
        texture.CreateInput("texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("texture.png"))
        offset = texture.CreateInput("offset", Sdf.ValueTypeNames.Float2)
        offset.Set(Gf.Vec2f(0, 0))
        texture.CreateInput("scale", Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(1, 1))
        texture_input = shader.CreateInput("base_color_texture", Sdf.ValueTypeNames.Float3)
        texture_input.ConnectToSource(texture.CreateOutput("out", Sdf.ValueTypeNames.Float3))
        builder = GltfToAperturePBRConverterBuilder()

        with patch("omni.flux.utils.material_converter.impl.gltf_to_aperture_pbr.carb.log_warn") as log_warn:
            builder._convert_connection_to_texture(None, texture_input.GetAttr())
            log_warn.assert_not_called()
            offset.Set(Gf.Vec2f(0.5, 0))
            builder._convert_connection_to_texture(None, texture_input.GetAttr())
            builder._convert_connection_to_texture(None, texture_input.GetAttr())
            log_warn.assert_called_once()
