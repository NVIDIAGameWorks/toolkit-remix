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
from typing import Any

from omni.flux.utils.widget.tree_widget import TreeItemBase as _TreeItemBase


class ItemBase(_TreeItemBase):
    """
    Base Item of the model. **This should not be used directly other than for typing, instead use one of the children
    classes**.
    """

    def __init__(self):
        super().__init__()
        self._title = None
        self._data = None
        self._enabled = True
        self._can_have_children = True

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_title": None,
                "_data": None,
                "_enabled": None,
                "_can_have_children": None,
            }
        )
        return default_attr

    @property
    def enabled(self) -> bool:
        """Whether the item is enabled or not."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    @property
    def title(self) -> str:
        """
        The title is the property that will be displayed in the tree widget

        **The title is assumed to be unique inside the collection. This is true both for the collection title and the
        children item titles**
        """
        return self._title

    @title.setter
    def title(self, value: str):
        self._title = value

    @property
    def data(self) -> Any:
        """Any data that the item needs to carry."""
        return self._data

    @property
    def can_have_children(self) -> bool:
        """
        Define if the item can have children or not.

        Use this attribute to determine whether the item should have an expansion arrow or not in the delegate.
        """
        return self._can_have_children

    def on_mouse_clicked(self) -> None:
        """Should be overridden by the inheriting class."""
        pass

    def on_key_pressed(self, key, pressed) -> None:
        """Should be overridden by the inheriting class."""
        pass

    def set_children(self, children: list["ItemBase"], sort: bool = True) -> None:
        """
        Set an item's children and the children's parent

        Args:
            children: the list of children to set
            sort: whether the children should be sorted
        """
        self.clear_children()
        children = children[:]  # we make copy so that the sort is invisible to devs
        if sort:
            children.sort(key=lambda i: i.title)
        for child in children:
            child.parent = self

    def append_child(self, child: "ItemBase", sort: bool = True) -> None:
        """
        Append a child to the item and set the child's parent

        Args:
            child: the item to append
            sort: whether the children should be sorted after appending the child
        """
        if child.parent == self:
            child.parent = None  # remove it and re add it

        child.parent = self  # simple append
        if not sort:
            return

        children = self.children
        children.sort(key=lambda i: i.title)
        self.clear_children()
        for _child in children:
            _child.parent = self

    def insert_child(self, child: "ItemBase", index: int) -> None:
        """
        Insert a child at a given index in the item's children and set the child's parent

        Args:
            child: the item to insert
            index: the index at which to insert the child
        """
        if child.parent == self:
            child.parent = None  # remove and re add

        children = self.children
        self.clear_children()
        children.insert(index, child)
        for _child in children:
            _child.parent = self

    def remove_child(self, child: "ItemBase") -> None:
        """
        Remove a child from the item's children and reset the child's parent

        Args:
            child: the item to remove
        """
        child.parent = None

    def __repr__(self):
        return self.title


class LayerItem(ItemBase):
    """A layer item is held inside a LayerCollectionItem"""

    def __init__(self, title: str, data: dict = None, parent: ItemBase = None, children: list[ItemBase] = None):
        super().__init__()
        self._title = title
        self.parent = parent
        self._data = data or {"locked": False, "visible": True, "savable": True}
        self._can_have_children = True

        if children is not None:
            self.set_children(children, False)

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_title": None,
                "_data": None,
                "_can_have_children": None,
            }
        )
        return default_attr
