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

from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from omni import ui
from omni.flux.asset_importer.core.utils import determine_ideal_types as _determine_ideal_types
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl

from ..extension import get_file_listener_instance as _get_file_listener_instance
from .items import TextureImportItem, TextureTypes


class TextureImportListModel(ui.AbstractItemModel):

    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_children": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._children: Dict[TextureImportItem, Tuple] = {}
        self._pref_normal_conv: Optional[TextureTypes] = None
        self.__file_listener_instance = _get_file_listener_instance()

        self.__texture_type_changed = _Event()
        self.__changed = _Event()

    def set_preferred_normal_type(self, preferred_normal_type: TextureTypes):
        self._pref_normal_conv = preferred_normal_type

    def refresh(self, input_files: List[Tuple[_OmniUrl, TextureTypes]]):
        """Refresh the list"""
        for child in self._children:
            self.__file_listener_instance.remove_model(child)
        self._children = {}
        for path, texture_type in input_files:
            item = TextureImportItem(path, texture_type)
            self._children[item] = (
                item.subscribe_item_texture_type_changed(self._on_texture_type_changed),
                item.subscribe_item_changed(self._on_changed),
            )
            self.__file_listener_instance.add_model(item)

        self._item_changed(None)

    def refresh_texture_types(self, texture_types: Dict[str, TextureTypes] = None):
        """Re-parse the texture types based on the file names"""
        if texture_types is None:
            texture_types = self._determine_ideal_types([])

        for child in self._children:
            child_type = texture_types.get(child.path.path, TextureTypes.OTHER)
            if child.texture_type == child_type:
                continue
            child.texture_type = child_type

    def add_items(self, paths: List[Union[str, _OmniUrl]]):
        # Don't allow adding the same path 2x
        current_paths = [c.path.path for c in self._children]
        paths = [str(path) for path in paths if _OmniUrl(path).path not in current_paths]
        texture_types = self._determine_ideal_types(paths)

        # Update all existing children texture types
        self.refresh_texture_types(texture_types=texture_types)

        for path in paths:
            # Don't allow adding the same path 2x
            if _OmniUrl(path).path in [c.path.path for c in self._children]:
                continue

            item = TextureImportItem(_OmniUrl(path), texture_types.get(path, TextureTypes.OTHER))

            self._children[item] = (
                item.subscribe_item_texture_type_changed(self._on_texture_type_changed),
                item.subscribe_item_changed(self._on_changed),
            )
            self.__file_listener_instance.add_model(item)
        self._item_changed(None)

    def _determine_ideal_types(self, paths: List[str]) -> Dict[str, TextureTypes]:
        """
        Will try to determine the TextureType based on the filename. If no TextureType can be found, no entry will be
        added to the dictionary.
        """

        all_paths = [c.path.path for c in self._children]
        all_paths.extend(paths)

        return _determine_ideal_types(all_paths, pref_normal_conv=self._pref_normal_conv)

    def remove_items(self, items: List[TextureImportItem]):
        for item in items:
            del self._children[item]
            self.__file_listener_instance.remove_model(item)
        self._item_changed(None)

    def get_item_children(self, item: Optional[TextureImportItem]):
        """Returns all the children."""
        return list(self._children.keys()) if item is None else []

    def get_item_value_model(self, item: TextureImportItem, _column_id: int = 0):
        """The value model used when no delegate is used."""
        return item.value_model

    def get_item_value_model_count(self, _):
        """The number of columns in the delegate."""
        return 1

    def _on_texture_type_changed(self):
        """Call the event object that has the list of functions"""
        self.__texture_type_changed()

    def _on_changed(self, path: _OmniUrl):
        """Call the event object that has the list of functions"""
        self.__changed(path)

    def subscribe_changed(self, func: Callable[[_OmniUrl], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__changed, func)

    def subscribe_texture_type_changed(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__texture_type_changed, func)

    def destroy(self):
        _reset_default_attrs(self)
