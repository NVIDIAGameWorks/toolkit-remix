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

import abc

from omni import ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class TreeItemBase(ui.AbstractItem):
    """
    Base class for items displayed in a TreeWidget.

    This class provides the fundamental tree structure with parent-child relationships,
    enabling hierarchical data representation. Items maintain bidirectional references
    to their parent and children, automatically managing relationship updates when
    items are reparented.

    The internal children storage uses a dict (with None values) for O(1) lookups
    while preserving insertion order.

    Subclasses should:
        - Override `can_have_children` to define if the item supports child items.
        - Override `default_attr` to add custom attributes that need cleanup on destroy.
        - Add custom properties like `display_name`, `data`, `tooltip`, etc.
    """

    def __init__(
        self,
        parent: "TreeItemBase | None" = None,
    ):
        """
        Initialize a tree item with an optional parent.

        Args:
            parent: The parent item to attach to. If provided, this item will be
                added to the parent's children. Defaults to None (root-level item).
        """
        super().__init__()

        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        # NOTE: use a dictionary with None values
        # so that it's fast like a set but maintains order
        self._parent = None
        self._children = {}

        # NOTE: set initial parent using setter logic
        self.parent = parent

    @property
    def parent(self) -> "TreeItemBase | None":
        """
        The parent item of this item.

        Returns:
            The parent TreeItemBase, or None if this is a root-level item.
        """
        return self._parent

    @parent.setter
    def parent(self, new_parent: "TreeItemBase | None"):
        """
        Set or change the parent of this item.

        Handles bidirectional relationship management:
        - Removes this item from the previous parent's children (if any).
        - Adds this item to the new parent's children (if provided).

        Args:
            new_parent: The new parent item, or None to make this a root-level item.
        """
        if self._parent == new_parent:
            return  # nothing changes

        # unparent object
        if self._parent:
            # we access a protected variable here because we want to manipulate a dict
            if self in self._parent._children:  # noqa: SLF001
                del self._parent._children[self]  # noqa: SLF001
            self._parent = None

        if not new_parent:
            return

        # if new parent is added setup two way relationship
        self._parent = new_parent
        new_parent._children[self] = None  # noqa: SLF001

    @property
    def children(self) -> list["TreeItemBase"]:
        """
        The list of child items.

        Returns a copy of the children list to prevent accidental mutation of the
        internal collection. The underlying storage is a dict for O(1) lookups.

        Returns:
            A list of child TreeItemBase instances.
        """
        return list(self._children.keys())

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            "_display_name": None,
            "_data": None,
            "_tooltip": None,
            "_icon": None,
        }

    def clear_children(self):
        """
        Remove all children from this item.

        Iterates through all children and sets their parent to None, which
        automatically removes them from this item's children collection.
        """
        for child in self.children:
            child.parent = None

    @property
    @abc.abstractmethod
    def can_have_children(self) -> bool:
        """
        Whether this item can have child items.

        Subclasses must implement this property to indicate whether the item
        supports a hierarchical structure. This is used by the TreeWidget to
        determine whether to show expand/collapse controls.

        Returns:
            True if the item can contain children, False otherwise.
        """
        raise NotImplementedError()

    def destroy(self):
        self._children.clear()
        self._parent = None
        _reset_default_attrs(self)


class AlternatingRowItem(ui.AbstractItem):
    """
    A simple item used by AlternatingRowWidget to create alternating row backgrounds.

    Each item knows its position (odd/even) to determine its background style.

    Args:
        index: The row index, used to determine if this is an alternating row.
    """

    def __init__(self, index: int):
        super().__init__()

        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._alternate = index % 2 == 0

    @property
    def default_attr(self) -> dict[str, None]:
        return {"_alternate": None}

    @property
    def alternate(self) -> bool:
        return self._alternate

    def destroy(self):
        _reset_default_attrs(self)
