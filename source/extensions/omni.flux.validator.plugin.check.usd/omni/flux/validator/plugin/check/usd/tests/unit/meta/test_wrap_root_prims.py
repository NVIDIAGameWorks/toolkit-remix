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
from omni.flux.validator.plugin.check.usd.meta.wrap_root_prims import WrapRootPrims
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import get_test_data_path, open_stage, wait_stage_loading


class TestWrapRootPrims(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.attr_name = "flux:wrap"
        self.prim_name = "TestName"

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.attr_name = None

    def _make_core(self, rename_root_prim: bool, set_default_prim: bool):
        return _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "WrapRootPrims",
                        "selector_plugins": [{"name": "Nothing", "data": {}}],
                        "data": {
                            "set_default_prim": set_default_prim,
                            "wrap_prim_name": self.prim_name if rename_root_prim else None,
                        },
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                        "pause_if_fix_failed": False,
                    }
                ],
            }
        )

    async def test_data_is_not_empty_is_empty_should_raise_value_error(self):
        # Arrange
        wrap = WrapRootPrims()

        # Act
        with self.assertRaises(ValueError) as cm:
            wrap.Data.is_not_empty("   ")

        # Assert
        self.assertEqual("The value cannot be empty", str(cm.exception))

    async def test_data_is_not_empty_not_empty_should_return_value(self):
        # Arrange
        wrap = WrapRootPrims()
        input_val = "NotEmpty"

        # Act
        val = wrap.Data.is_not_empty(input_val)

        # Assert
        self.assertEqual(input_val, val)

    async def test_data_is_valid_prim_path_is_not_valid_should_raise_value_error(self):
        # Arrange
        wrap = WrapRootPrims()

        # Act
        with self.assertRaises(ValueError) as cm:
            wrap.Data.is_valid_prim_path("Invalid Test")

        # Assert
        self.assertEqual("The value is not a valid Prim name", str(cm.exception))

    async def test_data_is_valid_prim_path_is_valid_should_return_value(self):
        # Arrange
        wrap = WrapRootPrims()
        input_val = "NotEmpty"

        # Act
        val = wrap.Data.is_valid_prim_path(input_val)

        # Assert
        self.assertEqual(input_val, val)

    async def test_run_fix_set_default_prim(self):
        await self.__run_fix("usd/wrap_fix.usda", "/Group", False, True)

    async def test_run_fix_dont_set_default_prim(self):
        await self.__run_fix("usd/wrap_fix.usda", "/Group", False, False)

    async def test_run_fix_multi_root_set_default_prim(self):
        await self.__run_fix("usd/wrap_multi_root_fix.usda", "/Group", False, True)

    async def test_run_fix_multi_root_dont_set_default_prim(self):
        await self.__run_fix("usd/wrap_multi_root_fix.usda", "/Group", False, False)

    async def test_run_fix_rename_prim(self):
        prim_name = f"/{self.prim_name}"
        await self.__run_fix("usd/wrap_fix.usda", prim_name, True, True)
        await self.__run_fix("usd/wrap_fix.usda", prim_name, True, False)
        await self.__run_fix("usd/wrap_multi_root_fix.usda", prim_name, True, True)
        await self.__run_fix("usd/wrap_multi_root_fix.usda", prim_name, True, False)

    async def __run_fix(self, stage_file: str, final_root_prim: str, rename_root_prim: bool, set_default_prim: bool):
        # Arrange
        await open_stage(get_test_data_path(__name__, stage_file))
        core = self._make_core(rename_root_prim, set_default_prim)

        # Act
        await core.deferred_run()

        # Assert
        stage = omni.usd.get_context().get_stage()

        session_layer = stage.GetSessionLayer()
        root_prims = [p for p in stage.GetPseudoRoot().GetChildren() if not session_layer.GetPrimAtPath(p.GetPath())]

        self.assertTrue(stage.HasDefaultPrim())
        self.assertEqual(len(root_prims), 1)
        self.assertEqual(str(root_prims[0].GetPath()), final_root_prim)

        if set_default_prim:
            self.assertEqual(str(stage.GetDefaultPrim().GetPath()), final_root_prim)
        else:
            # Will not be valid because the prim won't exist anymore
            self.assertFalse(stage.GetDefaultPrim().IsValid())
