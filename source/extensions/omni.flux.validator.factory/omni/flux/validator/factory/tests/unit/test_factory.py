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

from typing import Any

import omni.usd
from omni.flux.validator.factory import SelectorBase as _SelectorBase
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from omni.flux.validator.factory import get_instance as _get_factory_instance
from omni.kit.test import AsyncTestCase

_FAKE_PLUGIN_NAME = "FakePlugin"


class FakeSelectorPlugin(_SelectorBase):
    name = _FAKE_PLUGIN_NAME
    tooltip = "This is a test plugin"

    @omni.usd.handle_exception
    async def _select(
        self, schema_data: Any, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        return True, "Test", [1, 2, 3]

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Any) -> Any:
        pass

    @omni.usd.handle_exception
    async def _on_crash(self, schema_data: Any, data: Any) -> None:
        pass


class TestValidatorFactory(AsyncTestCase):
    async def setUp(self):
        self.factory = _get_factory_instance()

    # After running each test
    async def tearDown(self):
        self.factory = None

    async def test_is_plugin_registered_is_registered_should_return_true(self):
        # Arrange
        self.factory._plugins[_FAKE_PLUGIN_NAME] = FakeSelectorPlugin

        # Act
        value = self.factory.is_plugin_registered(_FAKE_PLUGIN_NAME)

        # Assert
        self.assertTrue(value)

    async def test_is_plugin_registered_is_not_registered_should_raise_value_error(self):
        # Arrange
        pass

        # Act
        with self.assertRaises(ValueError) as cm:
            self.factory.is_plugin_registered(_FAKE_PLUGIN_NAME)

        # Assert
        self.assertEqual(str(cm.exception), f"Plugin {_FAKE_PLUGIN_NAME} is not registered/not found! Stopped.")
