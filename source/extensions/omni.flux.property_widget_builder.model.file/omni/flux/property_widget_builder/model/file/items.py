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

from typing import Any, Optional

from omni.flux.property_widget_builder.widget import Item as _Item

from .item_model.name import CustomFileAttributeNameModel as _CustomFileAttributeNameModel
from .item_model.name import FileAttributeNameModel as _FileAttributeNameModel
from .item_model.value import CustomFileAttributeValueModel as _CustomFileAttributeValueModel
from .item_model.value import FileAttributeValueModel as _FileAttributeValueModel


class FileAttributeItem(_Item):
    """Item of the model"""

    def __init__(
        self,
        path: str,
        attribute: str,
        display_attr_name: Optional[str] = None,
    ):
        """
        Item that represent an attribute of a file

        Args:
            path: the path of the file
            attribute: the attribute of the file. It has to be an attribute from omni.client.ListEntry
            display_attr_name: override the name of the attribute to show
        """
        super().__init__()
        self.attribute = attribute  # used by custom delegate(s)
        self._name_models = [_FileAttributeNameModel(path, attribute, display_attr_name=display_attr_name)]
        self._value_models = [_FileAttributeValueModel(path, attribute)]


class CustomFileAttributeItem(FileAttributeItem):
    def __init__(self, values: [Any], attribute_name: str, multiline: (bool, int) = (False, 0)):
        super().__init__("", "", None)
        self.attribute = "custom"  # used by custom delegate(s)
        self._name_models = [_CustomFileAttributeNameModel(attribute_name)]
        self._value_models = [_CustomFileAttributeValueModel(value, multiline) for value in values]
