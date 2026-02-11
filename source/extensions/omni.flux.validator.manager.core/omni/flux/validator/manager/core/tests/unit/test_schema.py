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

from __future__ import annotations

from omni.flux.validator.manager.core import ValidationSchema as _ValidationSchema
from omni.kit.test import AsyncTestCase
from pydantic import ValidationError


def _good_schema():
    return {
        "name": "Test",
        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
        "check_plugins": [
            {
                "name": "PrintPrims",
                "enabled": False,
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "selector_plugins": [{"name": "AllPrims", "data": {}}],
                "data": {},
                "pause_if_fix_failed": False,
            }
        ],
        "resultor_plugins": [{"name": "FakeResultor", "data": {}}, {"name": "FakeResultor", "data": {}}],
    }


class TestUpdateMethod(AsyncTestCase):
    async def setUp(self):
        self.mymodel_instance = _ValidationSchema(**_good_schema())

    async def test_valid_update(self):
        update_data = {
            "name": "Test2",  # new name for the schema instance
            "context_plugin": {"name": "CurrentStage", "data": {"context_name": "hello"}},
            "check_plugins": [
                {
                    "name": "PrintPrims",
                    "enabled": True,
                    "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    "selector_plugins": [{"name": "AllPrims", "data": {}}],
                    "data": {},
                    "pause_if_fix_failed": True,
                },
                {
                    "name": "PrintPrims",
                    "enabled": False,
                    "context_plugin": {"name": "CurrentStage", "data": {"context_name": "dam"}},
                    "selector_plugins": [{"name": "AllPrims", "data": {}}],
                    "data": {},
                    "pause_if_fix_failed": True,
                },
            ],
        }

        updated_dict = _ValidationSchema(**update_data)
        self.mymodel_instance.update(updated_dict.model_dump(serialize_as_any=True))

        # Check if the attributes have been updated correctly
        self.assertEqual(self.mymodel_instance.name, "Test2")
        self.assertEqual(self.mymodel_instance.context_plugin.data.context_name, "hello")
        # we only update value of existing plugins. We don't append more plugins
        self.assertEqual(len(self.mymodel_instance.check_plugins), 1)
        self.assertTrue(self.mymodel_instance.check_plugins[0].enabled)
        self.assertTrue(self.mymodel_instance.check_plugins[0].pause_if_fix_failed)
        self.assertIsNone(self.mymodel_instance.resultor_plugins)

    async def test_invalid_update(self):
        update_data = {"unknown_field": 123}  # invalid data

        with self.assertRaises(ValidationError):
            self.mymodel_instance.update(update_data)
