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

from typing import Any, Tuple

import omni.usd
from omni.flux.validator.factory import SelectorBase as _SelectorBase
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from omni.flux.validator.factory import get_instance as _get_factory_instance
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, wait_stage_loading


class FakeSelectorPlugin(_SelectorBase):

    name = "FakePlugin"
    tooltip = "This is a test plugin"

    @omni.usd.handle_exception
    async def _select(
        self, schema_data: Any, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to select the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the previous selector plugin

        Returns: True if ok + message + the selected data
        """
        return True, "Test", [1, 2, 3]

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Any) -> Any:
        """
        Build the UI for the plugin
        """
        pass


class TestValidatorFactory(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    async def test_factory(self):
        factory_instance = _get_factory_instance()
        # empty
        self.assertFalse(factory_instance.get_all_plugins())
        with self.assertRaises(ValueError):
            self.assertFalse(factory_instance.is_plugin_registered("FakePlugin"))
        self.assertIsNone(factory_instance.get_plugins_from_name("FakePlugin"))

        # register
        factory_instance.register_plugins([FakeSelectorPlugin])
        self.assertTrue(factory_instance.get_all_plugins() == {"FakePlugin": FakeSelectorPlugin})
        self.assertTrue(factory_instance.is_plugin_registered("FakePlugin"))
        self.assertTrue(factory_instance.get_plugins_from_name("FakePlugin") == FakeSelectorPlugin)

        # unregister
        factory_instance.unregister_plugins([FakeSelectorPlugin])
        self.assertFalse(factory_instance.get_all_plugins())
        with self.assertRaises(ValueError):
            self.assertFalse(factory_instance.is_plugin_registered("FakePlugin"))
        self.assertIsNone(factory_instance.get_plugins_from_name("FakePlugin"))
