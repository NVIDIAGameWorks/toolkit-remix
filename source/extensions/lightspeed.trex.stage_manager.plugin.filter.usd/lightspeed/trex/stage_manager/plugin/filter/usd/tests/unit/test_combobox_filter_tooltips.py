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

from unittest.mock import patch

import omni.kit.test
from lightspeed.trex.stage_manager.plugin.filter.usd.is_capture import IsCaptureFilterPlugin, ReferenceType
from lightspeed.trex.stage_manager.plugin.filter.usd.is_category import IsCategoryFilterPlugin
from lightspeed.trex.stage_manager.plugin.filter.usd.is_logic_graph import FilterTypes, RemixLogicPrimsFilterPlugin

__all__ = ["TestComboboxFilterTooltipsUnit"]

_LAYER_MGR_PATCH = "lightspeed.trex.stage_manager.plugin.filter.usd.is_capture.LayerManagerCore"


class TestComboboxFilterTooltipsUnit(omni.kit.test.AsyncTestCase):
    async def test_filter_active_should_only_be_declared_by_usd_base_filter_class(self):
        # Arrange
        filter_classes = [IsCaptureFilterPlugin, IsCategoryFilterPlugin, RemixLogicPrimsFilterPlugin]

        # Assert
        for filter_class in filter_classes:
            with self.subTest(filter_class=filter_class.__name__):
                self.assertNotIn("filter_active", filter_class.__annotations__)

    async def test_asset_state_tooltip_describes_each_combo_box_option(self):
        # Arrange / Act
        with patch(_LAYER_MGR_PATCH):
            tooltip = IsCaptureFilterPlugin().tooltip

        # Assert
        self.assertIn("- All: Show every prim.", tooltip)
        self.assertIn("- Captured: Show prims that still reference captured assets.", tooltip)
        self.assertIn("- Replaced: Show prims using replacement assets instead of captured references.", tooltip)
        self.assertIn("- Deleted: Show captured prims whose reference was removed.", tooltip)

    async def test_remix_category_tooltip_describes_each_combo_box_option_type(self):
        # Arrange / Act
        tooltip = IsCategoryFilterPlugin().tooltip

        # Assert
        self.assertIn("- All Categories: Show every prim.", tooltip)
        self.assertIn(
            "- Individual categories: Show prims assigned to the selected render category.",
            tooltip,
        )

    async def test_remix_logic_tooltip_describes_each_combo_box_option(self):
        # Arrange / Act
        tooltip = RemixLogicPrimsFilterPlugin().tooltip

        # Assert
        self.assertIn("- No Filter: Show every prim.", tooltip)
        self.assertIn("- Graphs Only: Show only OmniGraph graph prims.", tooltip)
        self.assertIn("- Graphs + Nodes: Show OmniGraph graph and node prims.", tooltip)

    async def test_asset_state_all_option_should_not_be_active(self):
        # Arrange / Act
        with patch(_LAYER_MGR_PATCH):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.ALL)

        # Assert
        self.assertFalse(plugin.filter_active)

    async def test_asset_state_specific_option_should_be_active(self):
        # Arrange / Act
        with patch(_LAYER_MGR_PATCH):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.CAPTURED)

        # Assert
        self.assertTrue(plugin.filter_active)

    async def test_asset_state_filter_active_should_track_all_and_non_default_values(self):
        # Arrange
        with patch(_LAYER_MGR_PATCH):
            plugin = IsCaptureFilterPlugin()

            # Act
            plugin.reference_type = ReferenceType.REPLACED

            # Assert
            self.assertTrue(plugin.filter_active)

            # Act
            plugin.reference_type = ReferenceType.ALL

            # Assert
            self.assertFalse(plugin.filter_active)

    async def test_remix_category_all_option_should_not_be_active(self):
        # Arrange / Act
        plugin = IsCategoryFilterPlugin(category_type="All Categories")

        # Assert
        self.assertFalse(plugin.filter_active)

    async def test_remix_category_specific_option_should_be_active(self):
        # Arrange
        plugin = IsCategoryFilterPlugin()
        category_type = next(label for label in plugin._CATEGORY_DISPLAY_LABELS.values() if label != "All Categories")

        # Act
        plugin = IsCategoryFilterPlugin(category_type=category_type)

        # Assert
        self.assertTrue(plugin.filter_active)

    async def test_remix_category_filter_active_should_track_all_and_non_default_values(self):
        # Arrange
        plugin = IsCategoryFilterPlugin()

        # Act
        plugin.category_type = "Sky"

        # Assert
        self.assertTrue(plugin.filter_active)

        # Act
        plugin.category_type = "All Categories"

        # Assert
        self.assertFalse(plugin.filter_active)

    async def test_remix_logic_no_filter_option_should_not_be_active(self):
        # Arrange / Act
        plugin = RemixLogicPrimsFilterPlugin(current_filter_type=FilterTypes.NO_FILTERS)

        # Assert
        self.assertFalse(plugin.filter_active)

    async def test_remix_logic_specific_option_should_be_active(self):
        # Arrange / Act
        plugin = RemixLogicPrimsFilterPlugin(current_filter_type=FilterTypes.GRAPHS_ONLY)

        # Assert
        self.assertTrue(plugin.filter_active)

    async def test_remix_logic_filter_active_should_track_no_filter_and_non_default_values(self):
        # Arrange
        plugin = RemixLogicPrimsFilterPlugin()

        # Act
        plugin.current_filter_type = FilterTypes.GRAPHS_AND_NODES

        # Assert
        self.assertTrue(plugin.filter_active)

        # Act
        plugin.current_filter_type = FilterTypes.NO_FILTERS

        # Assert
        self.assertFalse(plugin.filter_active)
