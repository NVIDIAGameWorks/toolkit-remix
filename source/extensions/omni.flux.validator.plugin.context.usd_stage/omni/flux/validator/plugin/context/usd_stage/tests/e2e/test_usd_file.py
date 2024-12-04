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

import omni.client
import omni.usd
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, wait_stage_loading


class TestUsdFile(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    async def test_run_file_dont_exist(self):
        core = _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {
                    "name": "USDFile",
                    "data": {"file": "wrong_file_path/hello/ahah.usda", "context_name": ""},
                },
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {}},
                    }
                ],
            }
        )
        sub_check_count = 0
        sub_set_count = 0

        def check_check_sub_validation(_result, _message):
            nonlocal sub_check_count
            sub_check_count += 1
            self.assertFalse(_result)
            self.assertEqual(
                f"Can't read the file {omni.client.normalize_url('wrong_file_path/hello/ahah.usda')}", _message
            )

        def check_set_sub_validation(_result, _message, _data):
            nonlocal sub_set_count
            sub_set_count += 1

        _sub_check_check = core.model.context_plugin.instance.subscribe_check(check_check_sub_validation)  # noqa
        _sub_check_set = core.model.context_plugin.instance.subscribe_set(check_set_sub_validation)  # noqa

        with self.assertRaises(ValueError):
            # will crash because the usd file doesn't exist
            await core.deferred_run()

        self.assertEqual(sub_check_count, 1)
        self.assertEqual(sub_set_count, 0)

    async def test_run_file_ok(self):
        core = _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {
                    "name": "USDFile",
                    "data": {"file": get_test_data_path(__name__, "usd/cubes.usda"), "context_name": ""},
                },
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {}},
                    }
                ],
            }
        )
        # run, it should be ok
        await core.deferred_run()

        sub_check_count = 0
        sub_set_count = 0

        def check_check_sub_validation(_result, _message):
            nonlocal sub_check_count
            sub_check_count += 1
            self.assertTrue(_result)
            self.assertTrue(
                _message
                == f"File {omni.client.normalize_url(get_test_data_path(__name__, 'usd/cubes.usda'))} ok to read"
            )

        def check_set_sub_validation(_result, _message, _data):
            nonlocal sub_set_count
            sub_set_count += 1
            self.assertTrue(_result)
            self.assertTrue(_message == omni.client.normalize_url(get_test_data_path(__name__, "usd/cubes.usda")))
            self.assertTrue(_data == omni.usd.get_context().get_stage())

        _sub_check_check = core.model.context_plugin.instance.subscribe_check(check_check_sub_validation)  # noqa
        _sub_check_set = core.model.context_plugin.instance.subscribe_set(check_set_sub_validation)  # noqa

        await core.deferred_run()

        self.assertTrue(sub_check_count == 1)
        self.assertTrue(sub_set_count == 1)
