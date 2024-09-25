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

import omni.ui as ui
from omni.flux.utils.common import Event as _Event


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.value = True
        self.selected = False

    @property
    def nickname(self) -> str:
        return self.path

    def __repr__(self):
        return f'"{self.path}"'


class Model(ui.AbstractItemModel):
    """Model for TreeView"""

    def __init__(self):
        super().__init__()
        self.__children = []
        self.__on_items_selected_changed = _Event()

    def refresh(self):
        """Refresh the list"""
        self.__children = []
        self._item_changed(None)

    def get_item_children(self, item):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__children
        return []

    def add_item(self, item):
        self.__children.append(Item(item))

    def get_item_value_model_count(self, item):
        """The number of columns"""
        return 1

    def _items_selected_changed(self):
        """Call the event object that has the list of functions"""
        self.__on_items_selected_changed()

    def set_items_selected(self, items: list[Item]):
        """
        Select the items from the tree

        Args:
            items: the items to select
        """
        for item in self.__children:
            item.selected = item in items
        self._items_selected_changed()

    def get_selected_items(self):
        """Returns the selected items from the tree"""
        return [item for item in self.__children if item.selected is True]
