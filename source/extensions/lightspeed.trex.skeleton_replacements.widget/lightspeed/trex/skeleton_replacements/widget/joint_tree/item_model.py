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
from omni.flux.utils.widget.tree_widget import TreeItemBase as _TreeItemBase


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, text: str):
        super().__init__()
        self.text = text
        self.model = ui.SimpleStringModel(self.text)

    def __repr__(self):
        return f'"{self.text}"'


class ComboListModel(ui.AbstractItemModel):

    def __init__(self, item_list, default_index=0):
        super().__init__()
        if default_index >= len(item_list):
            raise ValueError("Invalid default index")
        self._default_index = default_index
        self._current_index = ui.SimpleIntModel(default_index)
        self._current_index.add_value_changed_fn(lambda a: self._item_changed(None))
        self._item_list = item_list
        self._items = []
        if item_list:
            for item in item_list:
                self._items.append(Item(item))

    def get_item_children(self, item):
        return self._items

    def get_item_list(self):
        return self._item_list

    def get_item_value_model(self, item=None, column_id=-1):
        if item is None:
            return self._current_index
        return item.model

    def get_current_index(self):
        return self._current_index.get_value_as_int()

    def set_current_index(self, index):
        self._current_index.set_value(index)

    def get_current_string(self):
        return self._items[self._current_index.get_value_as_int()].model.get_value_as_string()

    def get_item_value_model_count(self, item=None):
        if item is None:
            return len(self._items)
        return 1


class RemappedJointModel(ComboListModel):

    def __init__(self, joint_names: list[str], default_index=-1):
        # if joint not found or out of range, use the last index as this is the most likely to be correct
        # for remapping skeletons where an extra joint exists at the end of a hierarchy chain
        last_index = len(joint_names) - 1
        if default_index >= len(joint_names) or default_index < 0:
            default_index = last_index
        super().__init__(joint_names, default_index=default_index)


class JointItem(_TreeItemBase):
    """An item representing an originally bound mesh joint and its corresponding capture joint."""

    def __init__(
        self,
        name: str,
        index: int,
        options: list[str],
        remapped_index: int = None,
        children: list[_TreeItemBase] = None,
    ):
        super().__init__(children=children)
        self._name = name
        self._index = index
        if remapped_index is None:
            remapped_index = index
        self._name_model = ui.SimpleStringModel(name)
        self._remap_options = RemappedJointModel(options, default_index=remapped_index)

    @property
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update({"_name_model": None, "_remap_options": None})
        return default_attr

    def add_child(self, child: _TreeItemBase):
        self._children.append(child)

    @property
    def children(self) -> list[_TreeItemBase]:
        return self._children

    @property
    def can_have_children(self) -> bool:
        return True

    @property
    def index(self):
        return self._index

    def name_model(self):
        return self._name_model

    def remap_model(self):
        return self._remap_options
