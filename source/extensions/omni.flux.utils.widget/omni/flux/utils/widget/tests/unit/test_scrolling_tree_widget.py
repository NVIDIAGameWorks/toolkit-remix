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
import asyncio
import gc
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import omni.kit.app
from omni import ui
from omni.flux.utils.widget.scrolling_tree_view import ScrollingTreeWidget
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows

from .test_tree_widget.helper import MockTreeDelegate, MockTreeItem, MockTreeModel


class _KeepAliveTreeWidget:
    """Track keep-alive access without constructing an Omni UI TreeView."""

    def __init__(self, keep_alive: bool):
        self._keep_alive = keep_alive
        self._destroyed = False
        self.values = []

    @property
    def keep_alive(self) -> bool:
        """Return the current keep-alive value."""
        if self._destroyed:
            raise AssertionError("Destroyed TreeView was accessed")
        return self._keep_alive

    @keep_alive.setter
    def keep_alive(self, value: bool):
        """Record a new keep-alive value."""
        if self._destroyed:
            raise AssertionError("Destroyed TreeView was accessed")
        self._keep_alive = value
        self.values.append(value)

    def destroy(self):
        """Mark the fake TreeView as destroyed."""
        self._destroyed = True


class _ObservedFuture(asyncio.Future):
    """Expose when synchronization code starts waiting for a test future."""

    def __init__(self):
        super().__init__()
        self.waited = asyncio.Event()

    def add_done_callback(self, callback, *, context=None):
        """Record that a task started waiting before registering its callback."""
        self.waited.set()
        return super().add_done_callback(callback, context=context)


def _make_keep_alive_owner(tree_widget: _KeepAliveTreeWidget):
    """Create the minimum scrolling-widget state needed by the context manager."""
    return SimpleNamespace(
        _tree_widget=tree_widget,
        _destroyed=False,
        _keep_alive_disable_lock=asyncio.Lock(),
    )


class TestScrollingTreeWidget(AsyncTestCase):
    """Tests for the ScrollingTreeWidget class."""

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

    async def test_destroy_releases_tasks_subscriptions_and_owned_widgets(self):
        """Explicit destruction releases resources without waiting for garbage collection."""
        # Arrange
        model, delegate, _ = self._create_test_tree()
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestScrollingTreeWidgetDestroy", height=400, width=400)
        with window.frame:
            widget = ScrollingTreeWidget(model, delegate, alternating_rows=True)
        tasks = [MagicMock(), MagicMock(), MagicMock()]
        widget._update_content_size_task, widget._selection_update_task, widget._model_change_sync_task = tasks
        tree_widget = widget._tree_widget
        alternating_rows = widget._alternating_row_widget

        # Act
        with (
            patch.object(tree_widget, "destroy", wraps=tree_widget.destroy) as tree_destroy,
            patch.object(alternating_rows, "destroy", wraps=alternating_rows.destroy) as rows_destroy,
        ):
            widget.destroy()

        # Assert
        for task in tasks:
            task.cancel.assert_called_once_with()
        tree_destroy.assert_called_once_with()
        rows_destroy.assert_called_once_with()
        self.assertIsNone(widget._app_window_size_changed_sub)
        self.assertIsNone(widget._item_changed_sub)
        self.assertIsNone(widget._item_expanded_sub)
        self.assertIsNone(widget._tree_widget)
        self.assertIsNone(widget._alternating_row_widget)
        window.destroy()

    async def test_iter_visible_items_top_level_only(self):
        """Test iter_visible_items returns only top-level items when nothing is expanded."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestIterVisibleItems", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await ui_test.human_delay()

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

        await ui_test.human_delay()

        # Expand Root1
        widget.set_expanded(root1, True, False)
        await ui_test.human_delay()

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

        await ui_test.human_delay()

        # Expand Root1 and Child1_1
        widget.set_expanded(root1, True, False)
        widget.set_expanded(child1_1, True, False)
        await ui_test.human_delay()

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

        await ui_test.human_delay()

        # Expand Root1 - but with recursive=False, we should only get top-level
        widget.set_expanded(root1, True, False)
        await ui_test.human_delay()

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

        await ui_test.human_delay()

        # Set selection
        widget.selection = [root1, root2]
        await ui_test.human_delay()
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

        await ui_test.human_delay()

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

        await ui_test.human_delay()

        # Initially not expanded
        self.assertFalse(widget.is_expanded(root1))

        # Expand
        widget.set_expanded(root1, True, False)
        await ui_test.human_delay()

        self.assertTrue(widget.is_expanded(root1))

        # Collapse
        widget.set_expanded(root1, False, True)
        await ui_test.human_delay()

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

        await ui_test.human_delay()

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

    async def test_model_change_no_error_when_alternating_rows_disabled(self):
        """Test that model changes don't cause errors when alternating rows are disabled."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestModelChangeNoAlternatingRows", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate, alternating_rows=False)

        await ui_test.human_delay()

        # Trigger model change - should not raise even without alternating rows
        model._item_changed(None)  # pylint: disable=protected-access

        await ui_test.human_delay()

        # Widget should still be functional
        self.assertIsNone(widget._alternating_row_widget)  # pylint: disable=protected-access

        # Cleanup
        del widget
        window.destroy()

    async def test_frame_selection_disabled_by_default(self):
        """Test that frame_selection defaults to False."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestFrameSelectionDefault", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        self.assertFalse(widget._frame_selection)  # pylint: disable=protected-access

        # Cleanup
        del widget
        window.destroy()

    async def test_frame_selection_enabled(self):
        """Test that frame_selection can be enabled on creation."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestFrameSelectionEnabled", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate, frame_selection=True)

        self.assertTrue(widget._frame_selection)  # pylint: disable=protected-access

        # Cleanup
        del widget
        window.destroy()

    async def test_selection_setter_triggers_scroll_when_frame_selection_enabled(self):
        """Test that setting selection auto-scrolls when frame_selection is True."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        child1_1 = root1.children[0]
        grandchild = child1_1.children[0]  # Deeply nested item

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSelectionAutoScroll", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate, frame_selection=True, select_all_children=False)

        await ui_test.human_delay()

        # Initially nothing is expanded
        self.assertFalse(widget.is_expanded(root1))
        self.assertFalse(widget.is_expanded(child1_1))

        # Set selection to deeply nested item
        widget.selection = [grandchild]

        # Wait for async scroll_to_items to complete
        await ui_test.human_delay(5)

        # Parents should now be expanded to reveal the selected item
        self.assertTrue(widget.is_expanded(root1))
        self.assertTrue(widget.is_expanded(child1_1))

        # Cleanup
        del widget
        window.destroy()

    async def test_selection_setter_does_not_scroll_when_frame_selection_disabled(self):
        """Test that setting selection does NOT auto-scroll when frame_selection is False."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        child1_1 = root1.children[0]
        grandchild = child1_1.children[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSelectionNoAutoScroll", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate, frame_selection=False, select_all_children=False)

        await ui_test.human_delay()
        # Set selection to deeply nested item
        widget.selection = [grandchild]

        # Wait a few frames
        await ui_test.human_delay(5)

        # Parents should NOT be expanded since frame_selection is False
        self.assertFalse(widget.is_expanded(root1))
        self.assertFalse(widget.is_expanded(child1_1))

        # Cleanup
        del widget
        window.destroy()

    async def test_expand_to_items_single_item(self):
        """Test expand_to_items expands parents for a single deeply nested item."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        child1_1 = root1.children[0]
        grandchild = child1_1.children[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestExpandToItemsSingle", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await ui_test.human_delay()

        # Initially nothing expanded
        self.assertFalse(widget.is_expanded(root1))
        self.assertFalse(widget.is_expanded(child1_1))

        # Expand to grandchild
        await widget.expand_to_items([grandchild])

        # Parents should be expanded
        self.assertTrue(widget.is_expanded(root1))
        self.assertTrue(widget.is_expanded(child1_1))

        # Cleanup
        del widget
        window.destroy()

    async def test_expand_to_items_multiple_items_same_branch(self):
        """Test expand_to_items with multiple items in the same branch."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        child1_1 = root1.children[0]
        grandchild1 = child1_1.children[0]
        grandchild2 = child1_1.children[1]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestExpandToItemsSameBranch", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await ui_test.human_delay()

        # Expand to both grandchildren
        await widget.expand_to_items([grandchild1, grandchild2])

        # Shared parents should be expanded
        self.assertTrue(widget.is_expanded(root1))
        self.assertTrue(widget.is_expanded(child1_1))

        # Cleanup
        del widget
        window.destroy()

    async def test_expand_to_items_multiple_items_different_branches(self):
        """Test expand_to_items with items from different branches."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        root2 = items[1]
        child1_1 = root1.children[0]
        child2_1 = root2.children[0]
        grandchild = child1_1.children[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestExpandToItemsDiffBranches", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await ui_test.human_delay()

        # Expand to items from different branches
        await widget.expand_to_items([grandchild, child2_1])

        # Both branches should be expanded
        self.assertTrue(widget.is_expanded(root1))
        self.assertTrue(widget.is_expanded(child1_1))
        self.assertTrue(widget.is_expanded(root2))

        # Cleanup
        del widget
        window.destroy()

    async def test_expand_to_items_empty_list(self):
        """Test expand_to_items handles empty list gracefully."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestExpandToItemsEmpty", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await ui_test.human_delay()

        # Should not raise
        await widget.expand_to_items([])

        # Nothing should be expanded
        self.assertFalse(widget.is_expanded(root1))

        # Cleanup
        del widget
        window.destroy()

    async def test_expand_to_items_top_level_item(self):
        """Test expand_to_items with a top-level item (no parents to expand)."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        root2 = items[1]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestExpandToItemsTopLevel", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await ui_test.human_delay()

        # Expand to a top-level item
        await widget.expand_to_items([root1])

        # Should not expand root1 itself (it has no parent), only parents of items
        # Root1 is not expanded because expand_to_items expands parents, not the item itself
        self.assertFalse(widget.is_expanded(root1))
        self.assertFalse(widget.is_expanded(root2))

        # Cleanup
        del widget
        window.destroy()

    async def test_scroll_to_items_expands_parents_first(self):
        """Test that scroll_to_items calls expand_to_items before scrolling."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        child1_1 = root1.children[0]
        grandchild = child1_1.children[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestScrollToItemsExpandsFirst", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await ui_test.human_delay()

        # Initially collapsed
        self.assertFalse(widget.is_expanded(root1))

        # Scroll to deeply nested item
        await widget.expand_to_items([grandchild])
        await widget.scroll_to_items([grandchild])

        # Parents should be expanded as part of scroll_to_items
        self.assertTrue(widget.is_expanded(root1))
        self.assertTrue(widget.is_expanded(child1_1))

        # Cleanup
        del widget
        window.destroy()

    async def test_scroll_to_items_item_not_in_tree(self):
        """Test scroll_to_items with an item not in the visible tree."""
        model, delegate, _ = self._create_test_tree()
        orphan_item = MockTreeItem("OrphanItem")  # Not part of the tree

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestScrollToItemsOrphan", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate)

        await ui_test.human_delay()

        # Should not raise even though item isn't in tree
        await widget.scroll_to_items([orphan_item])

        # Cleanup
        del widget
        window.destroy()

    async def test_set_expanded_updates_cache_when_caching_enabled(self):
        """Test that set_expanded automatically updates the expansion cache when expansion_caching is True."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        root2 = items[1]
        child1_1 = root1.children[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSetExpandedUpdatesCache", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate, expansion_caching=True)

        await ui_test.human_delay()

        widget.set_expanded(root1, True, False)
        widget.set_expanded(child1_1, True, False)
        await ui_test.human_delay()

        cache = widget._item_expansion_states  # pylint: disable=protected-access
        self.assertIn(hash(root1), cache)
        self.assertIn(hash(child1_1), cache)
        self.assertNotIn(hash(root2), cache)

        # Collapsing should remove from cache
        widget.set_expanded(root1, False, False)
        self.assertNotIn(hash(root1), cache)
        self.assertIn(hash(child1_1), cache)

        # Cleanup
        del widget
        window.destroy()

    async def test_set_expanded_does_not_update_cache_when_caching_disabled(self):
        """Test that set_expanded does NOT populate the cache when expansion_caching is False."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSetExpandedNoCaching", height=400, width=400)

        with window.frame:
            widget = ScrollingTreeWidget(model, delegate, expansion_caching=False)

        await ui_test.human_delay()

        widget.set_expanded(root1, True, False)
        await ui_test.human_delay()

        cache = widget._item_expansion_states  # pylint: disable=protected-access
        self.assertEqual(len(cache), 0)

        # Cleanup
        del widget
        window.destroy()

    async def test_wait_for_model_change_sync_when_sync_is_replaced_waits_for_replacement(self):
        """Follow synchronization work replaced while a caller is waiting."""
        # Arrange
        initial_sync = _ObservedFuture()
        replacement_sync = _ObservedFuture()
        widget = SimpleNamespace(_model_change_sync_task=initial_sync)

        # Act
        async with asyncio.TaskGroup() as task_group:
            waiter = task_group.create_task(ScrollingTreeWidget.wait_for_model_change_sync(widget))
            await initial_sync.waited.wait()
            initial_sync.cancel()
            widget._model_change_sync_task = replacement_sync
            await asyncio.wait_for(replacement_sync.waited.wait(), timeout=1)
            waited_for_replacement = not waiter.done()
            replacement_sync.set_result(None)

        # Assert
        self.assertTrue(waited_for_replacement)

    async def test_wait_for_model_change_sync_when_caller_is_cancelled_keeps_sync_running(self):
        """Propagate caller cancellation without cancelling widget synchronization."""
        # Arrange
        sync = _ObservedFuture()
        widget = SimpleNamespace(_model_change_sync_task=sync)

        # Act
        async with asyncio.TaskGroup() as task_group:
            waiter = task_group.create_task(ScrollingTreeWidget.wait_for_model_change_sync(widget))
            await sync.waited.wait()
            waiter.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiter
            synchronization_cancelled = sync.cancelled()
            if not sync.done():
                sync.set_result(None)

        # Assert
        self.assertFalse(synchronization_cancelled)

    async def test_model_change_sync_item_notification_when_global_sync_is_pending_keeps_existing_work(self):
        """Keep an unfinished global synchronization when an item notification follows it."""
        # Arrange
        pending_sync = asyncio.Future()
        replacement_sync = asyncio.Future()
        widget = SimpleNamespace(
            _destroyed=False,
            _suppress_model_change_sync=False,
            _model_change_sync_task=pending_sync,
            _sync_ui_after_model_change=lambda **_: object(),
        )

        # Act
        with patch("omni.flux.utils.widget.scrolling_tree_view.ensure_future", return_value=replacement_sync):
            ScrollingTreeWidget._on_model_item_changed(widget, None, MockTreeItem("Changed"))

        # Assert
        self.assertIs(pending_sync, widget._model_change_sync_task)
        self.assertFalse(pending_sync.cancelled())

    async def test_model_change_sync_global_notification_when_work_is_pending_replaces_existing_work(self):
        """Replace unfinished synchronization work when a newer global notification arrives."""
        # Arrange
        pending_sync = asyncio.Future()
        replacement_sync = asyncio.Future()
        restore_expansion_requests = []

        def _sync_ui_after_model_change(restore_expansion=True):
            restore_expansion_requests.append(restore_expansion)
            return object()

        widget = SimpleNamespace(
            _destroyed=False,
            _suppress_model_change_sync=False,
            _model_change_sync_task=pending_sync,
            _sync_ui_after_model_change=_sync_ui_after_model_change,
        )

        # Act
        with patch("omni.flux.utils.widget.scrolling_tree_view.ensure_future", return_value=replacement_sync):
            ScrollingTreeWidget._on_model_item_changed(widget, None, None)

        # Assert
        self.assertTrue(pending_sync.cancelled())
        self.assertIs(replacement_sync, widget._model_change_sync_task)
        self.assertEqual([True], restore_expansion_requests)

    def test_destroy_clears_owned_ui_without_destroying_external_objects(self):
        """Destroy wrapper-owned UI without destroying the supplied model or delegate."""
        # Arrange
        root_frame = Mock()
        tree_widget = Mock()
        alternating_row_widget = Mock()
        model = Mock()
        delegate = Mock()
        widget = SimpleNamespace(
            _destroyed=False,
            _expansion_resolve_cancel_event=None,
            _update_content_size_task=None,
            _selection_update_task=None,
            _model_change_sync_task=None,
            _app_window_size_changed_sub=None,
            _item_changed_sub=None,
            _item_expanded_sub=None,
            _root_frame=root_frame,
            _tree_widget=tree_widget,
            _tree_frame=Mock(),
            _tree_scroll_frame=Mock(),
            _alternating_row_widget=alternating_row_widget,
            _model=model,
            _delegate=delegate,
        )

        # Act
        ScrollingTreeWidget.destroy(widget)

        # Assert
        root_frame.clear.assert_called_once_with()
        alternating_row_widget.destroy.assert_called_once_with()
        tree_widget.destroy.assert_called_once_with()
        model.destroy.assert_not_called()
        delegate.destroy.assert_not_called()
        self.assertIsNone(widget._tree_widget)
        self.assertIsNone(widget._tree_frame)
        self.assertIsNone(widget._tree_scroll_frame)
        self.assertIsNone(widget._root_frame)
        self.assertIsNone(widget._alternating_row_widget)
        self.assertIsNone(widget._model)
        self.assertIsNone(widget._delegate)

    def test_resolve_expansion_plan_restores_duplicate_paths_and_ancestors(self):
        """Path fallback restores every duplicate visible row and its ancestors in root-first order."""
        # Arrange
        child_a = MockTreeItem("ChildA")
        child_b = MockTreeItem("ChildB")
        root_a = MockTreeItem("RootA", children=[child_a])
        root_b = MockTreeItem("RootB", children=[child_b])
        previous_hash = 1234

        # Act
        recursive_items, ordered_items, cache_state = ScrollingTreeWidget._resolve_expansion_plan(
            expansion_state_by_hash={previous_hash: True},
            previous_path_by_hash={previous_hash: "/World/Shared"},
            item_by_hash={hash(item): item for item in (root_a, child_a, root_b, child_b)},
            items_by_path={"/World/Shared": [child_a, child_b]},
            root_items=[root_a, root_b],
            expand_filtered_roots=True,
            cancel_event=threading.Event(),
        )

        # Assert
        self.assertEqual([root_a, root_b], recursive_items)
        self.assertEqual([root_a, child_a, root_b, child_b], ordered_items)
        self.assertEqual(dict.fromkeys(map(hash, ordered_items), True), cache_state)

    async def test_refresh_model_when_superseded_during_commit_keeps_generation_consistent(self):
        """Serialize model publication and expansion state across overlapping refreshes."""
        # Arrange
        old_root = MockTreeItem("Old")
        root_a = MockTreeItem("A")
        root_b = MockTreeItem("B")
        path = "/Group"

        def _result(root):
            return SimpleNamespace(
                root_items=[root],
                item_by_hash={hash(root): root},
                items_by_path={path: [root]},
                path_by_hash={hash(root): path},
            )

        result_a = _result(root_a)
        result_b = _result(root_b)
        results = iter((result_a, result_b))

        async def _refresh_threaded():
            return next(results)

        model = SimpleNamespace(root_items=[old_root], refresh_threaded=_refresh_threaded)

        def _publish_refresh_result(result):
            model.root_items = result.root_items

        model.publish_refresh_result = _publish_refresh_result

        first_commit_waiting = asyncio.Event()
        release_first_commit = asyncio.Event()
        update_count = 0

        async def _next_update_async():
            nonlocal update_count
            update_count += 1
            if update_count == 1:
                first_commit_waiting.set()
                await release_first_commit.wait()

        tree_widget = Mock()
        tree_widget.selection = []
        tree_widget.is_expanded.return_value = False
        widget = object.__new__(ScrollingTreeWidget)
        widget._model = model
        widget._tree_widget = tree_widget
        widget._tree_frame = None
        widget._tree_scroll_frame = None
        widget._root_frame = None
        widget._alternating_rows = False
        widget._alternating_row_widget = None
        widget._update_content_size_task = None
        widget._selection_update_task = None
        widget._model_change_sync_task = None
        widget._app_window_size_changed_sub = None
        widget._item_changed_sub = None
        widget._item_expanded_sub = None
        widget._destroyed = False
        widget._expansion_caching = True
        widget._item_expansion_states = {hash(old_root): True}
        widget._item_paths_by_hash = {hash(old_root): path}
        widget._expansion_resolve_cancel_event = None
        widget._refresh_commit_lock = asyncio.Lock()
        kit_app = SimpleNamespace(next_update_async=_next_update_async)
        real_get_app = omni.kit.app.get_app
        existing_tasks = set(asyncio.all_tasks())
        second_commit_started = asyncio.Event()
        commit_states = []

        def _get_app_for_current_task():
            return real_get_app() if asyncio.current_task() in existing_tasks else kit_app

        async def _commit_refresh_result(self, model, result, expansion_plan, cancel_event):
            if result is result_b:
                second_commit_started.set()
            committed = await ScrollingTreeWidget._commit_refresh_result(
                self, model, result, expansion_plan, cancel_event
            )
            if committed:
                commit_states.append(
                    (
                        result,
                        model.root_items,
                        self._item_paths_by_hash,
                        dict(self._item_expansion_states),
                    )
                )
            return committed

        widget._commit_refresh_result = _commit_refresh_result.__get__(widget, ScrollingTreeWidget)

        # Act
        with patch(
            "omni.flux.utils.widget.scrolling_tree_view.omni.kit.app.get_app",
            side_effect=_get_app_for_current_task,
        ):
            async with asyncio.TaskGroup() as task_group:
                try:
                    task_group.create_task(widget.refresh_model())
                    await first_commit_waiting.wait()
                    task_group.create_task(widget.refresh_model())
                    await second_commit_started.wait()

                    release_first_commit.set()
                finally:
                    release_first_commit.set()

        # Assert
        self.assertEqual(
            [
                (result_a, [root_a], result_a.path_by_hash, {hash(root_a): True}),
                (result_b, [root_b], result_b.path_by_hash, {hash(root_b): True}),
            ],
            commit_states,
        )

    async def test_keep_alive_disabled_when_context_exits_restores_after_one_update(self):
        # Arrange
        tree_widget = _KeepAliveTreeWidget(keep_alive=True)
        widget = _make_keep_alive_owner(tree_widget)
        values_during_update = []

        async def _next_update():
            values_during_update.append(tree_widget.keep_alive)

        kit_app = SimpleNamespace(next_update_async=AsyncMock(side_effect=_next_update))

        # Act
        with patch("omni.flux.utils.widget.scrolling_tree_view.omni.kit.app.get_app", return_value=kit_app):
            async with ScrollingTreeWidget.keep_alive_disabled(widget):
                keep_alive_inside = tree_widget.keep_alive

        # Assert
        self.assertFalse(keep_alive_inside)
        self.assertTrue(tree_widget.keep_alive)
        self.assertEqual([False, True], tree_widget.values)
        self.assertEqual([False], values_during_update)
        kit_app.next_update_async.assert_awaited_once_with()

    async def test_keep_alive_disabled_when_body_raises_restores_value(self):
        # Arrange
        tree_widget = _KeepAliveTreeWidget(keep_alive=True)
        widget = _make_keep_alive_owner(tree_widget)
        kit_app = SimpleNamespace(next_update_async=AsyncMock())

        # Act
        with (
            patch("omni.flux.utils.widget.scrolling_tree_view.omni.kit.app.get_app", return_value=kit_app),
            self.assertRaisesRegex(RuntimeError, "test failure"),
        ):
            async with ScrollingTreeWidget.keep_alive_disabled(widget):
                raise RuntimeError("test failure")

        # Assert
        self.assertTrue(tree_widget.keep_alive)
        self.assertEqual([False, True], tree_widget.values)

    async def test_keep_alive_disabled_when_frame_wait_is_cancelled_restores_value(self):
        # Arrange
        tree_widget = _KeepAliveTreeWidget(keep_alive=True)
        widget = _make_keep_alive_owner(tree_widget)
        frame_started = asyncio.Event()
        release_frame = asyncio.Event()

        async def _next_update():
            frame_started.set()
            await release_frame.wait()

        kit_app = SimpleNamespace(next_update_async=AsyncMock(side_effect=_next_update))

        async def _use_context():
            async with ScrollingTreeWidget.keep_alive_disabled(widget):
                pass

        # Act
        with patch("omni.flux.utils.widget.scrolling_tree_view.omni.kit.app.get_app", return_value=kit_app):
            task = asyncio.create_task(_use_context())
            try:
                await frame_started.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                release_frame.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        # Assert
        self.assertTrue(tree_widget.keep_alive)
        self.assertEqual([False, True], tree_widget.values)

    async def test_keep_alive_disabled_when_widget_is_destroyed_does_not_access_tree_view(self):
        # Arrange
        tree_widget = _KeepAliveTreeWidget(keep_alive=True)
        widget = _make_keep_alive_owner(tree_widget)
        kit_app = SimpleNamespace(next_update_async=AsyncMock())

        # Act
        with patch("omni.flux.utils.widget.scrolling_tree_view.omni.kit.app.get_app", return_value=kit_app):
            async with ScrollingTreeWidget.keep_alive_disabled(widget):
                widget._destroyed = True
                tree_widget.destroy()

        # Assert
        self.assertEqual([False], tree_widget.values)
        kit_app.next_update_async.assert_awaited_once_with()

    async def test_keep_alive_disabled_when_already_disabled_does_not_wait_for_update(self):
        # Arrange
        tree_widget = _KeepAliveTreeWidget(keep_alive=False)
        widget = _make_keep_alive_owner(tree_widget)
        kit_app = SimpleNamespace(next_update_async=AsyncMock())

        # Act
        with patch("omni.flux.utils.widget.scrolling_tree_view.omni.kit.app.get_app", return_value=kit_app):
            async with ScrollingTreeWidget.keep_alive_disabled(widget):
                keep_alive_while_disabled = tree_widget.keep_alive

        # Assert
        self.assertFalse(keep_alive_while_disabled)
        self.assertEqual([], tree_widget.values)
        kit_app.next_update_async.assert_not_awaited()

    async def test_keep_alive_disabled_when_scopes_overlap_keeps_replacement_disabled(self):
        # Arrange
        tree_widget = _KeepAliveTreeWidget(keep_alive=True)
        widget = _make_keep_alive_owner(tree_widget)
        first_attempted = asyncio.Event()
        first_entered = asyncio.Event()
        first_release = asyncio.Event()
        second_attempted = asyncio.Event()
        second_entered = asyncio.Event()
        second_release = asyncio.Event()
        kit_app = SimpleNamespace(next_update_async=AsyncMock())
        real_get_app = omni.kit.app.get_app
        context_tasks = set()

        def _get_app_for_current_task():
            return kit_app if asyncio.current_task() in context_tasks else real_get_app()

        async def _use_context(attempted: asyncio.Event, entered: asyncio.Event, release: asyncio.Event):
            attempted.set()
            async with ScrollingTreeWidget.keep_alive_disabled(widget):
                entered.set()
                await release.wait()

        # Act
        with patch(
            "omni.flux.utils.widget.scrolling_tree_view.omni.kit.app.get_app",
            side_effect=_get_app_for_current_task,
        ):
            async with asyncio.TaskGroup() as task_group:
                try:
                    first_task = task_group.create_task(_use_context(first_attempted, first_entered, first_release))
                    context_tasks.add(first_task)
                    await first_attempted.wait()
                    await first_entered.wait()
                    second_task = task_group.create_task(_use_context(second_attempted, second_entered, second_release))
                    context_tasks.add(second_task)
                    await second_attempted.wait()
                    first_release.set()
                    await second_entered.wait()
                    keep_alive_during_replacement = tree_widget.keep_alive
                    second_release.set()
                finally:
                    first_release.set()
                    second_release.set()

        # Assert
        self.assertFalse(keep_alive_during_replacement)
        self.assertTrue(tree_widget.keep_alive)
        self.assertEqual([False, True, False, True], tree_widget.values)
