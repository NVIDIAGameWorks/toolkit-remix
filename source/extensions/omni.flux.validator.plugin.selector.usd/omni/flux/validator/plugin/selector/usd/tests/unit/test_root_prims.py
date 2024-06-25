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

import omni.usd
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import get_test_data_path, open_stage, wait_stage_loading


class TestRootPrims(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await open_stage(get_test_data_path(__name__, "usd/root_prims.usda"))

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def test_run(self):
        core = _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "RootPrims", "data": {}}],
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
            self.assertEqual(_message, "Ok")
            self.assertListEqual([str(prim.GetPath()) for prim in _data], ["/Xform_01", "/Xform"])

        _sub_selector_select = (
            core.model.check_plugins[0].selector_plugins[0].instance.subscribe_select(selector_select_sub_validation)
        )

        await core.deferred_run()

        self.assertTrue(sub_select_count == 1)

        # create an empty stage
        usd_context = omni.usd.get_context()
        await usd_context.new_stage_async()
        await wait_stage_loading(usd_context)

        sub_select_count = 0

        def selector_select_sub_validation_empty(_result, _message, _data):
            nonlocal sub_select_count
            sub_select_count += 1
            self.assertTrue(_result)
            self.assertEqual(_message, "Ok")
            self.assertListEqual(_data, [])

        _sub_selector_select = None
        _sub_selector_select = (  # noqa
            core.model.check_plugins[0]
            .selector_plugins[0]
            .instance.subscribe_select(selector_select_sub_validation_empty)
        )

        await core.deferred_run()
        self.assertTrue(sub_select_count == 1)
