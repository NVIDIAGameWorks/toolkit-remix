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

from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.utils.material_converter.base.converter_base import ConverterBase
from omni.flux.utils.material_converter.utils import MaterialConverterUtils


class TestConverterBase(omni.kit.test.AsyncTestCase):
    async def test_input_material_prim_valid_invalid_prim_should_raise_value_error(self):
        # Arrange
        converter = ConverterBase.construct()

        path_mock = Mock()
        prim_mock = Mock()
        prim_mock.IsValid.return_value = False
        prim_mock.GetPath.return_value = path_mock

        # Act
        with self.assertRaises(ValueError) as cm:
            converter.input_material_prim_valid(prim_mock)

        # Assert
        self.assertEqual(f"Prim '{path_mock}' is invalid", str(cm.exception))

    async def test_input_material_prim_valid_valid_prim_should_return_value(self):
        # Arrange
        converter = ConverterBase.construct()

        prim_mock = Mock()
        prim_mock.IsValid.return_value = True

        # Act
        val = converter.input_material_prim_valid(prim_mock)

        # Assert
        self.assertEqual(prim_mock, val)

    async def test_output_mdl_valid_not_in_library_should_raise_value_error(self):
        # Arrange
        converter = ConverterBase.construct()

        subidentifier_mock = Mock()

        invalid_path_mock = Mock()
        invalid_path_mock.stem = "invalid_stem"
        library_urls_mock = [invalid_path_mock, invalid_path_mock, invalid_path_mock, invalid_path_mock]

        with patch.object(MaterialConverterUtils, "get_material_library_shader_urls") as get_shaders_urls_mock:
            get_shaders_urls_mock.return_value = library_urls_mock

            # Act
            with self.assertRaises(ValueError) as cm:
                converter.output_mdl_valid(subidentifier_mock)

        # Assert
        self.assertEqual(
            f"The subidentifier ({subidentifier_mock}) does not exist in the material library. "
            f"If using non-default shaders, add your shader path to the following setting "
            f"'{MaterialConverterUtils.MATERIAL_LIBRARY_SETTING_PATH}'. Currently available shaders are: "
            f"{', '.join([u.stem for u in library_urls_mock])}",
            str(cm.exception),
        )

    async def test_output_mdl_valid_in_library_should_return_value(self):
        # Arrange
        converter = ConverterBase.construct()

        subidentifier_mock = Mock()
        shader_mock = Mock()
        shader_mock.stem = subidentifier_mock

        with patch.object(MaterialConverterUtils, "get_material_library_shader_urls") as get_shaders_urls_mock:
            get_shaders_urls_mock.return_value = [Mock(), Mock(), shader_mock, Mock(), Mock()]

            # Act
            val = converter.output_mdl_valid(subidentifier_mock)

        # Assert
        self.assertEqual(subidentifier_mock, val)
