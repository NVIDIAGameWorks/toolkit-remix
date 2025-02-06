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

from weakref import proxy

from omni import ui, usd
from omni.flux.custom_tags.core import CustomTagsCore as _CustomTagsCore
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf, Usd

from .items import TagsSelectionItem as _TagsSelectionItem


class TagsSelectionModel(ui.AbstractItemModel):
    def __init__(self, display_assigned_tags: bool = False, context_name: str = ""):
        super().__init__()

        self._default_attr = {
            "_display_assigned_tags": None,
            "_stage": None,
            "_items": None,
            "_widget": None,
            "_core": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._display_assigned_tags = display_assigned_tags
        self._stage = usd.get_context(context_name).get_stage()

        self._items = []
        self._widget = None

        self._core = _CustomTagsCore(context_name=context_name)

        self.__on_items_dropped = _Event()

    def refresh(self, prims: Usd.Prim):
        """
        Refresh the model items, taking in consideration the `display_assigned_tags` flag.

        Available items will not include assigned items, and vice versa.

        Args:
            prims: The list of prims to get the tags for (affects assigned tags fetching)
        """
        all_tags = self._core.get_all_tags()
        assigned_tags = set(all_tags)
        for prim in prims:
            assigned_tags = assigned_tags.intersection(self._core.get_prim_tags(prim))

        if self._display_assigned_tags:
            items = list(assigned_tags)
        else:
            items = list(set(all_tags).difference(assigned_tags))

        self._items = sorted([_TagsSelectionItem(item) for item in items], key=str)
        self._item_changed(None)

    def find_item(self, path: Sdf.Path | str) -> tuple[int | None, _TagsSelectionItem | None]:
        """
        Find an item based on its Prim Path.

        Returns:
            A tuple with the format [index, item] if the item is found or [None, None] otherwise
        """
        for index, item in enumerate(self._items):
            if not isinstance(item, _TagsSelectionItem):
                continue
            if str(item.path) == str(path):
                return index, item
        return None, None

    def insert_item(self, item: ui.AbstractItem, index: int | None = None):
        """
        Insert an item in the tree.

        Args:
            item: The item to insert
            index: Optional index where to insert the item.
                   If None, the items will be sorted after the insertion
        """
        if index is not None:
            # Inserting at -1 doesn't insert at the end so append instead
            if index < 0:
                self._items.append(item)
            else:
                self._items.insert(index, item)
        else:
            self._items.append(item)
            self._items = sorted(self._items, key=str)

        self._item_changed(None)

    def remove_item(self, item: ui.AbstractItem | str):
        """
        Remove an item from the tree.

        Args:
            item: A Tree Item or Prim Path to the item to remove
        """
        if not isinstance(item, ui.AbstractItem):
            _, item = self.find_item(item)

        if not item:
            return

        self._items.remove(item)
        self._item_changed(None)

    def get_item_children(self, item: _TagsSelectionItem | None) -> list[_TagsSelectionItem]:
        return self._items if item is None else []

    def get_item_value_model_count(self, _) -> int:
        return 1

    def get_drag_mime_data(self, item: _TagsSelectionItem) -> str:
        """
        Get the data for the dragged item(s).
        If the widget proxy is set, the widget selection will be used instead of the given item.

        Args:
            item: the item that was dragged

        Returns:
            A newline-separated string of prim paths
        """
        return "\n".join([str(i) for i in self._widget.selection]) if self._widget else str(item)

    def drop_accepted(
        self, _item_target: _TagsSelectionItem | None, item_source: str | _TagsSelectionItem, _drop_location: int = -1
    ) -> bool:
        return True

    def drop(
        self, _item_target: _TagsSelectionItem | None, item_source: str | _TagsSelectionItem, _drop_location: int = -1
    ):
        """
        The callback executed whenever one or more items are dropped on a widget.

        The widget will add the dropped item to the model and emmit the `on_items_dropped`.

        Args:
            _item_target: The item on which the dragged item is dropped
            item_source: The original item that was dragged (could be the mime data)
            _drop_location: The location where the item is dropped
        """
        if isinstance(item_source, str):
            items = item_source.split("\n")
        elif isinstance(item_source, _TagsSelectionItem):
            items = [str(item_source)]
        else:
            return

        # Don't add an already existing item again
        items = list(set(items).difference([str(i) for i in self._items]))

        for item in items:
            self.insert_item(_TagsSelectionItem(Sdf.Path(item)))

        self._on_items_dropped(items)

    def set_widget(self, widget: ui.TreeView):
        """
        Update the widget proxy. Will be used in the `get_drag_mime_data` function to get the current selection.

        Args:
            widget: The TreeView widget to use
        """
        self._widget = proxy(widget)

    def subscribe_items_dropped(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_items_dropped, function)

    def _on_items_dropped(self, paths: list[str]):
        """
        Trigger the "on_item_dropped" event
        """
        self.__on_items_dropped(paths)

    def destroy(self):
        _reset_default_attrs(self)
