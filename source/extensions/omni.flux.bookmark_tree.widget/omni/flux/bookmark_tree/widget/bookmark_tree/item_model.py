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

import re
from enum import Enum
from typing import Any, Callable, List, Optional

from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class ComponentTypes(Enum):
    """The indexes prefixing the names are used to sort by component type."""

    create_collection = "2 - CreateCollection"
    bookmark_collection = "0 - BookmarkCollection"
    bookmark_item = "1 - BookmarkItem"


class ItemBase(ui.AbstractItem):
    """
    Base Item of the model. **This should not be used directly other than for typing, instead use one of the children
    classes**.
    """

    def __init__(self):
        super().__init__()
        self._parent = None
        self._component_type = None
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
    def component_type(self) -> Optional[str]:
        """
        The item's component type.

        Use this attribute to set a "type/category" of your item. This attribute can be used in the delegate as a style
        for the branch icon like: f"TreeViewBranch{item.component_type}".
        """
        return self._component_type

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

    def on_mouse_double_clicked(self) -> None:
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
            self._children.sort(key=lambda i: (i.title, i.component_type))

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
            self._children.sort(key=lambda i: (i.title, i.component_type))

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
        return f'"{self.title} {self.component_type}"'


class CreateBookmarkItem(ItemBase):
    """An item that is used to create new bookmark collections. This looks like a 'Create a new bookmark...' button"""

    def __init__(self, on_mouse_clicked_callback: Callable = None):
        super().__init__()
        self._title = "Create a new bookmark..."
        self._on_mouse_clicked_callback = on_mouse_clicked_callback
        self._component_type = ComponentTypes.create_collection.value
        self._can_have_children = False

    def on_mouse_clicked(self):
        """Callback for when the mouse is clicked on the item"""
        self._on_mouse_clicked_callback()


class BookmarkCollectionItem(ItemBase):
    """
    A collection item can hold other collections or some BookmarkItems
    """

    def __init__(
        self,
        title: str,
        data=None,
        children: List[ItemBase] = None,
        on_mouse_double_clicked_callback: Callable = None,
    ):
        super().__init__()
        self._title = title
        self._data = data
        self._on_mouse_double_clicked_callback = on_mouse_double_clicked_callback
        self._component_type = ComponentTypes.bookmark_collection.value
        self._can_have_children = True

        if children is not None:
            self.set_children(children)

    def on_mouse_double_clicked(self):
        """Callback for when the mouse is double-clicked on the item"""
        self._on_mouse_double_clicked_callback(self)


class BookmarkItem(ItemBase):
    """A bookmark item is held inside a BookmarkCollectionItem"""

    def __init__(self, title: str, data=None, on_mouse_double_clicked_callback: Callable = None):
        super().__init__()
        self._title = title
        self._data = data
        self._on_mouse_double_clicked_callback = on_mouse_double_clicked_callback
        self._component_type = ComponentTypes.bookmark_item.value
        self._can_have_children = False


class TemporaryBookmarkModel(ui.AbstractValueModel):
    def __init__(self, placeholder: str):
        self._default_attr = {
            "_placeholder": None,
            "_value": None,
            "_is_valid": None,
            "_sub_values_changed_fn": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        super().__init__()
        self._placeholder = placeholder
        self._value = self._placeholder
        self._is_valid = True
        self._sub_values_changed_fn = self.subscribe_value_changed_fn(self._on_value_changed_callback)

        self.__on_value_changed_callback = _Event()

    @property
    def is_valid(self) -> bool:
        return self._is_valid

    def set_value(self, value: str) -> None:
        self._value = value
        self._value_changed()

    def get_value_as_string(self) -> str:
        return self._value if self._value and self._value.strip() else self._placeholder

    def _on_value_changed_callback(self, _=None):
        valid = len(self._value.strip()) > 0 and re.search("(?!^\\d+)^\\w+$", self._value) is not None
        if valid != self._is_valid:
            self._is_valid = valid
            self.__on_value_changed_callback(valid)

    def subscribe_on_value_changed_callback(self, function):
        """
        Subscribe to the *on_value_changed_callback* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_value_changed_callback, function)

    def destroy(self):
        _reset_default_attrs(self)
