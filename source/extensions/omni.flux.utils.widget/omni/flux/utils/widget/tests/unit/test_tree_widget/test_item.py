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

__all__ = ["TestTreeItemBase"]

from omni.kit.test import AsyncTestCase

from .helper import MockTreeItem


class TestTreeItemBase(AsyncTestCase):
    """Tests for the TreeItemBase class."""

    # ===== Initialization Tests =====

    async def test_init_without_children(self):
        """Test that an item can be created without children."""
        item = MockTreeItem("Root")

        self.assertEqual("Root", item.name)
        self.assertEqual([], item.children)
        self.assertIsNone(item.parent)

    async def test_init_with_children(self):
        """Test that an item can be created with children."""
        child1 = MockTreeItem("Child1")
        child2 = MockTreeItem("Child2")
        parent = MockTreeItem("Parent", children=[child1, child2])

        self.assertEqual([child1, child2], parent.children)
        self.assertIs(parent, child1.parent)
        self.assertIs(parent, child2.parent)

    async def test_init_sets_parent_on_children(self):
        """Test that initializing with children sets parent references."""
        grandchild = MockTreeItem("Grandchild")
        child = MockTreeItem("Child", children=[grandchild])
        root = MockTreeItem("Root", children=[child])

        self.assertIs(root, child.parent)
        self.assertIs(child, grandchild.parent)
        self.assertIsNone(root.parent)

    # ===== add_child Tests =====

    async def test_add_child_sets_parent(self):
        """Test that add_child sets the child's parent reference."""
        parent = MockTreeItem("Parent")
        child = MockTreeItem("Child")

        child.parent = parent

        self.assertIs(parent, child.parent)

    async def test_add_child_appends_to_children_list(self):
        """Test that add_child appends the child to the children list."""
        parent = MockTreeItem("Parent")
        child1 = MockTreeItem("Child1")
        child2 = MockTreeItem("Child2")

        child1.parent = parent
        child2.parent = parent

        self.assertEqual([child1, child2], parent.children)

    async def test_add_child_preserves_order(self):
        """Test that children are added in order."""
        parent = MockTreeItem("Parent")
        children = [MockTreeItem(f"Child{i}") for i in range(5)]

        for child in children:
            child.parent = parent

        self.assertEqual(children, parent.children)

    # ===== clear_children Tests =====

    async def test_clear_children_removes_all_children(self):
        """Test that clear_children removes all children from the list."""
        child1 = MockTreeItem("Child1")
        child2 = MockTreeItem("Child2")
        parent = MockTreeItem("Parent", children=[child1, child2])

        parent.clear_children()

        self.assertEqual([], parent.children)

    async def test_clear_children_clears_parent_references(self):
        """Test that clear_children sets children's parent to None."""
        child1 = MockTreeItem("Child1")
        child2 = MockTreeItem("Child2")
        parent = MockTreeItem("Parent", children=[child1, child2])

        parent.clear_children()

        self.assertIsNone(child1.parent)
        self.assertIsNone(child2.parent)

    async def test_clear_children_on_empty_item(self):
        """Test that clear_children works on an item with no children."""
        item = MockTreeItem("Empty")

        # Should not raise
        item.clear_children()

        self.assertEqual([], item.children)

    # ===== parent property Tests =====

    async def test_parent_getter_returns_none_for_root(self):
        """Test that parent returns None for root items."""
        root = MockTreeItem("Root")

        self.assertIsNone(root.parent)

    async def test_parent_getter_returns_correct_parent(self):
        """Test that parent returns the correct parent item."""
        child = MockTreeItem("Child")
        parent = MockTreeItem("Parent", children=[child])

        self.assertIs(parent, child.parent)

    # ===== parent setter Tests =====

    async def test_parent_setter_adds_to_new_parent(self):
        """Test that setting parent adds item to new parent's children."""
        child = MockTreeItem("Child")
        new_parent = MockTreeItem("NewParent")

        child.parent = new_parent

        self.assertIn(child, new_parent.children)
        self.assertIs(new_parent, child.parent)

    async def test_parent_setter_removes_from_old_parent(self):
        """Test that setting parent removes item from old parent's children."""
        child = MockTreeItem("Child")
        old_parent = MockTreeItem("OldParent", children=[child])
        new_parent = MockTreeItem("NewParent")

        child.parent = new_parent

        self.assertNotIn(child, old_parent.children)
        self.assertIn(child, new_parent.children)

    async def test_parent_setter_to_none_removes_from_parent(self):
        """Test that setting parent to None removes item from parent's children."""
        child = MockTreeItem("Child")
        parent = MockTreeItem("Parent", children=[child])

        child.parent = None

        self.assertNotIn(child, parent.children)
        self.assertIsNone(child.parent)

    async def test_parent_setter_reparenting_preserves_siblings(self):
        """Test that reparenting doesn't affect siblings."""
        child1 = MockTreeItem("Child1")
        child2 = MockTreeItem("Child2")
        old_parent = MockTreeItem("OldParent", children=[child1, child2])
        new_parent = MockTreeItem("NewParent")

        child1.parent = new_parent

        # child2 should still be in old_parent
        self.assertIn(child2, old_parent.children)
        self.assertIs(old_parent, child2.parent)
        # child1 should be in new_parent
        self.assertIn(child1, new_parent.children)

    async def test_parent_setter_from_none_to_parent(self):
        """Test setting parent on an orphan item."""
        orphan = MockTreeItem("Orphan")
        parent = MockTreeItem("Parent")

        orphan.parent = parent

        self.assertIs(parent, orphan.parent)
        self.assertIn(orphan, parent.children)

    async def test_parent_setter_move_between_parents(self):
        """Test moving an item between different parents."""
        child = MockTreeItem("Child")
        parent1 = MockTreeItem("Parent1", children=[child])
        parent2 = MockTreeItem("Parent2")

        # Move to parent2
        child.parent = parent2

        self.assertEqual([], parent1.children)
        self.assertEqual([child], parent2.children)
        self.assertIs(parent2, child.parent)

    # ===== children property Tests =====

    async def test_children_returns_empty_list_for_leaf(self):
        """Test that children returns empty list for leaf items."""
        leaf = MockTreeItem("Leaf")

        self.assertEqual([], leaf.children)

    async def test_children_returns_all_children(self):
        """Test that children returns all child items."""
        child1 = MockTreeItem("Child1")
        child2 = MockTreeItem("Child2")
        child3 = MockTreeItem("Child3")
        parent = MockTreeItem("Parent", children=[child1, child2, child3])

        self.assertEqual([child1, child2, child3], parent.children)

    # ===== Integration Tests =====

    async def test_deep_hierarchy(self):
        """Test parent-child relationships in a deep hierarchy."""
        level3 = MockTreeItem("Level3")
        level2 = MockTreeItem("Level2", children=[level3])
        level1 = MockTreeItem("Level1", children=[level2])
        root = MockTreeItem("Root", children=[level1])

        self.assertIsNone(root.parent)
        self.assertIs(root, level1.parent)
        self.assertIs(level1, level2.parent)
        self.assertIs(level2, level3.parent)

    async def test_reparent_subtree(self):
        """Test moving a subtree to a different parent."""
        grandchild = MockTreeItem("Grandchild")
        child = MockTreeItem("Child", children=[grandchild])
        old_root = MockTreeItem("OldRoot", children=[child])
        new_root = MockTreeItem("NewRoot")

        # Move the subtree
        child.parent = new_root

        # Verify old_root is empty
        self.assertEqual([], old_root.children)
        # Verify new_root has the subtree
        self.assertEqual([child], new_root.children)
        # Verify grandchild still has child as parent
        self.assertIs(child, grandchild.parent)
        # Verify child's parent is new_root
        self.assertIs(new_root, child.parent)
