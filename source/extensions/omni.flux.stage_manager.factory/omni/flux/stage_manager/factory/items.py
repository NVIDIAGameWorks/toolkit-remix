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

from __future__ import annotations

__all__ = ["StageManagerItem"]

import threading
from typing import TYPE_CHECKING, Any

from omni.flux.utils.common import reset_default_attrs

if TYPE_CHECKING:
    from .plugins.tree_plugin import StageManagerTreeItem


class StageManagerItem:
    def __init__(self, identifier: Any, data: Any = None, parent: StageManagerItem | None = None):
        """
        An item that should be built by a context plugin and used by the interaction plugin and any of its children
        plugins.

        Args:
            identifier: An identifier for the item.
            data: Data associated with the item.
            parent: The parent item
        """
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._identifier = identifier
        self._data = data
        self._parent = parent

        self._is_valid = None
        self._is_child_valid = None
        self._tree_item = None

        self._lock = threading.Lock()

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            "_identifier": None,
            "_data": None,
            "_parent": None,
        }

    @property
    def identifier(self) -> Any:
        """
        Returns:
            The identifier for the item.
        """
        return self._identifier

    @property
    def data(self) -> Any:
        """
        Returns:
            Data associated with the item.
        """
        return self._data

    @property
    def parent(self) -> StageManagerItem | None:
        """
        Returns:
            The parent item if one exists.
        """
        return self._parent

    @parent.setter
    def parent(self, value: StageManagerItem | None):
        """
        Set the parent item for which this item is a child.
        """
        self._parent = value

    @property
    def is_valid(self) -> bool:
        """
        Returns:
            Whether the item is valid or not based on the active filters.
        """
        return self._is_valid

    @is_valid.setter
    def is_valid(self, value: bool):
        """
        Set the item state based on the active filters.

        Updating an item will also update the parent if it exists and the item is valid.

        Args:
            value: The new value for the item.
        """
        with self._lock:
            if self.is_valid is True:
                return

            self._is_valid = value

            # Check if we need to update the parent while we hold the lock
            update_parent = value is True and self.parent

        if update_parent:
            self.parent.is_child_valid = value

    @property
    def is_child_valid(self):
        """
        Returns:
            Whether the item has any valid children or not based on the active filters.
        """
        return self._is_child_valid

    @is_child_valid.setter
    def is_child_valid(self, value: bool):
        with self._lock:
            if self.is_child_valid is True:
                return

            self._is_child_valid = value

            # Check if we need to update the parent while we hold the lock
            update_parent = value is True and self.parent

        if update_parent:
            self.parent.is_child_valid = value

    @property
    def tree_item(self) -> StageManagerTreeItem:
        """
        Returns:
            The TreeView item for the stage item.
        """
        return self._tree_item

    @tree_item.setter
    def tree_item(self, value: StageManagerTreeItem):
        """
        Set the TreeView item for the stage item.

        Args:
            value: The new TreeView item.
        """
        self._tree_item = value

    def reset_filter_state(self):
        """
        Reset the filter state of the item.

        Should be used before filtering the item to make sure an updated state is set.
        """
        self._is_valid = None
        self._is_child_valid = None

    def destroy(self):
        reset_default_attrs(self)
