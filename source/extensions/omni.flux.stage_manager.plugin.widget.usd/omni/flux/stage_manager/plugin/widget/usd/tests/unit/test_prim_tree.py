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

from unittest.mock import Mock, PropertyMock, patch

import omni.kit.test

from ... import prim_tree
from ...prim_tree import PrimTreeWidgetPlugin

__all__ = ["TestPrimTreeWidgetPlugin"]


class TestPrimTreeWidgetPlugin(omni.kit.test.AsyncTestCase):
    """Test Prim Tree widget construction."""

    async def test_build_ui_with_icon_reads_item_icon_once(self):
        """Read the item icon once while building the icon branch."""
        # Arrange
        plugin = PrimTreeWidgetPlugin()
        item = Mock(tooltip="")

        # Act
        with (
            patch.object(type(item), "icon", new_callable=PropertyMock, create=True, return_value="TestIcon") as icon,
            patch.object(prim_tree.ui, "HStack"),
            patch.object(prim_tree.ui, "VStack") as vstack,
            patch.object(prim_tree.ui, "Spacer"),
            patch.object(prim_tree.ui, "Image") as image,
        ):
            plugin.build_ui(Mock(), item, 0, False)

        # Assert
        icon.assert_called_once_with()
        vstack.assert_called_once_with(width=0)
        self.assertEqual("TestIcon", image.call_args.kwargs["name"])
        item.build_widget.assert_called_once_with()

    async def test_build_ui_without_icon_builds_spacer_and_item_widget(self):
        """Build the spacer fallback without rereading the item icon."""
        # Arrange
        plugin = PrimTreeWidgetPlugin()
        item = Mock(tooltip="")

        # Act
        with (
            patch.object(type(item), "icon", new_callable=PropertyMock, create=True, return_value=None) as icon,
            patch.object(prim_tree.ui, "HStack"),
            patch.object(prim_tree.ui, "VStack") as vstack,
            patch.object(prim_tree.ui, "Spacer") as spacer,
            patch.object(prim_tree.ui, "Image") as image,
        ):
            plugin.build_ui(Mock(), item, 0, False)

        # Assert
        icon.assert_called_once_with()
        vstack.assert_not_called()
        image.assert_not_called()
        spacer.assert_called_once_with(height=0, width=0)
        item.build_widget.assert_called_once_with()

    async def test_build_overview_uses_published_non_virtual_count_without_tree_traversal(self):
        """Render singular and plural published counts without traversing the visible tree."""
        test_cases = (
            ("singular count", 1, "1 prim available"),
            ("plural count", 2, "2 prims available"),
        )

        for title, count, expected_text in test_cases:
            with self.subTest(title=title):
                # Arrange
                plugin = PrimTreeWidgetPlugin()
                model = Mock()
                model.visible_non_virtual_items_count = count
                model.iter_items_children.side_effect = AssertionError(
                    "The overview must not traverse the visible tree"
                )

                # Act
                with patch.object(prim_tree.ui, "Label") as label:
                    plugin.build_overview_ui(model)

                # Assert
                label.assert_called_once_with(expected_text)
                model.iter_items_children.assert_not_called()
