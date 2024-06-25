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

from typing import List

import omni.ui as ui

HEADER_DICT = {0: "Paths"}


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, path):
        super().__init__()
        self._path = path
        self.path_model = ui.SimpleStringModel(self._path)

    @property
    def path(self):
        return self._path

    def __repr__(self):
        return f'"{self._path}"'


class Model(ui.AbstractItemModel):
    """Basic list model"""

    def __init__(self):
        super().__init__()
        self.__items = []

    def set_items(self, items: List[Item]):
        """Set the items to show"""
        self.__items = items
        self._item_changed(None)

    def get_item_children(self, item: Item):
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
            return item.path_model
        return None

    def destroy(self):
        self.__items = []
