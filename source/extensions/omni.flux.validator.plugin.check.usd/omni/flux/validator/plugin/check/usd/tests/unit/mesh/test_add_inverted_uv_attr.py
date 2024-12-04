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
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, open_stage, wait_stage_loading


class TestAddInvertedUVAttr(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    async def test_run_no_fix(self):
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/cube_quads.usda"))
        core = _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "AddInvertedUVAttr",
                        "selector_plugins": [{"name": "AllMeshes", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {}},
                    }
                ],
            }
        )

        sub_check_count = 0
        sub_fix_count = 0

        def check_check_sub_validation(_result, _message, _data):
            nonlocal sub_check_count
            sub_check_count += 1
            self.assertTrue(_result, msg=_message)
            self.assertIn("Check", _message)
            self.assertNotIn("FAIL", _message)
            self.assertIn("PASS: /Cube/Cube", _message)

        def check_fix_sub_validation(_result, _message, _data):
            nonlocal sub_fix_count
            sub_fix_count += 1

        _sub_check_check = core.model.check_plugins[0].instance.subscribe_check(check_check_sub_validation)  # noqa
        _sub_check_fix = core.model.check_plugins[0].instance.subscribe_fix(check_fix_sub_validation)  # noqa

        # Act
        await core.deferred_run()

        # Assert
        self.assertTrue(sub_check_count == 1)
        self.assertTrue(sub_fix_count == 0)  # 0 because the check is good, so we dont run the fix

    async def test_run_fix(self):
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/cube_faceVarying_quads.usda"))
        core = _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "AddInvertedUVAttr",
                        "selector_plugins": [{"name": "AllMeshes", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {}},
                    }
                ],
            }
        )

        sub_check_count = 0
        sub_fix_count = 0

        def check_check_sub_validation(_result, _message, _data):
            nonlocal sub_check_count
            if sub_check_count == 0:
                self.assertFalse(_result, msg=_message)
                self.assertIn("Check", _message)
                self.assertNotIn("PASS", _message)
                self.assertIn("FAIL, never set: /Cube/Cube", _message)
            else:
                self.assertTrue(_result, msg=_message)
                self.assertIn("Check", _message)
                self.assertNotIn("FAIL", _message)
                self.assertIn("PASS: /Cube/Cube", _message)

            sub_check_count += 1

        def check_fix_sub_validation(_result, _message, _data):
            nonlocal sub_fix_count
            sub_fix_count += 1
            self.assertTrue(_result)
            self.assertIn("Fix", _message)
            self.assertNotIn("FAIL", _message)
            self.assertIn("PASS: /Cube/Cube", _message)

        _sub_check_check = core.model.check_plugins[0].instance.subscribe_check(check_check_sub_validation)  # noqa
        _sub_check_fix = core.model.check_plugins[0].instance.subscribe_fix(check_fix_sub_validation)  # noqa

        # Act
        await core.deferred_run()

        # Assert
        self.assertEquals(sub_check_count, 2)  # called 2 times: we check, fix, re check
        self.assertEquals(sub_fix_count, 1)

        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath("/Cube/Cube")

        attr = prim.GetAttribute("invertedUvs")
        self.assertTrue(attr)
        inverted_uvs = attr.Get()
        self.assertEquals(len(inverted_uvs), 24)
        uv_attr = prim.GetAttribute("primvars:st")
        uvs = uv_attr.Get()
        for i in range(0, len(inverted_uvs)):  # noqa PLC0200
            self.assertEquals(inverted_uvs[i][0], uvs[i][0])
            self.assertEquals(inverted_uvs[i][1], -uvs[i][1])

    async def test_run_fix_bad_length(self):
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/cube_faceVarying_triangulated.usda"))
        core = _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "AddInvertedUVAttr",
                        "selector_plugins": [{"name": "AllMeshes", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {}},
                    }
                ],
            }
        )

        sub_check_count = 0
        sub_fix_count = 0

        def check_check_sub_validation(_result, _message, _data):
            nonlocal sub_check_count
            if sub_check_count == 0:
                self.assertFalse(_result)
                self.assertIn("Check", _message)
                self.assertNotIn("PASS", _message)
                self.assertIn("FAIL, length mismatch: /Cube/Cube", _message)
            else:
                self.assertTrue(_result)
                self.assertIn("Check", _message)
                self.assertNotIn("FAIL", _message)
                self.assertIn("PASS: /Cube/Cube", _message)

            sub_check_count += 1

        def check_fix_sub_validation(_result, _message, _data):
            nonlocal sub_fix_count
            sub_fix_count += 1
            self.assertTrue(_result)
            self.assertIn("Fix", _message)
            self.assertNotIn("FAIL", _message)
            self.assertIn("PASS: /Cube/Cube", _message)

        _sub_check_check = core.model.check_plugins[0].instance.subscribe_check(check_check_sub_validation)  # noqa
        _sub_check_fix = core.model.check_plugins[0].instance.subscribe_fix(check_fix_sub_validation)  # noqa

        # Act
        await core.deferred_run()

        # Assert
        self.assertEquals(sub_check_count, 2)  # called 2 times: we check, fix, re check
        self.assertEquals(sub_fix_count, 1)

        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath("/Cube/Cube")

        attr = prim.GetAttribute("invertedUvs")
        self.assertTrue(attr)
        inverted_uvs = attr.Get()
        self.assertEquals(len(inverted_uvs), 36)
        uv_attr = prim.GetAttribute("primvars:st")
        uvs = uv_attr.Get()
        for i in range(0, len(inverted_uvs)):  # noqa PLC0200
            self.assertEquals(inverted_uvs[i][0], uvs[i][0])
            self.assertEquals(inverted_uvs[i][1], -uvs[i][1])

    async def test_run_fix_bad_values(self):
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/cube_triangulated.usda"))
        core = _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "AddInvertedUVAttr",
                        "selector_plugins": [{"name": "AllMeshes", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {}},
                    }
                ],
            }
        )

        sub_check_count = 0
        sub_fix_count = 0

        def check_check_sub_validation(_result, _message, _data):
            nonlocal sub_check_count
            if sub_check_count == 0:
                self.assertFalse(_result)
                self.assertIn("Check", _message)
                self.assertNotIn("PASS", _message)
                self.assertIn("FAIL, value mismatch: /Cube/Cube", _message)
            else:
                self.assertTrue(_result)
                self.assertIn("Check", _message)
                self.assertNotIn("FAIL", _message)
                self.assertIn("PASS: /Cube/Cube", _message)

            sub_check_count += 1

        def check_fix_sub_validation(_result, _message, _data):
            nonlocal sub_fix_count
            sub_fix_count += 1
            self.assertTrue(_result)
            self.assertIn("Fix", _message)
            self.assertNotIn("FAIL", _message)
            self.assertIn("PASS: /Cube/Cube", _message)

        _sub_check_check = core.model.check_plugins[0].instance.subscribe_check(check_check_sub_validation)  # noqa
        _sub_check_fix = core.model.check_plugins[0].instance.subscribe_fix(check_fix_sub_validation)  # noqa

        # Act
        await core.deferred_run()

        # Assert
        self.assertEquals(sub_check_count, 2)  # called 2 times: we check, fix, re check
        self.assertEquals(sub_fix_count, 1)

        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath("/Cube/Cube")

        attr = prim.GetAttribute("invertedUvs")
        self.assertTrue(attr)
        inverted_uvs = attr.Get()
        self.assertEquals(len(inverted_uvs), 8)
        uv_attr = prim.GetAttribute("primvars:st")
        uvs = uv_attr.Get()
        for i in range(0, len(inverted_uvs)):  # noqa PLC0200
            self.assertEquals(inverted_uvs[i][0], uvs[i][0])
            self.assertEquals(inverted_uvs[i][1], -uvs[i][1])
