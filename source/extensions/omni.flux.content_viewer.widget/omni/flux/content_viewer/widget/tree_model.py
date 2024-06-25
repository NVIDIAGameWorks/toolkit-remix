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

import typing
from typing import List, Type

if typing.TYPE_CHECKING:
    from .items import BaseContentItem

import omni.ui as ui

HEADER_DICT = {0: "Image", 1: "Title"}


class Model(ui.AbstractItemModel):
    """List model"""

    def __init__(self):
        super().__init__()
        self.__items = []

    def refresh(self, items: List[Type["BaseContentItem"]]):
        """
        Refresh the list with those items

        Args:
            items: the items
        """
        self.__items = items
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
        return None

    def destroy(self):
        for item in self.__items:
            item.destroy()
        self.__items = []
