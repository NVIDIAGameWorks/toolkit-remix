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

from contextlib import nullcontext

import omni.usd
from lightspeed.trex.asset_replacements.core.shared.data_models import AssetReplacementsValidators
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import wait_stage_loading


class TestAssetReplacementsValidators(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if self.context.can_close_stage():
            await self.context.close_stage_async()
        self.context = None

    async def test_is_valid_prim_returns_expected_value_or_raises(self):
        # Arrange
        valid_prim_path = "/test/prim/value"

        test_cases = {
            valid_prim_path: (True, None),
            "This.Is/Not A Prim": (False, "The string is not a valid prim path"),
            "/test/non/existent/prim": (False, "The prim path does not exist in the current stage"),
        }

        for prim_path, expected_value in test_cases.items():
            success, message = expected_value

            with self.subTest(title=f"prim_path_{prim_path}_success_{success}"):
                self.context.get_stage().DefinePrim(valid_prim_path, "Scope")

                # Act
                with nullcontext() if success else self.assertRaises(ValueError) as cm:
                    value = AssetReplacementsValidators.is_valid_prim(prim_path, "")

                # Assert
                if success:
                    self.assertEqual(value, prim_path)
                else:
                    self.assertEqual(str(cm.exception), f"{message}: {prim_path}")
