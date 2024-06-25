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

from typing import Any, Callable, List, Optional, Union

from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl

from ..extension import get_file_listener_instance as _get_file_listener_instance
from .items import FileImportItem


class FileImportListModel(ui.AbstractItemModel):
    def __init__(self):
        super().__init__()
        self.default_attr = {"_children": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._children = {}
        self.__changed = _Event()
        self.__file_listener_instance = _get_file_listener_instance()

    def refresh(self, paths: List[_OmniUrl]):
        """Refresh the list"""
        for item in self._children:
            self.__file_listener_instance.remove_model(item)
        self._children = {}
        self.add_items(paths)

    def add_items(self, paths: List[Union[str, _OmniUrl]]):
        for path in paths:
            # Don't allow adding the same path 2x
            if str(path) in [c.path for c in self._children]:
                continue
            item = FileImportItem(_OmniUrl(path))
            self._children[item] = (item.subscribe_item_changed(self._on_changed),)
            self.__file_listener_instance.add_model(item)
        self._item_changed(None)

    def add_item(self, item: FileImportItem):
        # Don't allow adding the same path 2x
        if str(item.path) in [c.path for c in self._children]:
            return
        self._children[item] = (item.subscribe_item_changed(self._on_changed),)
        self.__file_listener_instance.add_model(item)
        self._item_changed(None)

    def remove_items(self, items: List[FileImportItem]):
        for item in items:
            del self._children[item]
            self.__file_listener_instance.remove_model(item)
        self._item_changed(None)

    def _on_changed(self, path: _OmniUrl):
        """Call the event object that has the list of functions"""
        self.__changed(path)

    def subscribe_changed(self, func: Callable[[_OmniUrl], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__changed, func)

    def get_item_children(self, item: Optional[FileImportItem]):
        """Returns all the children."""
        return list(self._children.keys()) if item is None else []

    def get_item_value_model(self, item: FileImportItem, _column_id: int = 0):
        """The value model used when no delegate is used."""
        return item.value_model

    def get_item_value_model_count(self, _):
        """The number of columns in the delegate."""
        return 1

    def destroy(self):
        _reset_default_attrs(self)
