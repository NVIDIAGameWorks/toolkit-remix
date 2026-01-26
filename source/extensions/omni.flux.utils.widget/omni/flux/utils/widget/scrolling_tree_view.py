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

__all__ = ["ScrollingTreeWidget"]

from asyncio import Future, ensure_future
from collections import deque
from typing import Iterable, List

import omni.kit.app
import omni.usd
from carb.events import IEvent
from omni import appwindow, ui
from omni.flux.utils.widget.tree_widget import (
    AlternatingRowWidget,
    TreeDelegateBase,
    TreeItemBase,
    TreeModelBase,
    TreeWidget,
)


class ScrollingTreeWidget:
    """
    A scrollable tree widget with optional alternating row backgrounds.

    This widget wraps TreeWidget with scroll handling, automatic content size
    updates, and optional alternating row visual effects.

    Args:
        model: The tree widget's data model
        delegate: The tree widget's delegate for custom rendering
        alternating_rows: Whether to display alternating row background colors
        header_height: Height of the header row in pixels (default: 28)
        row_height: Height of each data row in pixels (default: 28)
        select_all_children: Whether selecting a parent item also selects all
            its children
        validate_action_selection: Whether to validate and update selection
            to include the right-clicked item
        **kwargs: Additional arguments passed to the underlying ui.TreeView
    """

    def __init__(
        self,
        model: TreeModelBase,
        delegate: TreeDelegateBase,
        alternating_rows: bool = False,
        header_height: int = 28,  # Default: 24px content + 4px spacing (Sane default value)
        row_height: int = 28,  # Default: 24px content + 4px spacing (Sane default value)
        select_all_children: bool = True,
        validate_action_selection: bool = True,
        **kwargs,
    ):
        self._alternating_row_widget: AlternatingRowWidget | None = None
        self._tree_frame: ui.Frame | None = None
        self._tree_scroll_frame: ui.ScrollingFrame | None = None
        self._tree_widget: TreeWidget | None = None

        self._model = model
        self._delegate = delegate

        self._alternating_rows = alternating_rows
        self._select_all_children = select_all_children

        self._header_height = header_height
        self._row_height = row_height
        self._previous_frame_height: float = 1.0

        self._extra_tree_view_args = kwargs

        self._update_content_size_task: Future | None = None
        self._validate_action_selection = validate_action_selection

        self._build_ui()

        # NOTE: this event subscription makes sure that the number of alternating rows always matches
        # the size of the tree view window regardless of the count of visible items on the tree
        # I tried using the tree_frame and scroll frame but the main app window
        # is the required window_resize_event_stream
        self._app_window_size_changed_sub = (
            appwindow.get_default_app_window()
            .get_window_resize_event_stream()
            .create_subscription_to_pop(self._on_window_resized, name="AppWindowResized")
        )

    def _on_window_resized(self, _: IEvent) -> None:
        if not self._tree_widget:
            return
        self._tree_widget.dirty_widgets()

    @property
    def selection(self) -> List[TreeItemBase]:
        """The currently selected items in the tree."""
        return self._tree_widget.selection

    @selection.setter
    def selection(self, items: Iterable[TreeItemBase]):
        self._tree_widget.selection = items

    @property
    def delegate(self) -> TreeDelegateBase:
        """The tree widget's delegate for custom rendering."""
        return self._delegate

    @property
    def model(self) -> TreeModelBase:
        """The tree widget's data model."""
        return self._model

    def _build_ui(self):
        scroll_change_fn = None
        with ui.ZStack():
            if self._alternating_rows:
                self._alternating_row_widget = AlternatingRowWidget(self._header_height, self._row_height)
                scroll_change_fn = self._alternating_row_widget.sync_scrolling_frame

            self._tree_scroll_frame = ui.ScrollingFrame(
                name="TreePanelBackground", scroll_y_changed_fn=scroll_change_fn
            )

            with self._tree_scroll_frame:
                self._tree_frame = ui.ZStack(
                    content_clipping=True,  # Add on top of the background
                    computed_content_size_changed_fn=self._on_content_size_changed,
                )
                with self._tree_frame:
                    self._tree_widget = TreeWidget(
                        self._model,
                        delegate=self._delegate,
                        select_all_children=self._select_all_children,
                        validate_action_selection=self._validate_action_selection,
                        **self._extra_tree_view_args,
                    )

    def _on_content_size_changed(self):
        if self._update_content_size_task:
            self._update_content_size_task.cancel()
        self._update_content_size_task = ensure_future(self._update_content_size_deferred())

    def iter_visible_items(self, recursive=True) -> Iterable[TreeItemBase]:
        """
        Iterate through all currently visible (expanded) items in the tree.

        Yields items in breadth-first order, respecting the expansion state of parent items.
        Only items whose parents are expanded will be yielded.

        Args:
            recursive: If True, recursively yields children of expanded items.
                If False, yields only top-level items.

        Yields:
            TreeItemBase: Each visible item in breadth-first traversal order.

        """
        stack = deque(self._model.get_item_children(item=None))
        if not stack:
            return

        while stack:
            item = stack.popleft()
            yield item
            if recursive and self._tree_widget.is_expanded(item):
                children = list(self._model.get_item_children(item=item))
                # NOTE: Reverse before extendleft() to preserve original order: extendleft([A,B,C])
                # inserts C, then B, then A at the front, yielding [A,B,C,...]. Without reversing,
                # children would appear in reverse order when popped.
                children.reverse()
                stack.extendleft(children)

    async def scroll_to_items(self, items: Iterable[TreeItemBase], center_ratio: float = 0.2):
        """
        Scroll to reveal the first item in `items`.

        Args:
            items: The items to scroll to
            center_ratio: where to frame first item (0.0: top, 0.5: center, 1.0: bottom)
        """
        # TODO: on the next MR, I'll look into putting selection, expansion, and framing on a single async call
        # hopefully this will fix our timing issues and dirty widgets won't be needed.
        self._tree_widget.dirty_widgets()

        # NOTE: Wait exactly 2 frame updates for UI recalculation after dirtying widgets.
        # This "magic number" has been tested and works reliably across
        # different UI scenarios. Adding validation would create unnecessary overhead
        # for what is a deterministic UI update cycle.
        for _ in range(2):
            await omni.kit.app.get_app().next_update_async()

        items_set = set(items)
        for i, child in enumerate(self.iter_visible_items()):
            if child in items_set:
                idx_item = i
                break
        else:
            return

        # Find out how far down the first item's center is
        scroll_y = (idx_item + 0.5) * self._row_height
        # Since that would scroll to the item, subtract some height to center the item
        target_from_top = self._tree_scroll_frame.computed_content_height * center_ratio
        self._tree_scroll_frame.scroll_y = scroll_y - target_from_top

    @omni.usd.handle_exception
    async def _update_content_size_deferred(self):
        """
        Update the scroll position when the content size changes to force the ScrollFrame to resize.
        """
        # Sync the alternating row widget frame height with the tree frame
        if self._alternating_rows and self._alternating_row_widget:
            self._alternating_row_widget.sync_frame_height(self._tree_frame.computed_height)

        # Only update the scroll position when shrinking the frame
        if self._tree_widget.computed_height < self._previous_frame_height:
            # Cache the current scroll position
            previous_scroll_y = self._tree_scroll_frame.scroll_y
            # Scroll to the top of the tree
            self._tree_scroll_frame.scroll_y = 0
            # Wait for the updated widget to be drawn

            await omni.kit.app.get_app().next_update_async()
            # Scroll to the bottom of the tree or the previous scroll position if still valid
            self._tree_scroll_frame.scroll_y = min(previous_scroll_y, self._tree_scroll_frame.scroll_y_max)
        # Cache the current frame height for the next update
        self._previous_frame_height = self._tree_widget.computed_height

    # NOTE: exposing tree_widget method directly
    def refresh(self):
        """
        Refresh the alternating row background widget.

        Automatically updates the row count from the model. Should be called
        when the number of visible items changes to update the alternating
        row pattern. No-op if alternating_rows is disabled.
        """
        if self._alternating_rows and self._alternating_row_widget:
            self._alternating_row_widget.refresh(item_count=self._model.get_children_count())

    def subscribe_selection_changed(self, *args, **kwargs):
        """
        Subscribe to selection change events.

        Args:
            callback: Function called when selection changes, receives
                the list of currently selected items.

        Returns:
            EventSubscription: Subscription handle. Keep a reference to
                maintain the subscription; releasing it unsubscribes.
        """
        return self._tree_widget.subscribe_selection_changed(*args, **kwargs)

    def dirty_widgets(self, *args, **kwargs):
        """
        Mark the tree widget as dirty, forcing a redraw on the next frame.
        """
        return self._tree_widget.dirty_widgets(*args, **kwargs)

    def set_expanded(self, *args, **kwargs):
        """
        Set the expansion state of an item.

        Args:
            item: The tree item to expand or collapse
            expanded: True to expand, False to collapse
            recursive: If True, also applies to all children
        """
        return self._tree_widget.set_expanded(*args, **kwargs)

    def is_expanded(self, *args, **kwargs):
        """
        Check if an item is currently expanded.

        Args:
            item: The tree item to check

        Returns:
            True if the item is expanded, False otherwise.
        """
        return self._tree_widget.is_expanded(*args, **kwargs)

    def __del__(self):
        """Destroy all subwidgets and release resources."""
        if self._update_content_size_task:
            self._update_content_size_task.cancel()

        # Release the subscription - this automatically unsubscribes from the event stream
        self._app_window_size_changed_sub = None
