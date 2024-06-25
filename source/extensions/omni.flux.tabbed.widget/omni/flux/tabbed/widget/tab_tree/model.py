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

from typing import Any, Callable, List, Optional

import omni.ui as ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription

HEADER_DICT = {0: "Items"}


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, title):
        super().__init__()
        self._title = title
        self.selected = False
        self.title_model = ui.SimpleStringModel(self.title)
        # for each schema, we create a default Pydantic model
        self.__on_mouse_released = _Event()

    def can_item_have_children(self, item: "Item") -> bool:
        """
        Define if the item can have children or not

        Args:
            item: the item itself

        Returns:
            If the item can has a children or not
        """
        return False

    def on_mouse_released(self):
        self.__on_mouse_released(self)

    def subscribe_mouse_released(self, function: Callable[["Item"], Any]):
        """
        Subscribe to the *on_value_changed_callback* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_mouse_released, function)

    @property
    def title(self) -> str:
        """The title that will be showed on the tree"""
        return self._title

    def __repr__(self):
        return self.title


class Model(ui.AbstractItemModel):
    """Basic list model"""

    def __init__(self):
        super().__init__()
        self.__items: List[Item] = []
        self.__sub_mouse_pressed = {}
        self.__sub_mouse_pressed_fn = []

    def _on_item_mouse_released(self, item: Item):
        for _item in self.__items:
            _item.selected = _item == item
        for function in self.__sub_mouse_pressed_fn:
            function(item)

    def add(self, datas: List[str]):
        """Set the items to show"""
        for data in datas:
            item = Item(data)
            self.__items.append(item)
            self.__sub_mouse_pressed[id(item)] = item.subscribe_mouse_released(self._on_item_mouse_released)
        self._item_changed(None)

    def remove(self, datas: List[str]):
        """Set the items to show"""
        to_removes = []
        for data in datas:
            for _data in self.__items:
                if data == _data.title:
                    to_removes.append(_data)
        for to_remove in to_removes:
            self.__items.remove(to_remove)
            if id(to_remove) in self.__sub_mouse_pressed:
                del self.__sub_mouse_pressed[id(to_remove)]
        self._item_changed(None)

    def subscribe_item_mouse_released(self, function: Callable[["Item"], Any]):
        self.__sub_mouse_pressed_fn.append(function)
        for item in self.__items:
            self.__sub_mouse_pressed[id(item)] = item.subscribe_mouse_released(self._on_item_mouse_released)

    def get_item_children(self, item: Optional[Item]):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__items
        return []

    def get_item_value_model_count(self, item: Item):
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
        self.__sub_mouse_pressed = []
