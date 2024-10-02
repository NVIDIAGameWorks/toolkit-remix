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

from omni.flux.feature_flags.core import FeatureFlag
from omni.kit.test.async_unittest import AsyncTestCase


class TestFeatureFlag(AsyncTestCase):
    async def setUp(self):
        pass

    # After running each test
    async def tearDown(self):
        pass

    async def test_initialize_item_initializes_correctly(self):
        for key, data in {
            "test_feature_with_data": {
                "value": 1,
                "display_name": "Test Feature",
                "Tooltip": "Tooltip",
                "extra": "Extra",
            },
            "test_feature_value_only": {"value": False},
        }.items():
            with self.subTest(title=f"key_{key}"):
                # Arrange
                pass

                # Act
                item = FeatureFlag(key, data)

                # Assert
                self.assertEqual(item.key, key)
                self.assertEqual(item.value, data["value"])
                self.assertEqual(item.display_name, data["display_name"] if "display_name" in data else key)
                self.assertEqual(item.tooltip, data["tooltip"] if "tooltip" in data else "")

    async def test_initialize_item_no_value_should_raise_value_error(self):
        # Arrange
        key = "invalid_test_feature"
        data = {}

        with self.assertRaises(ValueError) as cm:
            # Act
            _ = FeatureFlag(key, data)

        # Assert
        self.assertEqual(str(cm.exception), "Expected feature flag value but got no data.")
