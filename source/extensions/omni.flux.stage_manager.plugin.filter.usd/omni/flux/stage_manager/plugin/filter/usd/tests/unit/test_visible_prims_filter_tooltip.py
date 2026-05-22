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
from omni.flux.stage_manager.plugin.filter.usd.visible_prims import VisiblePrimsFilterPlugin

__all__ = ["TestVisiblePrimsFilterTooltipUnit"]


class TestVisiblePrimsFilterTooltipUnit(omni.kit.test.AsyncTestCase):
    async def test_visibility_filter_tooltip_describes_each_combo_box_option(self):
        # Arrange / Act
        tooltip = VisiblePrimsFilterPlugin().tooltip

        # Assert
        self.assertIn("- All Prims: Show every prim.", tooltip)
        self.assertIn("- Visible Prims: Show imageable prims that resolve visible.", tooltip)
        self.assertIn("- Hidden Prims: Show imageable prims that resolve invisible.", tooltip)

    async def test_filter_active_all_prims_should_return_false(self):
        # Arrange
        plugin = VisiblePrimsFilterPlugin(visible_prims_type="All Prims")

        # Assert
        self.assertFalse(plugin.filter_active)

    async def test_filter_active_specific_visibility_should_return_true(self):
        # Arrange
        plugin = VisiblePrimsFilterPlugin(visible_prims_type="Visible Prims")

        # Assert
        self.assertTrue(plugin.filter_active)

    async def test_filter_active_should_track_default_and_non_default_visibility_values(self):
        # Arrange
        plugin = VisiblePrimsFilterPlugin()

        # Act
        plugin.visible_prims_type = "Hidden Prims"

        # Assert
        self.assertTrue(plugin.filter_active)

        # Act
        plugin.visible_prims_type = "All Prims"

        # Assert
        self.assertFalse(plugin.filter_active)
