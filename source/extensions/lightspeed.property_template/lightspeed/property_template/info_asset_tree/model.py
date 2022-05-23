"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
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
