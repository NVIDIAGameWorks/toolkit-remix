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

__all__ = ["TestScrollingTreeWidget"]
import gc

import omni.kit.app
import omni.usd
from omni import ui
from omni.flux.utils.widget.scrolling_tree_view import ScrollingTreeWidget
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows

from .test_tree_widget.helper import MockTreeDelegate, MockTreeItem, MockTreeModel


class TestScrollingTreeWidget(AsyncTestCase):
    """Tests for the ScrollingTreeWidget class."""

    async def setUp(self):
        await omni.usd.get_context().new_stage_async()

    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    def _create_test_tree(self) -> tuple[MockTreeModel, MockTreeDelegate, list[MockTreeItem]]:
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
        delegate = MockTreeDelegate()

        return model, delegate, all_items

    async def test_widget_creation(self):
        """Test that ScrollingTreeWidget can be created successfully."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestScrollingTreeWidget", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        self.assertIsNotNone(widget)
        self.assertIsNotNone(widget._tree_widget)  # pylint: disable=protected-access
        self.assertIsNotNone(widget._tree_scroll_frame)  # pylint: disable=protected-access

        # Cleanup
        del widget
        window.destroy()

    async def test_widget_creation_with_alternating_rows(self):
        """Test that ScrollingTreeWidget can be created with alternating rows enabled."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestScrollingTreeWidgetAlternating", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(
                model,
                delegate,
                alternating_rows=True,
                header_height=32,
                row_height=32,
            )

        self.assertIsNotNone(widget)
        self.assertIsNotNone(widget._alternating_row_widget)  # pylint: disable=protected-access

        # Cleanup
        del widget
        window.destroy()

    async def test_iter_visible_items_top_level_only(self):
        """Test iter_visible_items returns only top-level items when nothing is expanded."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestIterVisibleItems", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # With no items expanded, should only get root items in order
        visible_items = list(widget.iter_visible_items())
        visible_names = [item.name for item in visible_items]

        self.assertEqual(["Root1", "Root2", "Root3"], visible_names)

        # Cleanup
        del widget
        window.destroy()

    async def test_iter_visible_items_with_expansion(self):
        """Test iter_visible_items returns items in correct visual order when expanded."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestIterVisibleItemsExpanded", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Expand Root1
        widget.set_expanded(root1, True, False)
        await omni.kit.app.get_app().next_update_async()

        visible_items = list(widget.iter_visible_items())
        visible_names = [item.name for item in visible_items]

        # Should see Root1, then its children, then Root2 and Root3
        # This is the key test - items should be in VISUAL order (BFS), not DFS
        expected_order = ["Root1", "Child1_1", "Child1_2", "Root2", "Root3"]
        self.assertEqual(expected_order, visible_names)

        # Cleanup
        del widget
        window.destroy()

    async def test_iter_visible_items_deeply_nested(self):
        """Test iter_visible_items with deeply nested expansion."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        child1_1 = root1.children[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestIterVisibleItemsDeepNested", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Expand Root1 and Child1_1
        widget.set_expanded(root1, True, False)
        widget.set_expanded(child1_1, True, False)
        await omni.kit.app.get_app().next_update_async()

        visible_items = list(widget.iter_visible_items())
        visible_names = [item.name for item in visible_items]

        # Should be in visual display order
        expected_order = [
            "Root1",
            "Child1_1",
            "Grandchild1_1_1",
            "Grandchild1_1_2",
            "Child1_2",
            "Root2",
            "Root3",
        ]
        self.assertEqual(expected_order, visible_names)

        # Cleanup
        del widget
        window.destroy()

    async def test_iter_visible_items_non_recursive(self):
        """Test iter_visible_items with recursive=False returns only top-level items."""
        model, delegate, items = self._create_test_tree()
        root1, _, _ = items

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestIterVisibleItemsNonRecursive", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Expand Root1 - but with recursive=False, we should only get top-level
        widget.set_expanded(root1, True, False)
        await omni.kit.app.get_app().next_update_async()

        visible_items = list(widget.iter_visible_items(recursive=False))
        visible_names = [item.name for item in visible_items]

        self.assertEqual(["Root1", "Root2", "Root3"], visible_names)

        # Cleanup
        del widget
        window.destroy()

    async def test_selection_property(self):
        """Test that selection property delegates to the underlying tree widget."""
        model, delegate, items = self._create_test_tree()
        root1, root2, _ = items

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSelectionProperty", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate, select_all_children=False)

        await omni.kit.app.get_app().next_update_async()

        # Set selection
        widget.selection = [root1, root2]

        # Get selection
        selection = widget.selection
        self.assertEqual(2, len(selection))
        self.assertIn(root1, selection)
        self.assertIn(root2, selection)

        # Cleanup
        del widget
        window.destroy()

    async def test_subscribe_selection_changed(self):
        """Test that selection change subscription works."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSelectionChangedSub", height=400, width=400)

        selection_changed_called = False
        received_items = []

        def on_selection_changed(selected_items):
            nonlocal selection_changed_called, received_items
            selection_changed_called = True
            received_items = selected_items

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate, select_all_children=False)

        await omni.kit.app.get_app().next_update_async()

        # Subscribe to selection changes
        sub = widget.subscribe_selection_changed(on_selection_changed)
        self.assertIsNotNone(sub)

        # Cleanup
        del sub
        del widget
        window.destroy()

    async def test_is_expanded_delegation(self):
        """Test that is_expanded delegates to the underlying tree widget."""
        model, delegate, items = self._create_test_tree()
        root1, _, _ = items

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestIsExpandedDelegation", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Initially not expanded
        self.assertFalse(widget.is_expanded(root1))

        # Expand
        widget.set_expanded(root1, True, False)
        await omni.kit.app.get_app().next_update_async()

        self.assertTrue(widget.is_expanded(root1))

        # Collapse
        widget.set_expanded(root1, False, True)
        await omni.kit.app.get_app().next_update_async()

        self.assertFalse(widget.is_expanded(root1))

        # Cleanup
        del widget
        window.destroy()

    async def test_del_cleanup(self):
        """Test that __del__ properly cleans up resources when object is deleted."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestDelCleanup", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Store a reference to the task to verify it gets cancelled
        task = widget._update_content_size_task  # pylint: disable=protected-access

        # Delete the widget - this triggers __del__
        del widget

        # Force garbage collection to ensure __del__ is called
        gc.collect()

        # Verify task was cancelled (if one existed)
        if task is not None:
            self.assertTrue(task.cancelled() or task.done())

        # Cleanup
        window.destroy()

    async def test_refresh(self):
        """Test that refresh works when alternating rows are enabled."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestAlternatingRowRefresh", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate, alternating_rows=True)

        await omni.kit.app.get_app().next_update_async()

        # Should not raise when called
        widget.refresh()

        # Cleanup
        del widget
        window.destroy()

    async def test_alternating_row_disabled_refresh(self):
        """Test that refresh is a no-op when alternating rows are disabled."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestAlternatingRowRefreshDisabled", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate, alternating_rows=False)

        await omni.kit.app.get_app().next_update_async()

        # Should not raise when called, even though alternating rows are disabled
        result = widget.refresh()
        self.assertIsNone(result)

        # Cleanup
        del widget
        window.destroy()
