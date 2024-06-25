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

from typing import Any, List, Optional

from omni import ui


class ItemBase(ui.AbstractItem):
    """
    Base Item of the model. **This should not be used directly other than for typing, instead use one of the children
    classes**.
    """

    def __init__(self):
        super().__init__()
        self._parent = None
        self._title = None
        self._data = None
        self._enabled = True
        self._can_have_children = True
        self._children = []

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
    def parent(self) -> Optional["ItemBase"]:
        """The item's parent item. Not every item has a parent."""
        return self._parent

    @parent.setter
    def parent(self, value: "ItemBase"):
        self._parent = value

    @property
    def data(self) -> Any:
        """Any data that the item needs to carry."""
        return self._data

    @property
    def children(self) -> List["ItemBase"]:
        """The item's children"""
        return self._children

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

    def set_children(self, children: List["ItemBase"], sort: bool = True) -> None:
        """
        Set an item's children and the children's parent

        Args:
            children: the list of children to set
            sort: whether the children should be sorted
        """
        for child in children:
            child.parent = self
        self._children = children
        if sort:
            self._children.sort(key=lambda i: i.title)

    def clear_children(self) -> None:
        """Clear all the item's children"""
        self._children.clear()

    def append_child(self, child: "ItemBase", sort: bool = True) -> None:
        """
        Append a child to the item and set the child's parent

        Args:
            child: the item to append
            sort: whether the children should be sorted after appending the child
        """
        child.parent = self
        self._children.append(child)
        if sort:
            self._children.sort(key=lambda i: i.title)

    def insert_child(self, child: "ItemBase", index: int) -> None:
        """
        Insert a child at a given index in the item's children and set the child's parent

        Args:
            child: the item to insert
            index: the index at which to insert the child
        """
        child.parent = self
        self._children.insert(index, child)

    def remove_child(self, child: "ItemBase") -> None:
        """
        Remove a child from the item's children and reset the child's parent

        Args:
            child: the item to remove
        """
        self._children.remove(child)
        child.parent = None

    def __repr__(self):
        return self.title


class LayerItem(ItemBase):
    """A layer item is held inside a LayerCollectionItem"""

    def __init__(self, title: str, data: dict = None, parent: ItemBase = None, children: List[ItemBase] = None):
        super().__init__()
        self._title = title
        self._parent = parent
        self._data = data or {"locked": False, "visible": True, "savable": True}
        self._can_have_children = True

        if children is not None:
            self.set_children(children, False)
