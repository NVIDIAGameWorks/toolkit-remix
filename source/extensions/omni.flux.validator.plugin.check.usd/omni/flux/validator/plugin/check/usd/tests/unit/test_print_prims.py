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

import asyncio
import sys
from unittest.mock import patch

from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.flux.validator.plugin.check.usd.example.print_prims import PrintPrims as _PrintPrims
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, open_stage, wait_stage_loading


class TestPrintPrims(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()
        await open_stage(get_test_data_path(__name__, "usd/cubes.usda"))

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    async def test_run_no_fix(self):
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
        sub_fix_count = 0

        def check_check_sub_validation(_result, _message, _data):
            nonlocal sub_check_count
            sub_check_count += 1
            self.assertTrue(_result)
            self.assertTrue("Check" in _message)
            self.assertTrue([(prim.GetPath()) for prim in _data] == ["/Xform", "/Xform/Cube", "/Xform/Cube2"])

        def check_fix_sub_validation(_result, _message, _data):
            nonlocal sub_fix_count
            sub_fix_count += 1

        _sub_check_check = core.model.check_plugins[0].instance.subscribe_check(check_check_sub_validation)  # noqa
        _sub_check_fix = core.model.check_plugins[0].instance.subscribe_fix(check_fix_sub_validation)  # noqa

        await core.deferred_run()

        self.assertTrue(sub_check_count == 1)
        self.assertTrue(sub_fix_count == 0)  # 0 because the check is good, so we dont run the fix

    async def test_run_fix(self):
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
        sub_fix_count = 0

        def check_check_sub_validation(_result, _message, _data):
            nonlocal sub_check_count
            sub_check_count += 1
            self.assertTrue("Check" in _message)
            self.assertTrue(_data == ["1", "2", "3"])

        def check_fix_sub_validation(_result, _message, _data):
            nonlocal sub_fix_count
            sub_fix_count += 1
            self.assertTrue(_result)
            self.assertTrue("Fix" in _message)
            self.assertTrue([(prim.GetPath()) for prim in _data] == ["/Xform", "/Xform/Cube", "/Xform/Cube2"])

        _sub_check_check = core.model.check_plugins[0].instance.subscribe_check(check_check_sub_validation)  # noqa
        _sub_check_fix = core.model.check_plugins[0].instance.subscribe_fix(check_fix_sub_validation)  # noqa

        with patch.object(_PrintPrims, "_check") as m_mocked:
            v1 = (False, "Check", ["1", "2", "3"])
            v2 = (True, "Check", ["1", "2", "3"])
            if sys.version_info.minor > 7:
                m_mocked.side_effect = [v1, v2]
            else:
                f = asyncio.Future()
                f.set_result(v1)
                f1 = asyncio.Future()
                f1.set_result(v2)
                m_mocked.side_effect = [f, f1]

            await core.deferred_run()

        self.assertTrue(sub_check_count == 2)  # called 2 times: we check, fix, re check
        self.assertTrue(sub_fix_count == 1)
