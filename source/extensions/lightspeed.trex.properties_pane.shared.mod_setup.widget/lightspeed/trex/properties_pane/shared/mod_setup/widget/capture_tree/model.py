"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import List, Tuple

import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

HEADER_DICT = {0: "Path"}


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, path, image):
        super().__init__()
        self.path = path
        self.image = image
        self.path_model = ui.SimpleStringModel(self.path)

    def __repr__(self):
        return f'"{self.path}"'


class ListModel(ui.AbstractItemModel):
    """List model of actions"""

    def __init__(self):
        super().__init__()
        self.default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self.__children = []

    def refresh(self, paths: List[Tuple[str, str]]):
        """Refresh the list"""
        self.__children = [Item(path, image) for path, image in sorted(paths, key=lambda x: x[0])]
        self._item_changed(None)

    def get_item_children(self, item):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__children
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
            return item.path_model
        return None

    def destroy(self):
        _reset_default_attrs(self)
