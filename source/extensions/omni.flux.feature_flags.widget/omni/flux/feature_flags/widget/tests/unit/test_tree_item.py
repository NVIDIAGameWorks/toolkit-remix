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
from omni.flux.feature_flags.widget.tree import FeatureFlagItem
from omni.kit.test import AsyncTestCase


class TestFeatureFlagItem(AsyncTestCase):
    async def setUp(self):
        pass

    # After running each test
    async def tearDown(self):
        pass

    async def test_initialize_item_should_initialize_correctly(self):
        # Arrange
        flag = FeatureFlag("test_key", {"value": True, "display_name": "Test Name", "tooltip": "Test Tooltip"})

        # Act
        item = FeatureFlagItem(flag)

        # Assert
        self.assertEqual(flag.key, item.key)
        self.assertEqual(flag.value, item.value)
        self.assertEqual(flag.display_name, item.display_name)
        self.assertEqual(flag.tooltip, item.tooltip)
