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

from omni.flux.factory.base import FactoryBase, PluginBase
from omni.kit.test import AsyncTestCase

_PLUGIN_NAME_1 = "test_plugin"
_PLUGIN_NAME_2 = "another_test_plugin"


class TestPlugin1(PluginBase):
    name = _PLUGIN_NAME_1


class TestPlugin2(PluginBase):
    name = _PLUGIN_NAME_2


class TestValidatorFactory(AsyncTestCase):
    async def setUp(self):
        self.factory = FactoryBase[TestPlugin1]()

    # After running each test
    async def tearDown(self):
        self.factory = None

    async def test_is_plugin_registered_is_registered_should_return_true(self):
        # Arrange
        self.factory._plugins[_PLUGIN_NAME_1] = TestPlugin1  # noqa PLW0212

        # Act
        value = self.factory.is_plugin_registered(_PLUGIN_NAME_1)

        # Assert
        self.assertTrue(value)

    async def test_is_plugin_registered_is_not_registered_should_return_false(self):
        # Arrange
        pass

        # Act
        value = self.factory.is_plugin_registered(_PLUGIN_NAME_1)

        # Assert
        self.assertFalse(value)

    async def test_get_plugins_from_name_is_registered_should_return_plugin_type(self):
        # Arrange
        self.factory._plugins[_PLUGIN_NAME_1] = TestPlugin1  # noqa PLW0212

        # Act
        value = self.factory.get_plugin_from_name(_PLUGIN_NAME_1)

        # Assert
        self.assertEqual(value, TestPlugin1)

    async def test_get_plugins_from_name_is_not_registered_should_return_none(self):
        # Arrange
        pass

        # Act
        value = self.factory.get_plugin_from_name(_PLUGIN_NAME_1)

        # Assert
        self.assertIsNone(value)

    async def test_get_all_plugins_should_return_all_plugins(self):
        # Arrange
        expected_plugins = {
            _PLUGIN_NAME_1: TestPlugin1,
            _PLUGIN_NAME_2: TestPlugin2,
        }
        self.factory._plugins = expected_plugins  # noqa PLW0212

        # Act
        value = self.factory.get_all_plugins()

        # Assert
        self.assertDictEqual(value, expected_plugins)

    async def test_register_plugins_should_add_plugins_to_plugins(self):
        # Arrange
        self.factory._plugins = {_PLUGIN_NAME_2: TestPlugin2}  # noqa PLW0212

        # Act
        self.factory.register_plugins([TestPlugin1])

        # Assert
        self.assertDictEqual(
            self.factory._plugins,
            {_PLUGIN_NAME_1: TestPlugin1, _PLUGIN_NAME_2: TestPlugin2},  # noqa PLW0212
        )

    async def test_unregister_plugins_should_remove_plugins_from_plugins(self):
        # Arrange
        expected_plugins = {
            _PLUGIN_NAME_1: TestPlugin1,
            _PLUGIN_NAME_2: TestPlugin2,
        }
        self.factory._plugins = expected_plugins  # noqa PLW0212

        # Act
        self.factory.unregister_plugins([TestPlugin1])

        # Assert
        self.assertDictEqual(self.factory._plugins, {_PLUGIN_NAME_2: TestPlugin2})  # noqa PLW0212
