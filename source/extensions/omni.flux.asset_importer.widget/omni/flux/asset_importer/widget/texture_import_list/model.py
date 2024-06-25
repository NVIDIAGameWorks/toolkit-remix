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

import hashlib
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from omni import ui
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_REGEX_MAP as _TEXTURE_TYPE_REGEX_MAP
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl

from ..extension import get_file_listener_instance as _get_file_listener_instance
from .items import TextureImportItem, TextureTypes


class TextureImportListModel(ui.AbstractItemModel):

    _PREFIX_TEXTURE_NO_PREFIX = "Unknown_prefix"

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

    @staticmethod
    def _get_default_prefix(path):
        # only 8 digit
        hash_int = int(hashlib.sha256(str(_OmniUrl(path).parent_url).encode("utf-8")).hexdigest(), 16) % 10**8
        return f"{TextureImportListModel._PREFIX_TEXTURE_NO_PREFIX}_{hash_int}"

    @staticmethod
    def get_texture_sets(paths: List[str]) -> Dict[str, List[Tuple[str, str]]]:
        """
        From a list of path, return a list of set of textures

        Args:
            paths: the texture paths

        Returns:
            Set of textures
        """
        texture_sets = {}

        # Combine all the TextureTypes in 1 regex expression to make building texture sets faster
        patterns = [
            _TEXTURE_TYPE_REGEX_MAP[t] for t in _TEXTURE_TYPE_REGEX_MAP if _TEXTURE_TYPE_REGEX_MAP[t] is not None
        ]
        regex_search = re.compile(
            rf".*({'|'.join(patterns)})",
            re.IGNORECASE,
        )

        # Build Texture Sets
        for path in paths:
            file_path = _OmniUrl(path).path
            regex_match = re.search(regex_search, file_path)
            # At least 1 keyword was found
            if regex_match:
                # If the individual item expressions have matching group, use those
                match_index = 1
                for index, group in enumerate(regex_match.groups()):
                    if not group:
                        continue
                    match_index = index + 1
                # The possible texture type
                match_group = regex_match.group(match_index)
                # Isolate the prefix used for the texture set
                prefix = file_path[: regex_match.start(match_index)]
                # if the texture name is Albedo.png/Metal.png/... with no prefix, we hash the full parent directory path
                if prefix == "".strip():
                    prefix = TextureImportListModel._get_default_prefix(path)
                if prefix not in texture_sets:
                    texture_sets[prefix] = []
                texture_sets[prefix].append((match_group, path))
            else:
                if file_path not in texture_sets:
                    texture_sets[file_path] = []
                texture_sets[file_path].append(("Other", path))

        return texture_sets

    def _determine_ideal_types(self, paths: List[str]) -> Dict[str, TextureTypes]:
        """
        Will try to determine the TextureType based on the filename. If no TextureType can be found, no entry will be
        added to the dictionary.
        """

        texture_types = {}

        all_paths = [c.path.path for c in self._children]
        all_paths.extend(paths)

        texture_sets = TextureImportListModel.get_texture_sets(all_paths)

        # Sort the sets by length so the more precise prefixes overwrite the less precise prefixes
        ordered_sets = sorted(texture_sets.keys(), key=len)

        # Find the Texture Types
        for set_prefix in ordered_sets:
            set_types = texture_sets[set_prefix]

            for path in all_paths:
                file_path = _OmniUrl(path).path

                # Make sure the file is part of the texture set
                if not file_path.startswith(set_prefix) and not set_prefix.startswith(
                    TextureImportListModel._PREFIX_TEXTURE_NO_PREFIX
                ):
                    continue

                texture_type = None

                # Get the texture type of the file in the set
                set_texture_type = None
                for set_type, _ in set_types:
                    if file_path.startswith(set_prefix + set_type) or (
                        set_prefix.startswith(TextureImportListModel._PREFIX_TEXTURE_NO_PREFIX)
                        and file_path.startswith(set_type)
                    ):
                        set_texture_type = set_type
                        break

                # Get the enum value matching the texture type
                # If the texture type is in the set multiple times, we keep the type as OTHER since it's probably
                # not the texture type (Example: T_Metal_01.png and T_Metal_02.png)
                if set_texture_type and len([t for t, _ in set_types if t.lower() == set_texture_type.lower()]) == 1:
                    for t in TextureTypes:
                        pattern = _TEXTURE_TYPE_REGEX_MAP.get(t)
                        if pattern is None:
                            continue
                        # If the enum REGEX matches with the set texture type, we found the right type
                        if re.search(pattern, set_texture_type, re.IGNORECASE):
                            texture_type = t
                            break

                # Only update the texture type if a type was found.
                # Since the prefixes are ordered by length, a more precise prefix will override a broader one
                # (Example: T_Metal_Normal_OTH.png -> [T_Metal_, T_Metal_Normal_] will end up with value: OTH)
                if texture_type:
                    # Special check for normals, which can be in one of three encodings
                    if self._pref_normal_conv is not None and texture_type in [
                        TextureTypes.NORMAL_OGL,
                        TextureTypes.NORMAL_DX,
                        TextureTypes.NORMAL_OTH,
                    ]:
                        texture_types[path] = self._pref_normal_conv
                    else:
                        texture_types[path] = texture_type

        # Return the list of explicitly known texture types only
        return texture_types

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
