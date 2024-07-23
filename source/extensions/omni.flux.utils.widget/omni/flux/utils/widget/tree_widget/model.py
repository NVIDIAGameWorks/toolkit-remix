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
from typing import TYPE_CHECKING, Iterable

from omni import ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

if TYPE_CHECKING:
    from .item import TreeItemBase as _TreeItemBase


class TreeModelBase(ui.AbstractItemModel):
    def __init__(self):
        """
        A base Model class to be overridden and used with the TreeWidget.
        """
        super().__init__()

        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._items: list["_TreeItemBase"] = []

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return {"_items": None}

    def can_item_have_children(self, item: "_TreeItemBase") -> bool:
        return item.can_have_children

    def iter_items_children(
        self, items: Iterable["_TreeItemBase"] | None = None, recursive=True
    ) -> Iterable["_TreeItemBase"]:
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
