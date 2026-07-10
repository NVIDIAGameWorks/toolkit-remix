"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import dataclasses

from typing import Any

import omni.usd
from pxr import Usd

__all__ = [
    "LogicalGroupDefinition",
    "LogicalRowState",
    "get_grouped_item_value_signature",
    "is_logical_group_mixed",
    "normalize_value_for_signature",
]


@dataclasses.dataclass(frozen=True)
class LogicalRowState:
    """State used by the USD property delegate for row indicators and actions."""

    is_mixed: bool = False
    is_overriden: bool = False
    is_default: bool = True


@dataclasses.dataclass(frozen=True)
class LogicalGroupDefinition:
    """Suffix-based definition for a logical USD property row.

    A logical row is stored as several sibling USD attributes sharing one base name and different suffixes,
    for example ``primvars:particle:color:times`` and ``primvars:particle:color:values``.
    """

    suffixes: tuple[str, ...]
    widget_kind: str
    primary_suffix: str = "values"

    def get_base_name(self, attr_name: str) -> str:
        """Strip a known suffix from ``attr_name`` and return the logical group base name.

        Args:
            attr_name: Concrete USD attribute name.

        Returns:
            Logical group base name, or the original name when the suffix is not managed.
        """
        parts = attr_name.rsplit(":", 1)
        if len(parts) != 2 or parts[1] not in self.suffixes:
            return attr_name
        return parts[0]

    def get_attr_names(self, base_name: str) -> list[str]:
        """Return concrete USD attribute names for ``base_name`` and this definition's suffixes.

        Args:
            base_name: Logical group base name.

        Returns:
            Concrete USD attribute names for every suffix.
        """
        return [f"{base_name}:{suffix}" for suffix in self.suffixes]

    def is_mixed(self, context_name: str, target_paths: list[str], base_name: str) -> bool:
        """Return whether this logical group has different values across target prims.

        Args:
            context_name: USD context containing the target prims.
            target_paths: Prim paths to compare.
            base_name: Logical group base name.

        Returns:
            ``True`` when any target's grouped value signature differs.
        """
        return is_logical_group_mixed(context_name, target_paths, self.get_attr_names(base_name))


def _get_signature_children(value: Any) -> tuple[str, list[Any]] | None:
    """Return normalized child traversal data for container-like values.

    Args:
        value: Value to inspect.

    Returns:
        Tuple of container kind and child values, or ``None`` for scalar-like values.
    """
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return None
    if isinstance(value, dict):
        return "dict", list(value.items())
    try:
        return "iterable", list(value)
    except TypeError:
        return None


def normalize_value_for_signature(value: Any) -> Any:
    """Normalize USD/Vt/Python containers into deterministic tuples for value signatures.

    Args:
        value: Scalar, USD/Vt container, or Python container to normalize.

    Returns:
        Stable scalar value or nested tuple representation suitable for equality
        checks across USD targets.
    """
    root_children = _get_signature_children(value)
    if root_children is None:
        return value

    root_kind, root_values = root_children
    root_frame = {
        "kind": root_kind,
        "children": root_values,
        "index": 0,
        "results": [None] * len(root_values),
        "parent": None,
        "parent_index": None,
    }
    frames = [root_frame]
    normalized = None

    while frames:
        frame = frames[-1]
        children = frame["children"]
        index = frame["index"]
        if index < len(children):
            frame["index"] += 1
            child = children[index]
            child_value = child[1] if frame["kind"] == "dict" else child
            child_children = _get_signature_children(child_value)
            if child_children is None:
                frame["results"][index] = child_value
                continue
            child_kind, child_values = child_children
            frames.append(
                {
                    "kind": child_kind,
                    "children": child_values,
                    "index": 0,
                    "results": [None] * len(child_values),
                    "parent": frame,
                    "parent_index": index,
                }
            )
            continue

        if frame["kind"] == "dict":
            frame_value = tuple(sorted((key, frame["results"][i]) for i, (key, _) in enumerate(children)))
        else:
            frame_value = tuple(frame["results"])

        frames.pop()
        parent = frame["parent"]
        if parent is None:
            normalized = frame_value
        else:
            parent["results"][frame["parent_index"]] = frame_value

    return normalized


def get_grouped_item_value_signature(
    stage: Usd.Stage, prim_path: str, attr_names: list[str]
) -> tuple[tuple[str, Any], ...]:
    """Return a deterministic value signature for a logical row on one prim.

    Args:
        stage: USD stage containing the prim.
        prim_path: Prim path to inspect.
        attr_names: Concrete USD attribute names to include.

    Returns:
        Tuple of ``(attr_name, normalized_value)`` entries.
    """
    prim = stage.GetPrimAtPath(prim_path)
    signature: list[tuple[str, Any]] = []
    for attr_name in attr_names:
        attr = prim.GetAttribute(attr_name) if prim and prim.IsValid() else None
        value = attr.Get() if attr and attr.IsValid() else None
        signature.append((attr_name, normalize_value_for_signature(value)))
    return tuple(signature)


def is_logical_group_mixed(context_name: str, target_paths: list[str], attr_names: list[str]) -> bool:
    """Return true if any attr in the logical group differs across target prims.

    Args:
        context_name: USD context name containing the selected target prims.
        target_paths: Ordered selected target prim paths to compare.
        attr_names: Concrete USD attribute names that make up the logical group.

    Returns:
        ``True`` when at least one target has a different grouped value signature.
    """
    if len(target_paths) <= 1:
        return False
    stage = omni.usd.get_context(context_name).get_stage()
    if stage is None:
        return False

    first_signature = get_grouped_item_value_signature(stage, target_paths[0], attr_names)
    for prim_path in target_paths[1:]:
        if get_grouped_item_value_signature(stage, prim_path, attr_names) != first_signature:
            return True
    return False
