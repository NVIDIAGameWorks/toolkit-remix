"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from __future__ import annotations

import abc
import math
from typing import TYPE_CHECKING
from collections.abc import Callable

from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.decorators import limit_recursion as _limit_recursion

from .delegate import AlternatingRowDelegate as _AlternatingRowDelegate
from .model import AlternatingRowModel as _AlternatingRowModel

if TYPE_CHECKING:
    from .delegate import TreeDelegateBase as _TreeDelegateBase
    from .item import TreeItemBase as _TreeItemBase
    from .model import TreeModelBase as _TreeModelBase


class TreeWidget(ui.TreeView):
    def __init__(
        self,
        model: _TreeModelBase,
        delegate: _TreeDelegateBase,
        select_all_children: bool = True,
        validate_action_selection: bool = True,
        **kwargs,
    ):
        """
        A tree widget that extends the built-in ui.TreeView.

        Args:
            model: The tree widget's model
            delegate: The tree widget's delegate
            select_all_children: Whether the tree should select all children items when selecting a parent item or not
            validate_action_selection: Whether the selection should be validated & updated to include the item being
                                       right-clicked on or not
            kwargs: The same arguments ui.TreeView exposes
        """
        super().__init__(model, delegate=delegate, **kwargs)

        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._model = model
        self._delegate = delegate
        self._select_all_children = select_all_children
        self._validate_action_selection = validate_action_selection

        if self._validate_action_selection:
            self._sub_selection_changed = self._delegate.subscribe_item_clicked(self._on_item_clicked)

        self.set_selection_changed_fn(self.on_selection_changed)

        self.__on_selection_changed = _Event()

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return {
            "_model": None,
            "_delegate": None,
            "_select_all_children": None,
            "_sub_selection_changed": None,
            "_validate_action_selection": None,
        }

    def _on_item_clicked(self, should_validate: bool, model: _TreeModelBase, item: _TreeItemBase):
        """
        This makes sure the right-clicked items is in the selection
        """
        if not self._validate_action_selection:
            return

        if should_validate and item not in self.selection:
            to_select = [item]
            if self._select_all_children:
                to_select.extend(model.iter_items_children([item]))
            self.selection = to_select
            self._delegate.selection = to_select

    @_limit_recursion()
    def on_selection_changed(self, items: list[_TreeItemBase]):
        """
        Function to be called whenever the tree widget selection widget changes (`set_selection_changed_fn`).

        The base implementation selects children when selecting a parent if `_select_all_children` is `True`

        Args:
            items: The list of items selected
        """
        if self._select_all_children:
            selection = set(self.selection)
            for item in items:
                selection.update(self._model.iter_items_children([item]))

            selection_list = list(selection)
            self.selection = selection_list
            self._delegate.selection = selection_list

        self.__on_selection_changed(self.selection)

    def subscribe_selection_changed(self, callback: Callable[[list[_TreeItemBase]], None]) -> _EventSubscription:
        return _EventSubscription(self.__on_selection_changed, callback)

    def iter_visible_children(self, items=None, recursive: bool = True):
        """
        Iterate through expanded children of items

        Args:
            items: The collection of items to get children from
            recursive: Whether to get the children recursively or only the direct children
        """
        if items is None:
            # top items are always visible
            items = list(self._model.get_item_children(item=None))
            yield from items
            if not recursive:
                return

        for item in items:
            if self.is_expanded(item):
                for child in self._model.get_item_children(item=item):
                    yield child
                    if recursive:
                        yield from self.iter_visible_children(items=[child], recursive=recursive)

    def visible_descendant_count(self, item: _TreeItemBase) -> int:
        """Count all visible (expanded) descendants of an item."""
        if not self.is_expanded(item) or not item.children:
            return 0

        count = 0
        stack = list(item.children)  # Start with direct children

        while stack:
            child = stack.pop()
            count += 1  # NOTE: This child is visible (parent was expanded)

            # NOTE: If this child is also expanded, add its children to process
            if self.is_expanded(child) and child.children:
                stack.extend(child.children)

        return count

    def destroy(self):
        _reset_default_attrs(self)


class AlternatingRowWidget:
    def __init__(
        self,
        header_height: int,
        row_height: int,
        scrollbar_spacing: bool = True,
        model: _AlternatingRowModel | None = None,
        delegate: _AlternatingRowDelegate | None = None,
    ):
        """
        A tree widget to be layered below another widget to create an alternating row effect.

        Notes:
            When using this widget, make sure to:

            - Sync the frame height to make sure the entire frame is filled with alternating row backgrounds.
                The `computed_content_size_changed_fn` callback of the frame wrapping the foreground tree can be used

            - Sync the scroll position whenever the foreground tree's scroll position changes.
                The `scroll_y_changed_fn` callback of the wrapping scrolling frame can be used to sync the scroll
                position

            - Refresh the widget whenever the number of items in the foreground tree changes.
                The `subscribe_item_changed_fn` callback of the Tree Model can be used to refresh the widget

        Example:
            >>> def _on_content_size_changed(self):
            >>>     self._alternating_row_widget.sync_frame_height(self._tree_widget.computed_height)
            >>>
            >>> def _on_item_changed(self):
            >>>     # Expect self._tree_model.item_count to return the total number of items (recursively) in the model
            >>>     self._alternating_row_widget.refresh(self._tree_model.item_count)
            >>>
            >>> def _build_ui(self):
            >>>     with ui.ZStack():
            >>>         # Build the AlternatingRowWidget
            >>>         self._alternating_row_widget = AlternatingRowWidget(header_height, row_height)
            >>>         # Build the Foreground TreeView wrapped in a ScrollingFrame
            >>>         tree_scroll_frame = ui.ScrollingFrame(
            >>>             computed_content_size_changed_fn=self._on_content_size_changed,
            >>>             scroll_y_changed_fn=self._alternating_row_widget.sync_scrolling_frame,
            >>>         )
            >>>         with tree_scroll_frame:
            >>>             self._tree_model = TreeModel(...)
            >>>             self._tree_delegate = TreeDelegate(...)
            >>>             self._item_changed_sub = self._tree_model.subscribe_item_changed_fn(self._on_item_changed)
            >>>             self._tree_widget = ui.TreeView(
            >>>                 self.tree.model,
            >>>                 delegate=self.tree.delegate,
            >>>             )
        """

        self._default_attr = {
            "_header_height": None,
            "_row_height": None,
            "_model": None,
            "_delegate": None,
            "_scroll_frame": None,
            "_tree": None,
            "_row_count": None,
            "_min_row_count": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._header_height = header_height
        self._row_height = row_height
        self._model = model or _AlternatingRowModel()
        self._delegate = delegate or _AlternatingRowDelegate(row_height, scrollbar_spacing=scrollbar_spacing)

        self._scroll_frame = None
        self._tree = None

        self._row_count = 0
        self._min_row_count = 0

        self._build_ui()

    def _build_ui(self):
        """
        Build the alternating row TreeView UI elements
        """
        self._scroll_frame = ui.ScrollingFrame(
            name="TreePanelBackground",
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
        )
        with self._scroll_frame:
            with ui.VStack():
                ui.Spacer(height=ui.Pixel(self._header_height))
                self._tree = ui.TreeView(
                    self._model,
                    delegate=self._delegate,
                    header_visible=False,
                )

    def sync_frame_height(self, frame_height: float):
        """
        Sync the frame height to make sure the entire frame is filled with alternating row backgrounds.

        Args:
            frame_height: The height of the frame this widget should fill.
        """
        self._min_row_count = math.ceil(frame_height / self._row_height)
        # Expand the tree is the new minimum row count is bigger than the current row count
        if self._row_count < self._min_row_count:
            self.refresh()

    def sync_scrolling_frame(self, position: float):
        """
        Sync the scroll position whenever the foreground tree's scroll position changes.

        Args:
            position: The new scroll position
        """
        self._scroll_frame.scroll_y = position

    def refresh(self, item_count: int = 0):
        """
        Refresh the widget whenever the number of items in the foreground tree changes.

        Args:
            item_count: The number of items in the foreground tree
        """
        self._row_count = max(item_count, self._min_row_count)
        self._model.refresh(self._row_count)

    def destroy(self):
        _reset_default_attrs(self)
