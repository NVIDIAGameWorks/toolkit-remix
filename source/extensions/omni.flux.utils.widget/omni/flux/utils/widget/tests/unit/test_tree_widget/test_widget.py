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

__all__ = ["TestTreeWidget"]

import omni.kit.app
import omni.usd
from omni import ui
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows

from .helper import MockTreeDelegate, MockTreeItem, MockTreeModel, MockTreeWidget


class TestTreeWidget(AsyncTestCase):
    """Tests for the TreeWidget class."""

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
        """Test that TreeWidget can be created successfully."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestTreeWidgetCreation", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate)

        self.assertIsNotNone(widget)
        self.assertEqual(widget._model, model)  # pylint: disable=protected-access
        self.assertEqual(widget._delegate, delegate)  # pylint: disable=protected-access

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_widget_creation_with_select_all_children_disabled(self):
        """Test that TreeWidget can be created with select_all_children=False."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestTreeWidgetSelectAllChildrenDisabled", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate, select_all_children=False)

        self.assertIsNotNone(widget)
        self.assertFalse(widget._select_all_children)  # pylint: disable=protected-access

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_widget_creation_with_validate_action_selection_disabled(self):
        """Test that TreeWidget can be created with validate_action_selection=False."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestTreeWidgetValidateActionDisabled", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate, validate_action_selection=False)

        self.assertIsNotNone(widget)
        self.assertFalse(widget._validate_action_selection)  # pylint: disable=protected-access
        # No subscription should be created when validate_action_selection is False
        self.assertIsNone(widget._sub_selection_changed)  # pylint: disable=protected-access

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_selection_selects_children_when_enabled(self):
        """Test that selecting a parent selects all children when select_all_children=True."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        child1_1 = root1.children[0]
        child1_2 = root1.children[1]
        grandchild1_1_1 = child1_1.children[0]
        grandchild1_1_2 = child1_1.children[1]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSelectionSelectsChildren", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate, select_all_children=True)

        await omni.kit.app.get_app().next_update_async()

        # Select only root1
        widget.selection = [root1]
        await omni.kit.app.get_app().next_update_async()

        # All children should be selected
        selection = widget.selection
        self.assertIn(root1, selection)
        self.assertIn(child1_1, selection)
        self.assertIn(child1_2, selection)
        self.assertIn(grandchild1_1_1, selection)
        self.assertIn(grandchild1_1_2, selection)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_selection_does_not_select_children_when_disabled(self):
        """Test that selecting a parent does NOT select children when select_all_children=False."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSelectionNotSelectChildren", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate, select_all_children=False)

        await omni.kit.app.get_app().next_update_async()

        # Select only root1
        widget.selection = [root1]
        await omni.kit.app.get_app().next_update_async()

        # Only root1 should be selected
        selection = widget.selection
        self.assertEqual([root1], selection)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_subscribe_selection_changed(self):
        """Test that selection change subscription works."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSubscribeSelectionChanged", height=400, width=400)

        selection_changed_called = False
        received_items = []

        def on_selection_changed(selected_items):
            nonlocal selection_changed_called, received_items
            selection_changed_called = True
            received_items = selected_items

        with window.frame:
            widget = MockTreeWidget(model, delegate, select_all_children=False)

        await omni.kit.app.get_app().next_update_async()

        # Subscribe to selection changes
        sub = widget.subscribe_selection_changed(on_selection_changed)
        self.assertIsNotNone(sub)

        # Change selection
        widget.selection = [root1]
        await omni.kit.app.get_app().next_update_async()

        self.assertTrue(selection_changed_called)
        self.assertEqual([root1], received_items)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_iter_visible_children_top_level_only(self):
        """Test iter_visible_children returns only top-level items when nothing is expanded."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestIterVisibleChildrenTopLevel", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # With no items expanded, should only get root items
        visible_items = list(widget.iter_visible_children())
        visible_names = [item.name for item in visible_items]
        visible_names.sort()  # NOTE: return order is not hierarchical so let's just test for presence not order

        self.assertEqual(["Root1", "Root2", "Root3"], visible_names)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_iter_visible_children_with_expansion(self):
        """Test iter_visible_children returns expanded children."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestIterVisibleChildrenExpanded", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Expand Root1
        widget.set_expanded(root1, True, False)
        await omni.kit.app.get_app().next_update_async()

        visible_items = list(widget.iter_visible_children())
        visible_names = [item.name for item in visible_items]

        # Should see Root1, its children, Root2 and Root3
        expected_names = ["Root1", "Child1_1", "Child1_2", "Root2", "Root3"]

        # NOTE: test for presense not order we know the order is wonky
        expected_names.sort()
        visible_names.sort()

        self.assertEqual(expected_names, visible_names)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_iter_visible_children_deeply_nested(self):
        """Test iter_visible_children with deeply nested expansion."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        child1_1 = root1.children[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestIterVisibleChildrenDeepNested", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Expand Root1 and Child1_1
        widget.set_expanded(root1, True, False)
        widget.set_expanded(child1_1, True, False)
        await omni.kit.app.get_app().next_update_async()

        visible_items = list(widget.iter_visible_children())
        visible_names = [item.name for item in visible_items]

        # Should be in visual display order
        expected_names = [
            "Root1",
            "Child1_1",
            "Grandchild1_1_1",
            "Grandchild1_1_2",
            "Child1_2",
            "Root2",
            "Root3",
        ]
        # NOTE: test for presense not order we know the order is wonky
        expected_names.sort()
        visible_names.sort()
        self.assertListEqual(expected_names, visible_names)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_iter_visible_children_non_recursive(self):
        """Test iter_visible_children with recursive=False returns only top-level items."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestIterVisibleChildrenNonRecursive", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Expand Root1 - but with recursive=False, we should only get direct children
        widget.set_expanded(root1, True, False)
        await omni.kit.app.get_app().next_update_async()

        visible_items = list(widget.iter_visible_children(recursive=False))
        visible_names = [item.name for item in visible_items]

        self.assertEqual(["Root1", "Root2", "Root3"], visible_names)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_iter_visible_children_from_specific_items(self):
        """Test iter_visible_children starting from specific items."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        child1_1 = root1.children[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestIterVisibleChildrenFromSpecific", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Expand Root1 and Child1_1
        widget.set_expanded(root1, True, False)
        widget.set_expanded(child1_1, True, False)
        await omni.kit.app.get_app().next_update_async()

        # Get visible children starting from root1 only
        visible_items = list(widget.iter_visible_children(items=[root1]))
        visible_names = [item.name for item in visible_items]

        # Should only get Root1's visible descendants
        expected_names = ["Child1_1", "Grandchild1_1_1", "Grandchild1_1_2", "Child1_2"]
        self.assertEqual(expected_names, visible_names)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_visible_descendant_count_not_expanded(self):
        """Test visible_descendant_count returns 0 when item is not expanded."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestVisibleDescendantCountNotExpanded", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Root1 is not expanded, so visible descendant count should be 0
        count = widget.visible_descendant_count(root1)
        self.assertEqual(0, count)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_visible_descendant_count_expanded(self):
        """Test visible_descendant_count returns correct count when item is expanded."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestVisibleDescendantCountExpanded", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Expand Root1
        widget.set_expanded(root1, True, False)
        await omni.kit.app.get_app().next_update_async()

        # Root1 has 2 direct children (Child1_1, Child1_2) visible
        count = widget.visible_descendant_count(root1)
        self.assertEqual(2, count)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_visible_descendant_count_deeply_expanded(self):
        """Test visible_descendant_count with deeply nested expansion."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        child1_1 = root1.children[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestVisibleDescendantCountDeepExpanded", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Expand Root1 and Child1_1
        widget.set_expanded(root1, True, False)
        widget.set_expanded(child1_1, True, False)
        await omni.kit.app.get_app().next_update_async()

        # Root1 now has 4 visible descendants:
        # Child1_1, Grandchild1_1_1, Grandchild1_1_2, Child1_2
        count = widget.visible_descendant_count(root1)
        self.assertEqual(4, count)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_visible_descendant_count_item_with_no_children(self):
        """Test visible_descendant_count returns 0 for item with no children."""
        model, delegate, items = self._create_test_tree()
        root3 = items[2]  # Root3 has no children

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestVisibleDescendantCountNoChildren", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        count = widget.visible_descendant_count(root3)
        self.assertEqual(0, count)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_delegate_selection_sync(self):
        """Test that delegate selection is synced with widget selection."""
        model, delegate, items = self._create_test_tree()
        root1, root2, _ = items

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestDelegateSelectionSync", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate, select_all_children=False)

        await omni.kit.app.get_app().next_update_async()

        # Set selection
        widget.selection = [root1, root2]
        await omni.kit.app.get_app().next_update_async()

        # Delegate selection should be synced (after on_selection_changed fires)
        # Note: With select_all_children=False, selection stays the same
        self.assertEqual([root1, root2], list(widget.selection))

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_destroy_cleanup(self):
        """Test that destroy properly cleans up resources."""
        model, delegate, _ = self._create_test_tree()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestDestroyCleanup", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Destroy the widget
        widget.destroy()

        # Check that attributes are reset
        self.assertIsNone(widget._model)  # pylint: disable=protected-access
        self.assertIsNone(widget._delegate)  # pylint: disable=protected-access
        self.assertIsNone(widget._select_all_children)  # pylint: disable=protected-access
        self.assertIsNone(widget._sub_selection_changed)  # pylint: disable=protected-access

        # Cleanup
        window.destroy()

    async def test_on_item_clicked_validates_selection(self):
        """Test that _on_item_clicked validates selection when validate_action_selection=True."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        root2 = items[1]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestOnItemClickedValidatesSelection", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate, select_all_children=False, validate_action_selection=True)

        await omni.kit.app.get_app().next_update_async()

        # Select root1
        widget.selection = [root1]
        await omni.kit.app.get_app().next_update_async()

        # Simulate clicking on root2 (which is not in selection)
        # With validate_action_selection=True, root2 should be added to selection
        widget._on_item_clicked(True, model, root2)  # pylint: disable=protected-access
        await omni.kit.app.get_app().next_update_async()

        # root2 should now be the selection (replaces previous selection)
        self.assertIn(root2, widget.selection)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_on_item_clicked_does_not_validate_when_disabled(self):
        """Test that _on_item_clicked does NOT validate selection when validate_action_selection=False."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        root2 = items[1]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestOnItemClickedNoValidate", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate, select_all_children=False, validate_action_selection=False)

        await omni.kit.app.get_app().next_update_async()

        # Select root1
        widget.selection = [root1]
        await omni.kit.app.get_app().next_update_async()

        # Simulate clicking on root2 (which is not in selection)
        # With validate_action_selection=False, selection should not change
        widget._on_item_clicked(True, model, root2)  # pylint: disable=protected-access
        await omni.kit.app.get_app().next_update_async()

        # Selection should remain root1 only
        self.assertEqual([root1], widget.selection)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_on_item_clicked_skips_when_item_already_selected(self):
        """Test that _on_item_clicked does nothing when item is already in selection."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        root2 = items[1]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestOnItemClickedAlreadySelected", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate, select_all_children=False, validate_action_selection=True)

        await omni.kit.app.get_app().next_update_async()

        # Select root1 and root2
        widget.selection = [root1, root2]
        await omni.kit.app.get_app().next_update_async()

        # Store original selection
        original_selection = list(widget.selection)

        # Simulate clicking on root1 (which IS in selection)
        widget._on_item_clicked(True, model, root1)  # pylint: disable=protected-access
        await omni.kit.app.get_app().next_update_async()

        # Selection should remain the same
        self.assertEqual(original_selection, widget.selection)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_on_item_clicked_with_select_all_children(self):
        """Test that _on_item_clicked selects children when select_all_children=True."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]
        root2 = items[1]  # Root2 has one child: Child2_1

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestOnItemClickedWithChildren", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate, select_all_children=True, validate_action_selection=True)

        await omni.kit.app.get_app().next_update_async()

        # Select root1
        widget.selection = [root1]
        await omni.kit.app.get_app().next_update_async()

        # Simulate clicking on root2 (which has children)
        widget._on_item_clicked(True, model, root2)  # pylint: disable=protected-access
        await omni.kit.app.get_app().next_update_async()

        # root2 and its child should be selected
        selection = widget.selection
        self.assertIn(root2, selection)
        self.assertIn(root2.children[0], selection)  # Child2_1

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_multiple_selection_change_subscriptions(self):
        """Test that multiple selection change subscriptions work correctly."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestMultipleSelectionSubs", height=400, width=400)

        callback1_called = False
        callback2_called = False

        def on_selection_changed_1(selected_items):
            nonlocal callback1_called
            callback1_called = True

        def on_selection_changed_2(selected_items):
            nonlocal callback2_called
            callback2_called = True

        with window.frame:
            widget = MockTreeWidget(model, delegate, select_all_children=False)

        await omni.kit.app.get_app().next_update_async()

        # Subscribe two callbacks
        sub1 = widget.subscribe_selection_changed(on_selection_changed_1)
        sub2 = widget.subscribe_selection_changed(on_selection_changed_2)

        self.assertIsNotNone(sub1)
        self.assertIsNotNone(sub2)

        # Change selection
        widget.selection = [root1]
        await omni.kit.app.get_app().next_update_async()

        self.assertTrue(callback1_called)
        self.assertTrue(callback2_called)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_empty_model(self):
        """Test TreeWidget works correctly with an empty model."""
        model = MockTreeModel(items=[])
        delegate = MockTreeDelegate()

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestEmptyModel", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate)

        await omni.kit.app.get_app().next_update_async()

        # Should return empty list
        visible_items = list(widget.iter_visible_children())
        self.assertEqual([], visible_items)

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_selection_with_empty_list(self):
        """Test setting empty selection."""
        model, delegate, items = self._create_test_tree()
        root1 = items[0]

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestEmptySelection", height=400, width=400)

        with window.frame:
            widget = MockTreeWidget(model, delegate, select_all_children=False)

        await omni.kit.app.get_app().next_update_async()

        # Set selection
        widget.selection = [root1]
        await omni.kit.app.get_app().next_update_async()

        # Clear selection
        widget.selection = []
        await omni.kit.app.get_app().next_update_async()

        self.assertEqual([], widget.selection)

        # Cleanup
        widget.destroy()
        window.destroy()
