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

from typing import Optional

from omni.flux.property_widget_builder.widget import ItemModel as _ItemModel


class FileAttributeNameModel(_ItemModel):
    def __init__(self, path: str, attribute: str, display_attr_name: Optional[str] = None):
        """
        Value model of the name of an attribute of a file

        Args:
            path: the file path
            attribute: the attribute of the file
            display_attr_name: override the name of the attribute to show
        """
        super().__init__()
        self._path = path
        self._attribute = attribute
        self._display_attr_name = display_attr_name
        self._value = None  # The value to be displayed on widget
        self._read_value_from_file()

    def refresh(self):
        """Name of the attribute doesn't refresh here"""
        pass

    def get_value(self) -> str:
        return self._value

    def _get_value_as_string(self) -> str:
        if self._value is None:
            return ""
        return str(self._value)

    def _get_value_as_float(self) -> float:
        if self._value is None:
            return 0.0
        return float(self._value)

    def _get_value_as_bool(self) -> bool:
        if self._value is None:
            return False
        return bool(self._value)

    def _get_value_as_int(self) -> int:
        if self._value is None:
            return 0
        return int(self._value)

    def _read_value_from_file(self):
        if not self._path:
            assert self._value is None
            return

        self._value = self._display_attr_name or self._attribute


class CustomFileAttributeNameModel(FileAttributeNameModel):
    def __init__(self, attribute_name: str):
        # Super Init Calls _read_value_from_file so this needs to be set before
        self._attribute_name = attribute_name
        super().__init__("", "", None)

    def _read_value_from_file(self):
        """
        :return: True if the cached value was updated; false otherwise
        """
        value_was_set = self._value != self._attribute_name
        self._value = self._attribute_name
        return value_was_set
