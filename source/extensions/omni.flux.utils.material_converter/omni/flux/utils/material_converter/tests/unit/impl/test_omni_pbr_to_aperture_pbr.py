"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from unittest.mock import Mock

import omni.kit.test
from omni.flux.utils.material_converter.impl.omni_pbr_to_aperture_pbr import OmniPBRToAperturePBRConverterBuilder
from pxr import Sdf, Usd


class TestOmniPBRToAperturePBRConverterBuilderUnit(omni.kit.test.AsyncTestCase):
    async def test_convert_normal_encoding_value_false_should_return_tangent_space_ogl(self):
        # Arrange
        converter_builder = OmniPBRToAperturePBRConverterBuilder()

        # Act
        output_type, output_value = converter_builder._convert_normal_encoding(False, Mock())

        # Assert
        self.assertEqual(Sdf.ValueTypeNames.Int, output_type)
        self.assertEqual(1, output_value)  # TANGENT_SPACE_OGL = 1

    async def test_convert_normal_encoding_value_true_should_return_tangent_space_dx(self):
        # Arrange
        converter_builder = OmniPBRToAperturePBRConverterBuilder()

        # Act
        output_type, output_value = converter_builder._convert_normal_encoding(True, Mock())

        # Assert
        self.assertEqual(Sdf.ValueTypeNames.Int, output_type)
        self.assertEqual(2, output_value)  # TANGENT_SPACE_DX = 2

    async def test_build_normal_encoding_should_use_typed_default(self):
        # Arrange
        converter_builder = OmniPBRToAperturePBRConverterBuilder()
        stage = Usd.Stage.CreateInMemory()
        input_material_prim = stage.DefinePrim("/Material")

        # Act
        converter = converter_builder.build(input_material_prim, "AperturePBR_Opacity")
        encoding_attr = next(attr for attr in converter.attributes if attr.input_attr_name == "inputs:flip_tangent_v")

        # Assert
        self.assertEqual(Sdf.ValueTypeNames.Int, encoding_attr.output_attr_type)
        self.assertEqual(2, encoding_attr.output_default_value)  # TANGENT_SPACE_DX = 2
