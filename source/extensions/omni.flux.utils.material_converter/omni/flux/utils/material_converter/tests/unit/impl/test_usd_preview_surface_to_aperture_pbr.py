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
from .... import USDPreviewSurfaceToAperturePBRConverterBuilder
from pxr import Sdf, Usd, UsdShade


__all__ = ["TestUSDPreviewSurfaceToAperturePBRConverterBuilderUnit"]


class TestUSDPreviewSurfaceToAperturePBRConverterBuilderUnit(omni.kit.test.AsyncTestCase):
    """Test material attribute conversion to AperturePBR."""

    async def test_build_normal_should_resolve_connected_rgb_not_first_output(self):
        """Resolve the connected normal texture output."""
        stage = Usd.Stage.CreateInMemory()
        material = UsdShade.Material.Define(stage, "/Material")
        shader = UsdShade.Shader.Define(stage, "/Material/Shader")
        shader.CreateIdAttr("UsdPreviewSurface")
        texture = UsdShade.Shader.Define(stage, "/Material/Texture")
        texture.CreateIdAttr("UsdUVTexture")
        texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("normal.png"))
        texture.CreateOutput("r", Sdf.ValueTypeNames.Float)
        rgb = texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        normal = shader.CreateInput("normal", Sdf.ValueTypeNames.Normal3f)
        normal.ConnectToSource(rgb)
        builder = USDPreviewSurfaceToAperturePBRConverterBuilder()

        converter = builder.build(material.GetPrim(), "AperturePBR_Opacity")
        mapping = next(attr for attr in converter.attributes if attr.output_attr_name == "inputs:normalmap_texture")
        output_type, output_value = mapping.translate_fn(
            normal.Get(), shader.GetPrim().GetAttribute(mapping.input_attr_name)
        )

        self.assertEqual("inputs:normal", mapping.input_attr_name)
        self.assertEqual(Sdf.ValueTypeNames.Asset, output_type)
        self.assertEqual(Sdf.AssetPath("normal.png"), output_value)

    async def test_build_normal_encoding_should_use_typed_fake_default(self):
        """Use OpenGL normal encoding without a source attribute."""
        stage = Usd.Stage.CreateInMemory()
        builder = USDPreviewSurfaceToAperturePBRConverterBuilder()

        converter = builder.build(stage.DefinePrim("/Material"), "AperturePBR_Opacity")
        encoding = next(attr for attr in converter.attributes if attr.output_attr_name == "inputs:encoding")

        self.assertTrue(encoding.fake_attribute)
        self.assertEqual(Sdf.ValueTypeNames.Int, encoding.output_attr_type)
        self.assertEqual(1, encoding.output_default_value)
