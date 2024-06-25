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
from pxr import Sdf


class TestOmniPBRToAperturePBRConverterBuilderUnit(omni.kit.test.AsyncTestCase):
    async def test_convert_normal_encoding_value_false_should_return_tangent_space_ogl(self):
        # Arrange
        converter_builder = OmniPBRToAperturePBRConverterBuilder()

        # Act
        val = converter_builder._convert_normal_encoding(False, Mock())  # noqa PLW0212

        # Assert
        self.assertEqual(1, val)  # TANGENT_SPACE_OGL = 2

    async def test_convert_normal_encoding_value_true_should_return_tangent_space_dx(self):
        # Arrange
        converter_builder = OmniPBRToAperturePBRConverterBuilder()

        # Act
        val = converter_builder._convert_normal_encoding(True, Mock())  # noqa PLW0212

        # Assert
        self.assertEqual(2, val)  # TANGENT_SPACE_DX = 2

    async def test_convert_normal_encoding_alt_value_false_should_return_int_type_and_tangent_space_ogl(self):
        # Arrange
        converter_builder = OmniPBRToAperturePBRConverterBuilder()

        # Act
        converted_type, converted_val = converter_builder._convert_normal_encoding_alt(  # noqa PLW0212
            Mock(), False, Mock()
        )  # noqa PLW0212

        # Assert
        self.assertEqual(Sdf.ValueTypeNames.Int, converted_type)
        self.assertEqual(1, converted_val)  # TANGENT_SPACE_OGL = 2

    async def test_convert_normal_encoding_alt_value_true_should_return_int_type_and_tangent_space_dx(self):
        # Arrange
        converter_builder = OmniPBRToAperturePBRConverterBuilder()

        # Act
        converted_type, converted_val = converter_builder._convert_normal_encoding_alt(  # noqa PLW0212
            Mock(), True, Mock()
        )  # noqa PLW0212

        # Assert
        self.assertEqual(Sdf.ValueTypeNames.Int, converted_type)
        self.assertEqual(2, converted_val)  # TANGENT_SPACE_DX = 2
