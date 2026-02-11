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

import omni.ui as ui

HEADER_DICT = {0: "Title", 1: "Value"}


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, title, value):
        super().__init__()
        self._title = title
        self._value = value
        self.selected = False
        self.title_model = ui.SimpleStringModel(self.title)
        self.value_model = ui.SimpleStringModel(self.value)

    @property
    def title(self):
        return self._title

    @property
    def value(self):
        return self._value

    def __repr__(self):
        return f'"{self.title}: {self.value}"'


class Model(ui.AbstractItemModel):
    """List model"""

    def __init__(self):
        super().__init__()
        self.__items = []

    @abc.abstractmethod
    def _set_items_from_data(self, items: list[Any]) -> list[Item]:
        """Function to implement for customization"""
        if not items:
            return []
        return [Item("Error", "Code not implemented")]

    def set_items_from_data(self, items: list[Any]):
        """
        Set items

        Args:
            items: the items to set
        """
        self.__items = self._set_items_from_data(items)
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
        if item is None:
            return self.__items
        if column_id == 0:
            return item.title_model
        if column_id == 1:
            return item.value_model
        return None

    def destroy(self):
        self.__items = []
