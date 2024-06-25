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


class TestAttributeBase(omni.kit.test.AsyncTestCase):
    async def test_translate_fn_should_have_default_behavior_should_return_same_value(self):
        # Arrange
        attr = AttributeBase.construct()
        val_mock = Mock()
        attr_mock = Mock()

        # Act
        val = attr.translate_fn(val_mock, attr_mock)

        # Assert
        self.assertEqual(val_mock, val)

    # TODO Bug OM-90672: `load_mdl_parameters_for_prim_async` will not work with non-default contexts
    # Remove this test when the bug is fixed
    async def test_translate_alt_fn_should_have_default_behavior_should_return_same_values(self):
        # Arrange
        attr = AttributeBase.construct()
        type_mock = Mock()
        val_mock = Mock()
        attr_mock = Mock()

        # Act
        translated_type, translated_val = attr.translate_alt_fn(type_mock, val_mock, attr_mock)

        # Assert
        self.assertEqual(type_mock, translated_type)
        self.assertEqual(val_mock, translated_val)
