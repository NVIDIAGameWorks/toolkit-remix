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

from collections.abc import Iterable
from typing import Any

from omni.flux.utils.common import reset_default_attrs


class StageManagerItem:
    """Represent one context wrapper consumed by the Stage Manager."""

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
        self._is_display_name_candidate = False
        self._prepared_display_name: tuple[str, str | None] | None = None
        self._prepared_group_memberships: tuple[str, ...] | None = None

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
    def is_display_name_candidate(self) -> bool:
        """Return whether this item contributes to prepared display names."""
        return self._is_display_name_candidate

    @property
    def prepared_display_name(self) -> tuple[str, str | None]:
        """Return the display name prepared for this context refresh.

        Raises:
            RuntimeError: If no display name was prepared for this item.
        """
        if self._prepared_display_name is None:
            raise RuntimeError(f"Display name is not prepared for item {self.identifier!r}.")
        return self._prepared_display_name

    @property
    def prepared_group_memberships(self) -> tuple[str, ...]:
        """Return the group memberships prepared for this context refresh.

        Raises:
            RuntimeError: If no group memberships were prepared for this item.
        """
        if self._prepared_group_memberships is None:
            raise RuntimeError(f"Group memberships are not prepared for item {self.identifier!r}.")
        return self._prepared_group_memberships

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
        self.set_filter_validity(value)

    @property
    def is_child_valid(self):
        """
        Returns:
            Whether the item has any valid children or not based on the active filters.
        """
        return self._is_child_valid

    @is_child_valid.setter
    def is_child_valid(self, value: bool):
        if self.is_child_valid is True:
            return

        self._is_child_valid = value
        if value is True and self.parent:
            self.parent.is_child_valid = value

    def mark_display_name_candidate(self) -> None:
        """Mark this item as a display-name preparation candidate."""
        self._is_display_name_candidate = True

    def prepare_display_name(self, value: tuple[str, str | None]) -> None:
        """Store the display name prepared for this context refresh.

        Args:
            value: Display name and optional parent name.
        """
        self._prepared_display_name = value

    def prepare_group_memberships(self, values: Iterable[str]) -> None:
        """Store immutable group memberships for this context refresh.

        Args:
            values: Ordered group identifiers, including duplicates.
        """
        self._prepared_group_memberships = tuple(values)

    def reset_filter_state(self):
        """
        Reset the filter state of the item.

        Should be used before filtering the item to make sure an updated state is set.
        """
        self._is_valid = None
        self._is_child_valid = None

    def set_filter_validity(self, value: bool, propagate_to_ancestors: bool = True):
        """Set filter validity and optionally retain valid descendants through ancestors.

        Args:
            value: Whether this item passed the active filters.
            propagate_to_ancestors: Whether a valid item marks its ancestors as containing a valid child.
        """
        if self.is_valid is True:
            return

        self._is_valid = value
        if value is True and propagate_to_ancestors and self.parent:
            self.parent.is_child_valid = value

    def destroy(self):
        """Release data owned by this context wrapper."""
        self._is_display_name_candidate = False
        self._prepared_display_name = None
        self._prepared_group_memberships = None
        reset_default_attrs(self)
