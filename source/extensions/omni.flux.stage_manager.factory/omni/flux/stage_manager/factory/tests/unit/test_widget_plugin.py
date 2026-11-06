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

from typing import ClassVar

import omni.kit.test
from omni.flux.stage_manager.factory.plugins.tree_plugin import (
    StageManagerTreeItem,
    StageManagerTreeItemProxy,
    StageManagerTreeModel,
    TreeRefreshResult,
)
from omni.flux.stage_manager.factory.plugins.widget_plugin import StageManagerWidgetPlugin

__all__ = ["TestStageManagerWidgetPlugin"]


class _TreeItem(StageManagerTreeItem):
    """Provide concrete canonical rows for action targeting."""

    @property
    def default_attr(self):
        """Return the inherited cleanup attributes."""
        return super().default_attr


class _VirtualTreeItem(_TreeItem):
    """Provide a synthetic grouping row."""

    @property
    def is_virtual(self):
        """Return whether this row is a virtual group."""
        return True


class _TreeModel(StageManagerTreeModel):
    """Provide a concrete model for publishing action rows."""

    @property
    def default_attr(self):
        """Return the inherited cleanup attributes."""
        return super().default_attr


class _WidgetPlugin(StageManagerWidgetPlugin):
    """Provide a widget without constructing UI."""

    display_name: str = "Test"
    tooltip: str = "Test"

    def build_ui(self, model, item, level, expanded):
        """Leave UI construction unused in query tests."""


class _RowOnlyWidgetPlugin(_WidgetPlugin):
    """Limit actions to the clicked row."""

    _action_row_only: ClassVar[bool] = True


class TestStageManagerWidgetPlugin(omni.kit.test.AsyncTestCase):
    """Verify row identity and selection order for pure action queries."""

    def _publish(self, *items):
        """Publish real proxies before a test assigns selection."""
        proxies = [StageManagerTreeItemProxy(item) for item in items]
        model = _TreeModel()
        model.publish_refresh_result(
            TreeRefreshResult(
                canonical_root_items=list(items),
                root_items=proxies,
                items_by_path={},
                item_by_hash={hash(proxy): proxy for proxy in proxies},
                path_by_hash={},
                visible_items_count=len(items),
                visible_non_virtual_items_count=sum(not item.is_virtual for item in items),
                input_items_count=len(items),
                output_items_count=len(items),
            )
        )
        return model, proxies

    async def test_get_action_items_selected_row_preserves_order_and_selection(self):
        """Return selected rows in order without changing the selection."""
        # Arrange
        first, second = _TreeItem("First", None), _TreeItem("Second", None)
        model, proxies = self._publish(first, second)
        model.selection = [proxies[1], proxies[0]]
        selection = model.selection

        # Act
        result = _WidgetPlugin()._get_action_items(model, first)

        # Assert
        self.assertEqual(result, [second, first])
        self.assertEqual(len(model.selection), len(selection))
        self.assertTrue(all(actual is expected for actual, expected in zip(model.selection, selection)))

    async def test_get_action_items_unselected_row_uses_clicked_row(self):
        """Target only the unselected clicked row without changing selection."""
        # Arrange
        first, second = _TreeItem("First", None), _TreeItem("Second", None)
        model, proxies = self._publish(first, second)
        model.selection = [proxies[0]]

        # Act
        result = _WidgetPlugin()._get_action_items(model, second)

        # Assert
        self.assertEqual(result, [second])
        self.assertEqual(model.selection, [proxies[0]])

    async def test_get_action_items_row_only_uses_clicked_row(self):
        """Restrict row-only actions to the clicked row."""
        # Arrange
        first, second = _TreeItem("First", None), _TreeItem("Second", None)
        model, proxies = self._publish(first, second)
        model.selection = proxies
        plugin = _RowOnlyWidgetPlugin()

        # Act
        result = plugin._get_action_items(model, second)

        # Assert
        self.assertEqual(result, [second])

    async def test_get_action_items_obsolete_selected_proxy_excludes_obsolete_row(self):
        """Exclude selected proxies absent from the current model."""
        # Arrange
        first, second = _TreeItem("First", None), _TreeItem("Second", None)
        obsolete = StageManagerTreeItemProxy(_TreeItem("Second", None))
        model, proxies = self._publish(first, second)
        model.selection = [obsolete, proxies[0]]

        # Act
        result = _WidgetPlugin()._get_action_items(model, first)

        # Assert
        self.assertEqual(result, [first])

    async def test_get_action_items_unpublished_clicked_row_returns_empty(self):
        """Return no targets for a clicked row absent from the model."""
        # Arrange
        model, proxies = self._publish(_TreeItem("First", None))
        model.selection = proxies
        obsolete = _TreeItem("First", None)
        StageManagerTreeItemProxy(obsolete)

        # Act
        result = _WidgetPlugin()._get_action_items(model, obsolete)

        # Assert
        self.assertEqual(result, [])

    async def test_get_action_items_virtual_and_duplicate_paths_preserve_row_identity(self):
        """Distinguish clicked rows from selected rows sharing their path."""
        # Arrange
        group = _VirtualTreeItem("Group", None)
        first = _TreeItem("First", None, path="/Shared")
        second = _TreeItem("Second", None, path="/Shared")
        model, proxies = self._publish(group, first, second)
        model.selection = [proxies[0], proxies[1]]

        # Act
        result = _WidgetPlugin()._get_action_items(model, second)

        # Assert
        self.assertEqual(len(result), 1)
        self.assertIs(result[0], second)

    async def test_get_action_items_selected_virtual_row_keeps_pathless_selection(self):
        """Include virtual and pathless rows in selected targets."""
        # Arrange
        group, pathless = _VirtualTreeItem("Group", None), _TreeItem("Pathless", None)
        model, proxies = self._publish(group, pathless)
        model.selection = proxies

        # Act
        result = _WidgetPlugin()._get_action_items(model, group)

        # Assert
        self.assertEqual(result, [group, pathless])
