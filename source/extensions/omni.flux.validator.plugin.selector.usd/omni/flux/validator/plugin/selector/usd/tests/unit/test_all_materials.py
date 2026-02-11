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

import omni.usd
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, open_stage, wait_stage_loading


class TestAllMaterials(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()
        await open_stage(get_test_data_path(__name__, "usd/mesh.usda"))

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
                        "selector_plugins": [{"name": "AllMaterials", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {}},
                    }
                ],
            }
        )
        # run, it should be ok
        await core.deferred_run()

        sub_select_count = 0

        def selector_select_sub_validation(_result, _message, _data):
            nonlocal sub_select_count
            sub_select_count += 1
            self.assertTrue(_result)
            self.assertTrue(_message == "Ok")
            self.assertTrue([(prim.GetPath()) for prim in _data] == ["/Cube/OmniPBR"])

        _sub_selector_select = (
            core.model.check_plugins[0].selector_plugins[0].instance.subscribe_select(selector_select_sub_validation)
        )

        await core.deferred_run()

        self.assertTrue(sub_select_count == 1)

        # create an empty stage
        usd_context = omni.usd.get_context()
        await usd_context.new_stage_async()
        await wait_stage_loading(usd_context=usd_context)

        sub_select_count = 0

        def selector_select_sub_validation_empty(_result, _message, _data):
            nonlocal sub_select_count
            sub_select_count += 1
            self.assertTrue(_result)
            self.assertTrue(_message == "Ok")
            self.assertTrue(_data == [])

        _sub_selector_select = None
        _sub_selector_select = (
            core.model.check_plugins[0]
            .selector_plugins[0]
            .instance.subscribe_select(selector_select_sub_validation_empty)
        )

        await core.deferred_run()
        self.assertTrue(sub_select_count == 1)
