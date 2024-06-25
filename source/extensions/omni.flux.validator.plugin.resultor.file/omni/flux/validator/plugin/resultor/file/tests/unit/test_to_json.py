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

import pathlib
import tempfile

from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, open_stage, wait_stage_loading
from pydantic import ValidationError


class TestToJson(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()
        await open_stage(get_test_data_path(__name__, "usd/cubes.usda"))
        self.temp_dir = tempfile.TemporaryDirectory()  # noqa PLR1732

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        self.temp_dir.cleanup()

    async def test_run_ok(self):
        json_path = pathlib.Path(self.temp_dir.name) / "result.json"
        core = _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {}},
                    }
                ],
                "resultor_plugins": [{"name": "ToJson", "data": {"json_path": str(json_path)}}],
            }
        )
        # run, it should be ok
        await core.deferred_run()

    async def test_run_failed_wrong_schema_json_path(self):
        schemas = [
            {  # empty json path
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    }
                ],
                "resultor_plugins": [{"name": "ToJson", "data": {"json_path": ""}}],
            },
        ]

        with self.assertRaises(ValidationError):
            for schema in schemas:
                _ManagerCore(schema)

    async def test_run_ok_file_written(self):
        json_path = pathlib.Path(self.temp_dir.name) / "result.json"
        core = _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {}},
                    }
                ],
                "resultor_plugins": [{"name": "ToJson", "data": {"json_path": str(json_path)}}],
            }
        )
        # run, it should be ok
        await core.deferred_run()

        sub_result_count = 0

        def sub_validation(_result, _message):
            nonlocal sub_result_count
            sub_result_count += 1
            self.assertTrue(_result)
            self.assertTrue("Ok" in _message)

        _sub = core.model.resultor_plugins[0].instance.subscribe_result(sub_validation)

        await core.deferred_run()

        self.assertTrue(sub_result_count == 1)

        # test that the file was created
        self.assertTrue(json_path.exists())
        _sub = None  # noqa
