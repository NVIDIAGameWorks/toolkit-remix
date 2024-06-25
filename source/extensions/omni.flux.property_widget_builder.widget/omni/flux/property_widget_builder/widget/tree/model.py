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

__all__ = (
    "Item",
    "ItemGroup",
    "Model",
)

import typing
from typing import Any, Dict, Iterable, List, Mapping, Optional

import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .item_model import ItemGroupModel as _ItemGroupModel

if typing.TYPE_CHECKING:
    from .item_model import ItemModel


HEADER_DICT = {0: "Name", 1: "Value"}


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self):
        super().__init__()
        self._name_models = []
        self._value_models = []
        self.children = []

    @property
    def name_models(self) -> List["ItemModel"]:
        """The name model that will be showed on the tree"""
        return self._name_models

    @property
    def value_models(self) -> List["ItemModel"]:
        """The name that will be showed on the tree"""
        return self._value_models

    @property
    def element_count(self) -> int:
        return len(self.value_models)

    def refresh(self):
        for name_model in self.name_models:
            name_model.refresh()
        for value_model in self.value_models:
            value_model.refresh()

    @property
    def read_only(self) -> bool:
        """Whether the item can have values edited or not"""
        return not (self.value_models and not any(x.read_only for x in self.value_models))

    def serialize(self) -> dict:
        return {
            "names": [x.serialize() for x in self.name_models],
            "values": [x.serialize() for x in self.value_models],
        }

    def matches_serialized_data(self, serialized_item: dict):
        if not isinstance(serialized_item, Mapping):
            return False
        if "names" not in serialized_item:
            return False
        if "values" not in serialized_item:
            return False
        if [x.serialize() for x in self.name_models] != serialized_item["names"]:
            return False
        try:
            val_len = len(serialized_item["values"])
        except TypeError:
            return False
        if val_len != len(self.value_models):
            return False
        return True

    def apply_serialized_data(self, serialized_item: dict):
        for value_model, value in zip(self.value_models, serialized_item["values"]):
            value_model.deserialize(value)

    def __repr__(self):
        return f"<{self.__class__.__name__}({repr(''.join(str(x) for x in self._name_models))})"


class ItemGroup(Item):
    """Item of the model"""

    def __init__(self, name):
        super().__init__()
        self._name_models = [_ItemGroupModel(name)]
        self._value_models = []


class Model(ui.AbstractItemModel):
    """Model for the treeview that will show a list of item(s)"""

    def __init__(self):
        super().__init__()
        self._default_attrs = {}
        for attr, value in self.default_attrs.items():
            setattr(self, attr, value)
        self.__items: List[Item] = []

    @property
    def default_attrs(self) -> Dict[str, Any]:
        """Default created class attribute"""
        return {}

    def set_items(self, items: List[Item]):
        """
        Set the items to show

        Args:
            items: the items to show
        """
        self.__items = items
        self.refresh()

    def refresh(self):
        """Refresh everything"""
        for item in self.get_all_items():
            item.refresh()
        self._item_changed(None)

    def get_all_items(self):
        def _get_children(items):
            result = list(items)
            for item in items:
                if item.children:
                    result.extend(_get_children(item.children))
            return result

        return _get_children(self.__items)

    def iter_item_children(self, items: Optional[Iterable[Item]] = None, recursive=True):
        if items is None:
            yield from self.__items
            items = self.__items if recursive else []

        for itm in items:
            for child in itm.children:
                yield child
                if recursive:
                    yield from self.iter_item_children([child], recursive=recursive)

    def get_item_children(self, item: Optional[Item]):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__items
        return item.children

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
            return item.name_models
        if column_id == 1:
            return item.value_models
        return None

    def destroy(self):
        self.__items = []
        _reset_default_attrs(self)
