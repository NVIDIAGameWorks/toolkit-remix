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

__all__ = ["TestTreeWidgetModel"]

from omni.kit.test import AsyncTestCase

from .helper import MockTreeItem, MockTreeModel


class TestTreeWidgetModel(AsyncTestCase):
    """Tests for the TreeModelBase.get_children_count method."""

    def _create_test_tree(self) -> tuple[MockTreeModel, list[MockTreeItem]]:
        """
        Create a test tree structure:

        Root1
        ├── Child1_1
        │   ├── Grandchild1_1_1
        │   └── Grandchild1_1_2
        └── Child1_2
        Root2
        └── Child2_1
        Root3 (no children)
        """
        grandchild1_1_1 = MockTreeItem("Grandchild1_1_1")
        grandchild1_1_2 = MockTreeItem("Grandchild1_1_2")
        child1_1 = MockTreeItem("Child1_1", children=[grandchild1_1_1, grandchild1_1_2])
        child1_2 = MockTreeItem("Child1_2")
        child2_1 = MockTreeItem("Child2_1")

        root1 = MockTreeItem("Root1", children=[child1_1, child1_2])
        root2 = MockTreeItem("Root2", children=[child2_1])
        root3 = MockTreeItem("Root3")

        all_items = [root1, root2, root3]
        model = MockTreeModel(items=all_items)

        return model, all_items

    async def test_get_children_count_recursive(self):
        """Test get_children_count with recursive=True counts all items."""
        model, _ = self._create_test_tree()

        # Total items: Root1, Child1_1, Grandchild1_1_1, Grandchild1_1_2, Child1_2,
        #              Root2, Child2_1, Root3 = 8 items
        count = model.get_children_count(recursive=True)
        self.assertEqual(8, count)

    async def test_get_children_count_non_recursive(self):
        """Test get_children_count with recursive=False counts only root items."""
        model, _ = self._create_test_tree()

        # Only root items: Root1, Root2, Root3 = 3 items
        count = model.get_children_count(recursive=False)
        self.assertEqual(3, count)

    async def test_get_children_count_from_specific_items(self):
        """Test get_children_count starting from specific items."""
        model, items = self._create_test_tree()
        root1 = items[0]

        # Count from Root1 only: Root1, Child1_1, Grandchild1_1_1, Grandchild1_1_2, Child1_2 = 5 items
        count = model.get_children_count(items=[root1], recursive=True)
        self.assertEqual(5, count)

    async def test_get_children_count_empty_model(self):
        """Test get_children_count with an empty model."""
        model = MockTreeModel(items=[])

        count = model.get_children_count(recursive=True)
        self.assertEqual(0, count)

    async def test_get_children_count_single_item_no_children(self):
        """Test get_children_count with a single item that has no children."""
        single_item = MockTreeItem("SingleItem")
        model = MockTreeModel(items=[single_item])

        count = model.get_children_count(recursive=True)
        self.assertEqual(1, count)
