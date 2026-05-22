"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import omni.kit.test
from omni.flux.stage_manager.plugin.filter.usd.ignore_prims import IgnorePrimsFilterPlugin

__all__ = ["TestIgnorePrimsFilterPluginUnit"]


class TestIgnorePrimsFilterPluginUnit(omni.kit.test.AsyncTestCase):
    async def test_filter_active_should_be_false_with_empty_ignore_paths(self):
        # Arrange / Act
        plugin = IgnorePrimsFilterPlugin()

        # Assert
        self.assertFalse(plugin.filter_active)

    async def test_filter_active_should_be_true_with_ignore_paths(self):
        # Arrange / Act
        plugin = IgnorePrimsFilterPlugin(ignore_prim_paths={"/World/Omni"})

        # Assert
        self.assertTrue(plugin.filter_active)
