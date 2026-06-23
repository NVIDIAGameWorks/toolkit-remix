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
from lightspeed.trex.stage_manager.plugin.filter.usd.scene_edit_state import SceneEditFilterPlugin

__all__ = ["TestComboboxFilterTooltipsUnit"]

_LAYER_MGR_PATCH = "lightspeed.trex.stage_manager.plugin.filter.usd.is_capture.LayerManagerCore"


class TestComboboxFilterTooltipsUnit(omni.kit.test.AsyncTestCase):
    async def test_filter_active_should_only_be_declared_by_usd_base_filter_class(self):
        # Arrange
        filter_classes = [IsCaptureFilterPlugin, IsCategoryFilterPlugin, RemixLogicPrimsFilterPlugin]

        # Act
        declares_filter_active = {
            filter_class.__name__: "filter_active" in filter_class.__annotations__ for filter_class in filter_classes
        }

        # Assert
        for filter_class in filter_classes:
            with self.subTest(filter_class=filter_class.__name__):
                self.assertFalse(declares_filter_active[filter_class.__name__])

    async def test_asset_state_tooltip_describes_each_combo_box_option(self):
        # Arrange
        with patch(_LAYER_MGR_PATCH):
            plugin = IsCaptureFilterPlugin()

            # Act
            tooltip = plugin.tooltip

        # Assert
        self.assertIn("- All: Show every prim.", tooltip)
        self.assertIn("- Captured: Show prims that still reference captured assets.", tooltip)
        self.assertIn("- Replaced: Show prims using replacement assets instead of captured references.", tooltip)
        self.assertIn("- Deleted: Show captured prims whose reference was removed.", tooltip)

    async def test_remix_category_tooltip_describes_each_combo_box_option_type(self):
        # Arrange
        plugin = IsCategoryFilterPlugin()

        # Act
        tooltip = plugin.tooltip

        # Assert
        self.assertIn("- All Categories: Show every prim.", tooltip)
        self.assertIn(
            "- Individual categories: Show prims assigned to the selected render category.",
            tooltip,
        )

    async def test_remix_logic_tooltip_describes_each_combo_box_option(self):
        # Arrange
        plugin = RemixLogicPrimsFilterPlugin()

        # Act
        tooltip = plugin.tooltip

        # Assert
        self.assertIn("- No Filter: Show every prim.", tooltip)
        self.assertIn("- Graphs Only: Show only OmniGraph graph prims.", tooltip)
        self.assertIn("- Graphs + Nodes: Show OmniGraph graph and node prims.", tooltip)

    async def test_scene_edit_tooltip_describes_each_combo_box_option(self):
        # Arrange
        plugin = SceneEditFilterPlugin()

        # Act
        tooltip = plugin.tooltip

        # Assert
        self.assertIn("- Show all prims: Show every prim in the scene.", tooltip)
        self.assertIn("- Modified prims: Show prims with at least one edit from the selected mod layer(s).", tooltip)
        self.assertIn("- Unedited prims: Show prims with no opinions from the replacement layer tree.", tooltip)
        self.assertIn(
            "- Unused edits: Show prims with mod edits that are shadowed by a stronger opinion.",
            tooltip,
        )

    async def test_asset_state_all_option_should_not_be_active(self):
        # Arrange
        with patch(_LAYER_MGR_PATCH):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.ALL)

            # Act
            filter_active = plugin.filter_active

        # Assert
        self.assertFalse(filter_active)

    async def test_asset_state_specific_option_should_be_active(self):
        # Arrange
        with patch(_LAYER_MGR_PATCH):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.CAPTURED)

            # Act
            filter_active = plugin.filter_active

        # Assert
        self.assertTrue(filter_active)

    async def test_asset_state_filter_active_should_track_all_and_non_default_values(self):
        # Arrange
        with patch(_LAYER_MGR_PATCH):
            plugin = IsCaptureFilterPlugin()

            # Act
            plugin.reference_type = ReferenceType.REPLACED
            replaced_filter_active = plugin.filter_active
            plugin.reference_type = ReferenceType.ALL
            all_filter_active = plugin.filter_active

            # Assert
            self.assertTrue(replaced_filter_active)
            self.assertFalse(all_filter_active)

    async def test_remix_category_all_option_should_not_be_active(self):
        # Arrange
        plugin = IsCategoryFilterPlugin(category_type="All Categories")

        # Act
        filter_active = plugin.filter_active

        # Assert
        self.assertFalse(filter_active)

    async def test_remix_category_specific_option_should_be_active(self):
        # Arrange
        plugin = IsCategoryFilterPlugin()
        category_type = next(label for label in plugin._CATEGORY_DISPLAY_LABELS.values() if label != "All Categories")

        # Act
        plugin = IsCategoryFilterPlugin(category_type=category_type)
        filter_active = plugin.filter_active

        # Assert
        self.assertTrue(filter_active)

    async def test_remix_category_filter_active_should_track_all_and_non_default_values(self):
        # Arrange
        plugin = IsCategoryFilterPlugin()

        # Act
        plugin.category_type = "Sky"
        sky_filter_active = plugin.filter_active
        plugin.category_type = "All Categories"
        all_filter_active = plugin.filter_active

        # Assert
        self.assertTrue(sky_filter_active)
        self.assertFalse(all_filter_active)

    async def test_remix_logic_no_filter_option_should_not_be_active(self):
        # Arrange
        plugin = RemixLogicPrimsFilterPlugin(current_filter_type=FilterTypes.NO_FILTERS)

        # Act
        filter_active = plugin.filter_active

        # Assert
        self.assertFalse(filter_active)

    async def test_remix_logic_specific_option_should_be_active(self):
        # Arrange
        plugin = RemixLogicPrimsFilterPlugin(current_filter_type=FilterTypes.GRAPHS_ONLY)

        # Act
        filter_active = plugin.filter_active

        # Assert
        self.assertTrue(filter_active)

    async def test_remix_logic_filter_active_should_track_no_filter_and_non_default_values(self):
        # Arrange
        plugin = RemixLogicPrimsFilterPlugin()

        # Act
        plugin.current_filter_type = FilterTypes.GRAPHS_AND_NODES
        graphs_and_nodes_filter_active = plugin.filter_active
        plugin.current_filter_type = FilterTypes.NO_FILTERS
        no_filters_filter_active = plugin.filter_active

        # Assert
        self.assertTrue(graphs_and_nodes_filter_active)
        self.assertFalse(no_filters_filter_active)
