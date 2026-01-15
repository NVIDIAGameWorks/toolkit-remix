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

import abc
from typing import Generic, Iterable, TypeVar

from omni import ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .item import AlternatingRowItem as _AlternatingRowItem
from .item import TreeItemBase as _TreeItemBase

T = TypeVar("T", bound=_TreeItemBase)


class TreeModelBase(ui.AbstractItemModel, Generic[T]):
    def __init__(self):
        """
        A base Model class to be overridden and used with the TreeWidget.
        """
        super().__init__()

        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._items: list[T] = []

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return {"_items": None}

    def can_item_have_children(self, item: T) -> bool:
        return item and item.can_have_children

    def get_children_count(self, items: Iterable[T] | None = None, recursive=True) -> int:
        """
        Count the number of items in the tree.

        More efficient than len(list(iter_items_children())) as it avoids
        creating intermediate objects.

        Args:
            items: The items to count from. If None, counts from root items.
            recursive: If True, includes all descendants. If False, counts
                only the provided items (or root items if items is None).

        Returns:
            The total number of items.
        """
        if items is None:
            items = self._items

        stack = list(items)
        count = 0
        while stack:
            child = stack.pop()
            count += 1
            if recursive:
                stack.extend(child.children)
        return count

    def iter_items_children(self, items: Iterable[T] | None = None, recursive=True) -> Iterable[T]:
        """
        Iterate through a collection of items' children

        Args:
            items: The collection of items to get children from
            recursive: Whether to get the children recursively or only the direct children
        """
        if items is None:
            yield from self._items
            items = self._items if recursive else []

        for item in items:
            for child in item.children:
                yield child
                if recursive:
                    yield from self.iter_items_children([child], recursive=recursive)

    def destroy(self):
        _reset_default_attrs(self)


class AlternatingRowModel(ui.AbstractItemModel):
    def __init__(self):
        super().__init__()

        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._items = []

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return {"_items": None}

    def refresh(self, item_count: int):
        self._items = [_AlternatingRowItem(i) for i in range(item_count)]
        self._item_changed(None)

    def get_item_children(self, item):
        if item is None:
            return self._items
        return []

    def get_item_value_model_count(self, item):
        return 1

    def destroy(self):
        _reset_default_attrs(self)
