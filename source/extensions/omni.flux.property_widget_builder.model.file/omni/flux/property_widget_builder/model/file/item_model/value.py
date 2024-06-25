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

from typing import Any

import omni.client
from omni.flux.property_widget_builder.widget import ItemModel as _ItemModel


class FileAttributeValueModel(_ItemModel):
    def __init__(self, path: str, attribute: str):
        """
        Value model of the value of an attribute of a file

        Args:
            path: the path of the file
            attribute: the attribute name to get the value from. It has to be an attribute from omni.client.ListEntry
        """
        super().__init__()
        self._path = path
        self._attribute = attribute
        self._value = None  # The value to be displayed on widget
        self._on_file_changed()

    def refresh(self):
        self._on_file_changed()
        self._on_dirty()

    def get_value(self) -> Any:
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

    def _on_file_changed(self):
        """Called with when an attribute in USD is changed"""
        self._read_value_from_file()

    def _read_value_from_file(self):
        """
        :return: True if the cached value was updated; false otherwise
        """
        if not self._path:
            assert self._value is None
            return False

        value_was_set = False
        result, entry = omni.client.stat(self._path)
        if result == omni.client.Result.OK and entry.flags & omni.client.ItemFlags.READABLE_FILE:
            value = getattr(entry, self._attribute)
            if self._value is None or value != self._value:
                self._value = value
                value_was_set = True
        return value_was_set

    def _set_value(self, value):
        """Override of ui.AbstractValueModel._set_value()"""
        pass

    def _on_dirty(self):
        self._value_changed()


class CustomFileAttributeValueModel(FileAttributeValueModel):
    def __init__(self, custom_value: Any, multiline: (bool, int)):
        # Super Init Calls _read_value_from_file so this needs to be set before
        self._custom_value = custom_value
        self._value = None
        super().__init__("", "")
        # Pass down the multiline capabilities after the super init
        self._multiline = multiline

    def _read_value_from_file(self):
        """
        :return: True if the cached value was updated; false otherwise
        """
        value_was_set = self._value != self._custom_value
        self._value = self._custom_value
        return value_was_set

    def _set_value(self, value):
        """Override of ui.AbstractValueModel._set_value()"""
        self._value = value

    def refresh(self):
        pass

    def _on_dirty(self):
        pass
