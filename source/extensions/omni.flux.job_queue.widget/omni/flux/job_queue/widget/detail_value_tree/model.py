"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

from __future__ import annotations

import dataclasses
import enum
import pathlib
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from omni import ui

from .item import DetailValueItem

__all__ = ("MISSING_VALUE", "DetailValueModel")

MISSING_VALUE = object()


class DetailValueModel(ui.AbstractItemModel):
    """Expose typed values while expanding only containers that genuinely branch."""

    def __init__(self, values: Sequence[tuple[str, str, Any]]) -> None:
        """Build one root item for each declared input or output port.

        Args:
            values: Port name, declared type name, and persisted value tuples.
        """
        super().__init__()
        self._roots = [self._build_item(name, value_type, value) for name, value_type, value in values]

    def can_item_have_children(self, item: DetailValueItem | None) -> bool:
        """Return whether the item exposes expandable nested values.

        Args:
            item: Item queried by the native tree.

        Returns:
            True when the item has one or more children.
        """
        return bool(item and item.children)

    def get_item_children(self, item: DetailValueItem | None = None) -> list[DetailValueItem]:
        """Return the requested item's children or the port roots.

        Args:
            item: Parent item, or None for the native tree root.

        Returns:
            Ordered child items.
        """
        return list(item.children) if item is not None else list(self._roots)

    @staticmethod
    def get_item_value_model_count(_item: DetailValueItem | None = None) -> int:
        """Return the fixed key and value column count.

        Args:
            _item: Unused native tree item.

        Returns:
            Two columns.
        """
        return 2

    @staticmethod
    def get_item_value_model(item: DetailValueItem | None, column_id: int = 0) -> ui.AbstractValueModel | None:
        """Return the key or value model for one item.

        Args:
            item: Item rendered by the native tree.
            column_id: Zero-based key or value column index.

        Returns:
            The requested string model, or None for the invisible native root.
        """
        if item is None:
            return None
        return item.key_model if column_id == 0 else item.value_model

    def get_visible_item_count(self, is_expanded: Callable[[DetailValueItem], bool]) -> int:
        """Count rows currently visible under the tree's expansion state.

        Args:
            is_expanded: Native expansion query for one item.

        Returns:
            Number of visible port and nested-value rows.
        """
        count = 0
        pending = list(reversed(self._roots))
        while pending:
            item = pending.pop()
            count += 1
            if item.children and is_expanded(item):
                pending.extend(reversed(item.children))
        return count

    def _build_item(self, key: str, value_type: str, value: Any) -> DetailValueItem:
        """Build one item and its nested children from a supported typed value.

        Args:
            key: Port, field, or collection-item name.
            value_type: Declared type shown on the port root.
            value: Persisted typed value.

        Returns:
            Native tree item containing readable models and children.
        """
        normalized = self._normalize_value(value)
        if normalized is MISSING_VALUE:
            return DetailValueItem((key,), "Not available", declared_type=value_type or None)
        if normalized is None:
            return DetailValueItem((key,), "Not set", declared_type=value_type or None)
        if isinstance(normalized, bool):
            return DetailValueItem((key,), "Yes" if normalized else "No", declared_type=value_type or None)
        if isinstance(normalized, (bytes, bytearray)):
            return DetailValueItem((key,), f"{len(normalized)} bytes", declared_type=value_type or None)
        if isinstance(normalized, Mapping):
            if not normalized:
                return DetailValueItem((key,), "{}", declared_type=value_type or None)
            children = [self._build_item(str(name), "", child_value) for name, child_value in normalized.items()]
            return self._build_container_item(key, value_type, children)
        if isinstance(normalized, list):
            if all(not isinstance(child_value, (Mapping, list)) for child_value in normalized):
                values = ", ".join(self._format_scalar(child_value) for child_value in normalized)
                return DetailValueItem((key,), f"[{values}]", declared_type=value_type or None)
            children = [
                self._build_item(f"Item {index}", "", child_value) for index, child_value in enumerate(normalized, 1)
            ]
            return self._build_container_item(key, value_type, children)
        return DetailValueItem((key,), str(normalized), declared_type=value_type or None)

    @staticmethod
    def _build_container_item(
        key: str,
        value_type: str,
        children: Sequence[DetailValueItem],
    ) -> DetailValueItem:
        """Fold an unbranched container path into one row, including its scalar leaf.

        Args:
            key: Key of the outer container.
            value_type: Declared type shown for the outer container.
            children: Normalized child rows.

        Returns:
            One compact scalar row when the path reaches a leaf, otherwise the first
            container row whose multiple children require an expandable branch.
        """
        key_parts = [key]
        compacted_children = tuple(children)
        while len(compacted_children) == 1:
            child = compacted_children[0]
            key_parts.extend(child.key_parts)
            if not child.children:
                return DetailValueItem(
                    key_parts,
                    child.value_model.as_string,
                    declared_type=value_type or None,
                )
            compacted_children = child.children
        return DetailValueItem(key_parts, value_type, compacted_children, declared_type=value_type or None)

    @staticmethod
    def _format_scalar(value: Any) -> str:
        """Format one normalized scalar inside an inline collection.

        Args:
            value: Normalized non-container value.

        Returns:
            Readable value matching scalar tree rows.
        """
        if value is None:
            return "Not set"
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, (bytes, bytearray)):
            return f"{len(value)} bytes"
        return str(value)

    @classmethod
    def _normalize_value(cls, value: Any) -> Any:
        """Convert supported typed values into explicit display containers.

        Args:
            value: Persisted typed value.

        Returns:
            A scalar, ordered mapping, or list suitable for the detail tree.
        """
        if value is MISSING_VALUE:
            return MISSING_VALUE
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return cls._normalize_value(dataclasses.asdict(value))
        if isinstance(value, Mapping):
            return {str(key): cls._normalize_value(child_value) for key, child_value in value.items()}
        if isinstance(value, (set, frozenset)):
            return [cls._normalize_value(child_value) for child_value in sorted(value, key=str)]
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [cls._normalize_value(child_value) for child_value in value]
        if isinstance(value, enum.Enum):
            return value.value if isinstance(value.value, (str, int, float, bool)) else value.name
        if isinstance(value, pathlib.Path):
            return value.as_posix()
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, type):
            return value.__name__
        if value is None or isinstance(value, (str, int, float, bool, bytes, bytearray)):
            return value
        return type(value).__name__
