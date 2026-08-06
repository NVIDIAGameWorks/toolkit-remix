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

import shutil
import tempfile
from pathlib import Path

import omni.kit.test
from omni.flux.utils.material_converter import MaterialConverterCore
from omni.flux.utils.material_converter.impl.omni_glass_to_aperture_pbr import (
    OmniGlassToAperturePBRConverterBuilder,
)
from omni.flux.utils.material_converter.utils import SupportedShaderOutputs
from omni.kit.test_suite.helpers import get_test_data_path
from pxr import Sdf, UsdShade

_MATERIAL_PATH = "/World/Looks/M_Fixture_Elevator_Interior_02"


class TestOmniGlassToAperturePBRConverterBuilderE2E(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.context = omni.usd.get_context()

    async def tearDown(self):
        if self.context.get_stage():
            await self.context.close_stage_async()

        self.temp_dir.cleanup()

        self.temp_dir = None
        self.context = None

    async def test_convert_explicit_normal_encoding_should_override_legacy_flip_tangent_v(self):
        # Arrange
        omni_glass_temp_path = Path(self.temp_dir.name) / "omni_glass.usda"
        shutil.copy(get_test_data_path(__name__, "usd/omni_pbr.usda"), omni_glass_temp_path)
        await self.context.open_stage_async(str(omni_glass_temp_path))
        stage = self.context.get_stage()
        material_prim = stage.GetPrimAtPath(_MATERIAL_PATH)
        input_shader_prim = omni.usd.get_shader_from_material(material_prim, get_prim=True)
        input_shader = UsdShade.Shader(input_shader_prim)
        normal_map_path = Sdf.AssetPath("./textures/normal.png")
        input_shader.CreateInput("normal_map_texture", Sdf.ValueTypeNames.Asset).Set(normal_map_path)
        input_shader.CreateInput("encoding", Sdf.ValueTypeNames.Int).Set(0)
        input_shader.CreateInput("flip_tangent_v", Sdf.ValueTypeNames.Bool).Set(True)
        converter = OmniGlassToAperturePBRConverterBuilder().build(
            material_prim,
            SupportedShaderOutputs.APERTURE_PBR_OPACITY.value,
        )

        # Act
        success, _message, was_skipped = await MaterialConverterCore.convert("", converter)

        # Assert
        output_material_prim = stage.GetPrimAtPath(_MATERIAL_PATH)
        output_shader_prim = omni.usd.get_shader_from_material(output_material_prim, get_prim=True)
        output_shader = UsdShade.Shader(output_shader_prim)
        self.assertTrue(success)
        self.assertFalse(was_skipped)
        self.assertEqual(normal_map_path, output_shader.GetInput("normalmap_texture").Get())
        self.assertEqual(0, output_shader.GetInput("encoding").Get())
