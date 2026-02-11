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

import omni.client
import omni.usd
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, open_stage, wait_stage_loading


class TestCurrentStage(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()
        await open_stage(get_test_data_path(__name__, "usd/cubes.usda"))

    # After running each test
    async def tearDown(self):
        pass

    async def test_run(self):
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
            self.assertTrue(_message == omni.client.normalize_url(get_test_data_path(__name__, "usd/cubes.usda")))

        def check_set_sub_validation(_result, _message, _data):
            nonlocal sub_set_count
            sub_set_count += 1
            self.assertTrue(_result)
            self.assertTrue(_message == omni.client.normalize_url(get_test_data_path(__name__, "usd/cubes.usda")))
            self.assertTrue(_data == omni.usd.get_context().get_stage())

        _sub_check_check = core.model.context_plugin.instance.subscribe_check(check_check_sub_validation)
        _sub_check_set = core.model.context_plugin.instance.subscribe_set(check_set_sub_validation)

        await core.deferred_run()

        self.assertTrue(sub_check_count == 1)
        self.assertTrue(sub_set_count == 1)

        # create an empty stage
        usd_context = omni.usd.get_context()
        await usd_context.new_stage_async()
        await wait_stage_loading(usd_context=usd_context)

        sub_check_count = 0
        sub_set_count = 0

        def check_check_sub_validation_empty(_result, _message):
            nonlocal sub_check_count
            sub_check_count += 1
            self.assertTrue(_result)
            self.assertTrue(_message.startswith("anon:") and _message.endswith(".usd"))

        def check_set_sub_validation_empty(_result, _message, _data):
            nonlocal sub_set_count
            sub_set_count += 1
            self.assertTrue(_result)
            self.assertTrue(_message.startswith("anon:") and _message.endswith(".usd"))
            self.assertTrue(_data == usd_context.get_stage() and _data.GetRootLayer().anonymous)

        _sub_check_check = core.model.context_plugin.instance.subscribe_check(check_check_sub_validation_empty)
        _sub_check_set = core.model.context_plugin.instance.subscribe_set(check_set_sub_validation_empty)

        await core.deferred_run()
        self.assertTrue(sub_check_count == 1)
        self.assertTrue(sub_set_count == 1)
