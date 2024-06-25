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
from typing import List

import omni.ui as ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription

HEADER_DICT = {0: "Items"}


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, title: str):
        """
        Item of the tree

        Args:
            title: the name of the item to display
        """
        super().__init__()
        self.title = title
        self.selected = False
        self.title_model = ui.SimpleStringModel(self.title)

    @abc.abstractmethod
    def on_mouse_pressed(self):
        """Called when an item if pressed"""
        pass

    def __repr__(self):
        return f'"{self.title}"'


class Model(ui.AbstractItemModel):
    """Model for the tree"""

    def __init__(self, titles):
        super().__init__()
        if not titles:
            titles = ["Code not implemented"]
        self.__items = [Item(title) for title in titles]
        self.__on_items_selected_changed = _Event()

        self.set_items_selected([self.__items[0]])

    def _items_selected_changed(self):
        """Call the event object that has the list of functions"""
        self.__on_items_selected_changed()

    def subscribe_items_selected_changed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when the selection of the tree change
        """
        return _EventSubscription(self.__on_items_selected_changed, function)

    def set_items_selected(self, items: List[Item]):
        """
        Select the items from the tree

        Args:
            items: the items to select
        """
        for item in self.__items:
            item.selected = item in items
        self._items_selected_changed()

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
        if item is None:
            return self.__items
        if column_id == 0:
            return item.title_model
        return None

    def destroy(self):
        self.__items = []
