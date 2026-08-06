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
from omni.flux.utils.material_converter.base.attribute_base import AttributeBase
from pxr import Sdf


class TestAttributeBase(omni.kit.test.AsyncTestCase):
    async def test_translate_fn_with_default_behavior_should_return_input_type_and_value(self):
        # Arrange
        attr = AttributeBase(input_attr_name="input", output_attr_name="output")
        type_mock = Mock()
        val_mock = Mock()
        attr_mock = Mock()
        attr_mock.GetTypeName.return_value = type_mock

        # Act
        translated_type, translated_val = attr.translate_fn(val_mock, attr_mock)

        # Assert
        self.assertEqual(type_mock, translated_type)
        self.assertEqual(val_mock, translated_val)

    async def test_output_default_type_and_value_should_store_both(self):
        # Arrange
        type_mock = Sdf.ValueTypeNames.Int
        val_mock = Mock()

        # Act
        attr = AttributeBase(
            input_attr_name="input",
            output_attr_name="output",
            output_attr_type=type_mock,
            output_default_value=val_mock,
        )

        # Assert
        self.assertEqual(type_mock, attr.output_attr_type)
        self.assertEqual(val_mock, attr.output_default_value)
