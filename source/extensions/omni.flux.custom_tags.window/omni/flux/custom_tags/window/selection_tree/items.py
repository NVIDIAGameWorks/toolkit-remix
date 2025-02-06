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

from omni import ui
from omni.flux.custom_tags.core import CustomTagsCore
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf


class TagsSelectionItem(ui.AbstractItem):
    def __init__(self, tag_path: Sdf.Path):
        """
        A tree item representing a Tag (USD Collection)

        Args:
            tag_path: The Prim Path to the tag (USD Collection)
        """
        super().__init__()

        self._default_attr = {
            "_path": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._path = tag_path

    @property
    def path(self) -> Sdf.Path:
        """
        The Prim Path to the tag (USD Collection)

        Returns:
            A Prim Path pointing to the tag
        """
        return self._path

    @property
    def title(self) -> str:
        """
        The Prim Path to the tag (USD Collection)

        Returns:
            A Prim Path pointing to the tag
        """
        return CustomTagsCore.get_tag_name(self._path)

    def __repr__(self):
        return str(self._path)

    def destroy(self):
        _reset_default_attrs(self)


class TagsEditItem(ui.AbstractItem):
    def __init__(self, original_item: TagsSelectionItem | None = None):
        """
        A tree item to edit an existing `TagsSelectionItem` item or create a new tag
        """
        super().__init__()

        self._default_attr = {
            "_original_item": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._original_item = original_item

    @property
    def original_item(self) -> TagsSelectionItem | None:
        """
        The TagsSelectionItem that is being edited.

        If the item is a new item being created, this will be None.

        Returns:
            The original item if editing or None if creating a new item
        """
        return self._original_item

    @property
    def value(self) -> str:
        """
        The original value that should be set when creating the StringField.

        Returns:
            The StringField value
        """
        return self.original_item.title if self.original_item else "New_Tag"

    def __repr__(self):
        return self.value

    def destroy(self):
        _reset_default_attrs(self)
