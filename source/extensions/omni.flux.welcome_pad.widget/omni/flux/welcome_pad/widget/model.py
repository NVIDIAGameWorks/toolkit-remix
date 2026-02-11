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

from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription

HEADER_DICT = {0: "Pad"}


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, idt=None):
        super().__init__()
        self._idt = idt
        self._title = None
        self._description = None
        self.enabled = True
        self.use_title_override_delegate = False
        self.use_description_override_delegate = False
        self.title_model = ui.SimpleStringModel(self.title)

    @abc.abstractmethod
    def get_image(self) -> str:
        """Image that will be showed on the left"""
        return ""

    def on_mouse_pressed(self):
        """Action that will be called when the item is clicked on"""
        print("Mouse pressed")

    def on_mouse_released(self):
        """Action that will be called when the item is released on"""
        print("Mouse released")

    def on_hovered(self, hovered):
        """Action that will be called when the item is hovered on"""
        print("Mouse hovered")

    def on_description_scrolled_x(self, x):
        """Action that will be called when the description is scrolled on x"""
        print("Description scrolled x")

    def on_description_scrolled_y(self, y):
        """Action that will be called when the description is scrolled on y"""
        print("Description scrolled y")

    @property
    @abc.abstractmethod
    def title(self):
        """Title of the item that will be shown"""
        return "Title " + self._idt

    def title_override_delegate(self) -> ui.Widget:
        """If use_title_override_delegate is True, this function will be executed to draw the title

        Returns:
            The created widget
        """
        return

    @property
    @abc.abstractmethod
    def description(self):
        """Description of the item that will be shown"""
        return (
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt "
            "ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco "
            "laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate "
            "velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, "
            "sunt in culpa qui officia deserunt mollit anim id est laborum." + self._idt
        )

    def description_override_delegate(self):
        """If use_description_override_delegate is True, this function will be executed to draw the description

        Returns:
            The created widget
        """
        return

    def __repr__(self):
        return f'"{self.title}"'


class Model(ui.AbstractItemModel):
    """List model"""

    def __init__(self, create_demo_items: bool = True):
        super().__init__()
        self.__original_items = []
        self.__items = []
        self.__current_limit_list = None
        self.__original_len_data = None
        self.__create_demo_items = create_demo_items

        self.__on_items_enabled = _Event()

        self._refresh_list()

    def _items_enabled(self, items, value):
        """Call the event object that has the list of functions"""
        self.__on_items_enabled(items, value)

    def subscribe_items_enabled(self, callback):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_items_enabled, callback)

    def set_list_limit(self, limit_list: int | None):
        """Set a size limit into the list of items"""
        self.__current_limit_list = limit_list
        self._refresh_list()

    def get_list_limit(self):
        return self.__current_limit_list

    def get_items(self):
        """Get current items"""
        return self.__original_items

    def get_size_data(self):
        """Get the size of the list of items"""
        return self.__original_len_data

    def add_items(self, items: list[Item]):
        """Add items into the list"""
        self.__original_items.extend(items)
        self._refresh_list()

    def set_items(self, items: list[Item]):
        """Set items into the list"""
        self.__original_items = items
        self._refresh_list()

    def enable_items(self, items: list[Item], value):
        """
        Enable/disable items

        Args:
            items: the list of items to set the value to
            value: enable or disable
        """
        for item in items:
            item.enabled = value
        self._item_changed(None)
        self._items_enabled(items, value)

    def remove_items(self, items: list[Item]):
        """Remove items from the list"""
        for item in items:
            if item in self.__original_items:
                self.__original_items.remove(item)
        self._refresh_list()

    def _refresh_list(self):
        """Refresh the list"""
        if not self.__original_items and self.__create_demo_items:
            # demo
            self.__items = [Item(idt) for idt in ["0", "1", "2", "3", "4"]]
        else:
            self.__items = list(self.__original_items)
        self.__original_len_data = len(self.__items)
        if self.__current_limit_list is not None:
            self.__items = self.__items[: self.__current_limit_list]
        self._item_changed(None)

    def get_item_children(self, item):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__items
        return []

    def get_item_value_model_count(self, item):
        """The number of columns"""
        return len(HEADER_DICT.keys())

    def get_item_value_model(self, item, column_id):
        """
        Return value model.
        It's the object that tracks the specific value.
        In our case we use ui.SimpleStringModel.
        """
        if column_id == 0:
            return item.title_model
        return None

    def destroy(self):
        self.__items = []
