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

import omni.ui as ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription

HEADER_DICT = {0: "Items"}


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, parent: "Item" = None):
        super().__init__()
        self._component_type = None
        self._title = None
        self.parent = parent
        self.selected = False
        self._enabled = True
        self.children_items = []
        self.title_model = ui.SimpleStringModel(self.title)
        self._on_item_enabled = _Event()

    def _item_enabled(self):
        """Call the event object that has the list of functions"""
        self._on_item_enabled(self._enabled)

    def subscribe_item_enabled(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self._on_item_enabled, function)

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value):
        self._enabled = value
        self._item_enabled()

    @property
    @abc.abstractmethod
    def component_type(self) -> str | None:
        """
        The component type. Use this attribute to set a "type/category" of your item.
        This attribute is used in the delegate as a style for the branch icon like:
        f"TreeViewBranch{item.component_type}"
        """
        return

    @abc.abstractmethod
    def can_item_have_children(self, item: "Item") -> bool:
        """
        Define if the item can have children or not

        Args:
            item: the item itself

        Returns:
            If the item can has a children or not
        """
        return True

    @abc.abstractmethod
    def on_mouse_pressed(self):
        """Called when the user click with the left mouse button"""
        print("Mouse pressed")

    @property
    @abc.abstractmethod
    def title(self) -> str:
        """The title that will be showed on the tree"""
        return "Title"

    def __repr__(self):
        return f'"{self.title} {self.component_type}"'


class Model(ui.AbstractItemModel):
    """Basic list model"""

    def __init__(self):
        super().__init__()
        self.__items = []

    def set_items(self, items: list[Item]):
        """Set the items to show"""
        self.__items = items
        self._item_changed(None)

    def get_item_children(self, item: Item | None):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__items
        return item.children_items

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
