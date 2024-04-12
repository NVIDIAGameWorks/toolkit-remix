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
from pathlib import Path
from typing import List

import omni.ui as ui

if typing.TYPE_CHECKING:
    from lightspeed.widget.content_viewer.scripts.core import ContentData

from ..utils import get_instance as get_game_json_instance

HEADER_DICT = {0: "Original", 1: "Result"}


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, title, path, search_value, replace_value):
        super().__init__()
        self.title = title
        resolved = Path(path).resolve()
        self.path = str(resolved)
        self.replaced_path = str(resolved).replace(search_value, replace_value)
        self.path_model = ui.SimpleStringModel(self.path)

    def replaced_path_valid(self):
        return Path(self.replaced_path).resolve().exists()

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

    def refresh(self, items: List["ContentData"], search_value, replace_value):
        """Refresh the list"""
        self.__children = [Item(data.title, data.path, search_value, replace_value) for data in items]
        self._item_changed(None)

    def relink(self):
        result = {}
        dict_game_capture_folder_data = get_game_json_instance().get_file_data()
        for game_name, data in dict_game_capture_folder_data.items():
            result[game_name] = data
            for item in self.__children:
                if item.title == game_name:
                    result[game_name] = {"path": item.replaced_path}
                    break
        get_game_json_instance().override_data_with(result)

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
        for attr, value in self.default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()
                del m_attr
                setattr(self, attr, value)
