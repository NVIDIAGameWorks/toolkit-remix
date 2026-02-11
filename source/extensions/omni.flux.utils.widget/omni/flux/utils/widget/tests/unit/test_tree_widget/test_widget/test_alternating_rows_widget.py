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

__all__ = ["TestAlternatingRowModel", "TestAlternatingRowWidget"]

import omni.kit.app
import omni.usd
from omni import ui
from omni.flux.utils.widget.tree_widget import AlternatingRowModel, AlternatingRowWidget
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestAlternatingRowWidget(AsyncTestCase):
    """Tests for the AlternatingRowWidget class."""

    async def setUp(self):
        await omni.usd.get_context().new_stage_async()

    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def test_widget_creation(self):
        """Test that AlternatingRowWidget can be created successfully."""
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestAlternatingRowWidgetCreation", height=400, width=400)

        with window.frame:
            widget = AlternatingRowWidget(header_height=32, row_height=24)

        self.assertIsNotNone(widget)
        self.assertIsNotNone(widget._model)  # pylint: disable=protected-access
        self.assertIsNotNone(widget._delegate)  # pylint: disable=protected-access
        self.assertIsNotNone(widget._scroll_frame)  # pylint: disable=protected-access
        self.assertIsNotNone(widget._tree)  # pylint: disable=protected-access
        self.assertEqual(32, widget._header_height)  # pylint: disable=protected-access
        self.assertEqual(24, widget._row_height)  # pylint: disable=protected-access

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_widget_creation_with_custom_model(self):
        """Test that AlternatingRowWidget can be created with a custom model."""
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestAlternatingRowWidgetCustomModel", height=400, width=400)

        custom_model = AlternatingRowModel()

        with window.frame:
            widget = AlternatingRowWidget(header_height=32, row_height=24, model=custom_model)

        self.assertIs(custom_model, widget._model)  # pylint: disable=protected-access

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_refresh_updates_row_count(self):
        """Test that refresh() updates the internal row count."""
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestRefreshUpdatesRowCount", height=400, width=400)

        with window.frame:
            widget = AlternatingRowWidget(header_height=32, row_height=24)

        # Initial row count should be 0
        self.assertEqual(0, widget._row_count)  # pylint: disable=protected-access

        # Refresh with 10 items
        widget.refresh(item_count=10)
        self.assertEqual(10, widget._row_count)  # pylint: disable=protected-access

        # Model should have 10 items
        items = widget._model.get_item_children(None)  # pylint: disable=protected-access
        self.assertEqual(10, len(items))

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_refresh_respects_min_row_count(self):
        """Test that refresh() uses max(item_count, _min_row_count)."""
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestRefreshRespectsMinRowCount", height=400, width=400)

        with window.frame:
            widget = AlternatingRowWidget(header_height=32, row_height=24)

        # Set a minimum row count by calling sync_frame_height
        # With row_height=24 and frame_height=240, min_row_count = ceil(240/24) = 10
        widget.sync_frame_height(240.0)
        self.assertEqual(10, widget._min_row_count)  # pylint: disable=protected-access

        # Refresh with fewer items than min_row_count
        widget.refresh(item_count=5)

        # Row count should be min_row_count (10), not item_count (5)
        self.assertEqual(10, widget._row_count)  # pylint: disable=protected-access
        items = widget._model.get_item_children(None)  # pylint: disable=protected-access
        self.assertEqual(10, len(items))

        # Refresh with more items than min_row_count
        widget.refresh(item_count=15)

        # Row count should be item_count (15), not min_row_count (10)
        self.assertEqual(15, widget._row_count)  # pylint: disable=protected-access
        items = widget._model.get_item_children(None)  # pylint: disable=protected-access
        self.assertEqual(15, len(items))

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_sync_frame_height_calculates_min_rows(self):
        """Test that sync_frame_height() correctly calculates _min_row_count."""
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSyncFrameHeightCalcMinRows", height=400, width=400)

        with window.frame:
            widget = AlternatingRowWidget(header_height=32, row_height=25)

        # Initial min_row_count should be 0
        self.assertEqual(0, widget._min_row_count)  # pylint: disable=protected-access

        # With row_height=25 and frame_height=100, min_row_count = ceil(100/25) = 4
        widget.sync_frame_height(100.0)
        self.assertEqual(4, widget._min_row_count)  # pylint: disable=protected-access

        # With row_height=25 and frame_height=101, min_row_count = ceil(101/25) = 5
        widget.sync_frame_height(101.0)
        self.assertEqual(5, widget._min_row_count)  # pylint: disable=protected-access

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_sync_frame_height_triggers_refresh_when_needed(self):
        """Test that sync_frame_height() triggers refresh when min_row_count increases."""
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSyncFrameHeightTriggersRefresh", height=400, width=400)

        with window.frame:
            widget = AlternatingRowWidget(header_height=32, row_height=20)

        # Set initial row count to 5
        widget.refresh(item_count=5)
        self.assertEqual(5, widget._row_count)  # pylint: disable=protected-access

        # sync_frame_height with a height that requires more rows (200/20 = 10 rows)
        widget.sync_frame_height(200.0)

        # Row count should have been updated to 10 (the new min)
        self.assertEqual(10, widget._row_count)  # pylint: disable=protected-access

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_sync_frame_height_does_not_shrink_rows(self):
        """Test that sync_frame_height() does not reduce row count below current item count."""
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSyncFrameHeightNoShrink", height=400, width=400)

        with window.frame:
            widget = AlternatingRowWidget(header_height=32, row_height=20)

        # Set row count to 15
        widget.refresh(item_count=15)
        self.assertEqual(15, widget._row_count)  # pylint: disable=protected-access

        # sync_frame_height with a smaller height (100/20 = 5 rows)
        widget.sync_frame_height(100.0)

        # Row count should still be 15 (not reduced)
        self.assertEqual(15, widget._row_count)  # pylint: disable=protected-access

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_sync_scrolling_frame(self):
        """Test that sync_scrolling_frame() updates scroll position."""
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSyncScrollingFrame", height=400, width=400)

        with window.frame:
            widget = AlternatingRowWidget(header_height=32, row_height=24)

        await omni.kit.app.get_app().next_update_async()

        # Sync scroll position
        widget.sync_scrolling_frame(50.0)

        # Scroll position should be updated
        self.assertEqual(50.0, widget._scroll_frame.scroll_y)  # pylint: disable=protected-access

        # Cleanup
        widget.destroy()
        window.destroy()

    async def test_destroy_cleanup(self):
        """Test that destroy() properly cleans up resources."""
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestAlternatingRowWidgetDestroy", height=400, width=400)

        with window.frame:
            widget = AlternatingRowWidget(header_height=32, row_height=24)

        await omni.kit.app.get_app().next_update_async()

        # Destroy the widget
        widget.destroy()

        # Check that attributes are reset
        self.assertIsNone(widget._model)  # pylint: disable=protected-access
        self.assertIsNone(widget._delegate)  # pylint: disable=protected-access
        self.assertIsNone(widget._scroll_frame)  # pylint: disable=protected-access
        self.assertIsNone(widget._tree)  # pylint: disable=protected-access
        self.assertIsNone(widget._header_height)  # pylint: disable=protected-access
        self.assertIsNone(widget._row_height)  # pylint: disable=protected-access

        # Cleanup
        window.destroy()

    async def test_alternating_pattern_in_items(self):
        """Test that items have correct alternating pattern."""
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestAlternatingPattern", height=400, width=400)

        with window.frame:
            widget = AlternatingRowWidget(header_height=32, row_height=24)

        # Refresh with some items
        widget.refresh(item_count=6)

        items = widget._model.get_item_children(None)  # pylint: disable=protected-access

        # Check alternating pattern: even indices should be True, odd should be False
        for i, item in enumerate(items):
            expected_alternate = i % 2 == 0
            self.assertEqual(
                expected_alternate,
                item.alternate,
                f"Item {i} should have alternate={expected_alternate}",
            )

        # Cleanup
        widget.destroy()
        window.destroy()


class TestAlternatingRowModel(AsyncTestCase):
    """Tests for the AlternatingRowModel class."""

    async def setUp(self):
        await omni.usd.get_context().new_stage_async()

    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def test_model_creation(self):
        """Test that AlternatingRowModel can be created successfully."""
        model = AlternatingRowModel()

        self.assertIsNotNone(model)
        self.assertEqual([], model._items)  # pylint: disable=protected-access

        # Cleanup
        model.destroy()

    async def test_refresh_creates_items(self):
        """Test that refresh() creates the correct number of items."""
        model = AlternatingRowModel()

        # Refresh with 5 items
        model.refresh(5)

        items = model.get_item_children(None)
        self.assertEqual(5, len(items))

        # Refresh with 10 items
        model.refresh(10)

        items = model.get_item_children(None)
        self.assertEqual(10, len(items))

        # Cleanup
        model.destroy()

    async def test_refresh_with_zero_items(self):
        """Test that refresh(0) creates an empty list."""
        model = AlternatingRowModel()

        model.refresh(0)

        items = model.get_item_children(None)
        self.assertEqual(0, len(items))

        # Cleanup
        model.destroy()

    async def test_get_item_children_root(self):
        """Test that get_item_children(None) returns all items."""
        model = AlternatingRowModel()
        model.refresh(3)

        items = model.get_item_children(None)
        self.assertEqual(3, len(items))

        # Cleanup
        model.destroy()

    async def test_get_item_children_non_root(self):
        """Test that get_item_children(item) returns empty list for any item."""
        model = AlternatingRowModel()
        model.refresh(3)

        items = model.get_item_children(None)

        # Alternating row items have no children
        for item in items:
            children = model.get_item_children(item)
            self.assertEqual([], children)

        # Cleanup
        model.destroy()

    async def test_get_item_value_model_count(self):
        """Test that get_item_value_model_count() returns 1."""
        model = AlternatingRowModel()
        model.refresh(3)

        items = model.get_item_children(None)

        for item in items:
            count = model.get_item_value_model_count(item)
            self.assertEqual(1, count)

        # Cleanup
        model.destroy()

    async def test_destroy_cleanup(self):
        """Test that destroy() properly cleans up resources."""
        model = AlternatingRowModel()
        model.refresh(5)

        model.destroy()

        self.assertIsNone(model._items)  # pylint: disable=protected-access
