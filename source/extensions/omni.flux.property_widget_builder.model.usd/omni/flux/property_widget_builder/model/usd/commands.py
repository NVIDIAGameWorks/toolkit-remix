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

import copy
from typing import Any

import carb
import omni.kit.commands
import omni.usd
from omni.flux.utils.common.interactive_usd_notices import defer_usd_notices
from omni.flux.utils.widget import GroupedKeysPayload
from pxr import Usd

from .logical_group_constants import (
    CURVE_LOGICAL_GROUP_DEFINITION,
    CURVE_LOGICAL_SUFFIXES,
    GRADIENT_LOGICAL_GROUP_DEFINITION,
    GRADIENT_LOGICAL_SUFFIXES,
    SCALAR_CURVE_LOGICAL_GROUP_DEFINITION,
)
from .logical_row import LogicalGroupDefinition, normalize_value_for_signature

__all__ = ["SetDataPrimvarsCommand"]


def __dir__() -> list[str]:
    """Expose only registerable command classes to Kit's module command registration."""
    return __all__


def _copy_snapshot_value(value: Any) -> Any:
    """Return a detached value suitable for undo snapshots and payload storage.

    Args:
        value: Raw USD/Python value to copy.

    Returns:
        A best-effort detached copy of ``value``.
    """
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return value
    if isinstance(value, dict):
        return copy.deepcopy(value)
    try:
        return list(value)
    except TypeError:
        pass
    try:
        return copy.deepcopy(value)
    except Exception:  # noqa: BLE001 - best effort for opaque USD container values.
        return type(value)(value)


def _is_color_values_payload(values: Any) -> bool:
    """Return whether grouped ``values`` data looks like color samples instead of scalar samples.

    Args:
        values: Payload ``values`` entry to inspect.

    Returns:
        ``True`` when the entry is a non-empty sequence of non-nested component sequences.
    """
    if values is None:
        value_items = []
    elif isinstance(values, (str, bytes, dict)):
        return False
    else:
        try:
            value_items = list(values)
        except TypeError:
            return False
    if not value_items:
        return False

    for value in value_items:
        if value is None or isinstance(value, (str, bytes, dict)):
            return False
        try:
            components = list(value)
        except TypeError:
            return False
        for component in components:
            if component is None or isinstance(component, (str, bytes, dict)):
                continue
            try:
                list(component)
            except TypeError:
                continue
            return False
    return True


def _infer_logical_group_definition(payload: GroupedKeysPayload) -> LogicalGroupDefinition:
    """Infer the grouped-key schema from suffixes and value shape.

    Full curve payloads include tangent/infinity suffixes. Two-suffix payloads are either scalar curves
    or gradients, disambiguated by whether ``values`` is a list of scalar samples or a list of color samples.

    Args:
        payload: Suffix-keyed grouped payload supplied to the command.

    Returns:
        Logical group definition matching the payload shape.

    Raises:
        ValueError: If the payload suffixes do not match a supported grouped-key schema.
    """
    suffixes = frozenset(payload)
    if suffixes == CURVE_LOGICAL_SUFFIXES:
        return CURVE_LOGICAL_GROUP_DEFINITION
    if suffixes == GRADIENT_LOGICAL_SUFFIXES:
        if _is_color_values_payload(payload.get("values")):
            return GRADIENT_LOGICAL_GROUP_DEFINITION
        return SCALAR_CURVE_LOGICAL_GROUP_DEFINITION
    raise ValueError(f"Cannot infer grouped-key logical group definition from payload suffixes {sorted(suffixes)!r}")


def _get_attrs_for_group(
    prim: Usd.Prim,
    logical_group_definition: LogicalGroupDefinition,
    group_id: str,
) -> dict[str, Usd.Attribute] | None:
    """Return all required attrs for one logical group, or ``None`` if the schema is incomplete.

    Args:
        prim: Target prim to inspect.
        logical_group_definition: Suffix definition for the grouped attrs.
        group_id: Full USD base name for the logical group.

    Returns:
        Mapping of suffix to USD attribute, or ``None`` when any required suffix attr is missing.
    """
    attrs = {}
    missing = []
    for suffix in logical_group_definition.suffixes:
        attr = prim.GetAttribute(f"{group_id}:{suffix}") if prim and prim.IsValid() else None
        if not attr or not attr.IsValid():
            missing.append(suffix)
            continue
        attrs[suffix] = attr
    if missing:
        carb.log_warn(
            f"Skipping grouped-key primvar write for {prim.GetPath() if prim and prim.IsValid() else '<invalid>'} "
            f"{group_id!r}: missing required suffix attrs {missing}"
        )
        return None
    return attrs


def _snapshot_group_payload(
    prim: Usd.Prim,
    logical_group_definition: LogicalGroupDefinition,
    group_id: str,
) -> GroupedKeysPayload | None:
    """Read one prim's grouped-key payload without creating missing schema attrs.

    Args:
        prim: Target prim to read.
        logical_group_definition: Suffix definition for the grouped attrs.
        group_id: Full USD base name for the logical group.

    Returns:
        Suffix-keyed payload, or ``None`` when the prim does not expose the complete group.
    """
    attrs = _get_attrs_for_group(prim, logical_group_definition, group_id)
    if attrs is None:
        return None
    return {suffix: _copy_snapshot_value(attr.Get()) for suffix, attr in attrs.items()}  # pyright: ignore[reportCallIssue]


def _snapshot_targets(
    stage: Usd.Stage,
    prim_paths: list[str],
    logical_group_definition: LogicalGroupDefinition,
    group_id: str,
) -> dict[str, GroupedKeysPayload]:
    """Capture per-target grouped payloads for undo/redo restoration.

    Args:
        stage: USD stage containing the targets.
        prim_paths: Target prim paths to snapshot.
        logical_group_definition: Suffix definition for the grouped attrs.
        group_id: Full USD base name for the logical group.

    Returns:
        Mapping of prim path to suffix-keyed payload for targets with complete schema attrs.
    """
    old_values = {}
    for prim_path in prim_paths:
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            carb.log_warn(f"Skipping grouped-key primvar snapshot: prim no longer valid at {prim_path}")
            continue
        payload = _snapshot_group_payload(prim, logical_group_definition, group_id)
        if payload is not None:
            old_values[prim_path] = payload
    return old_values


def _payload_has_required_suffixes(
    payload: GroupedKeysPayload, logical_group_definition: LogicalGroupDefinition
) -> bool:
    """Return whether ``payload`` contains every suffix required by the logical group definition.

    Args:
        payload: Candidate grouped-key payload.
        logical_group_definition: Suffix definition for the grouped attrs.

    Returns:
        ``True`` when every required suffix is present.
    """
    missing = [suffix for suffix in logical_group_definition.suffixes if suffix not in payload]
    if missing:
        carb.log_warn(f"Skipping grouped-key primvar write: payload is missing required suffixes {missing}")
        return False
    return True


def _write_payload_to_targets(
    stage: Usd.Stage,
    prim_paths: list[str],
    logical_group_definition: LogicalGroupDefinition,
    group_id: str,
    payload: GroupedKeysPayload,
) -> None:
    """Write a complete grouped payload to every valid target prim.

    Missing required suffix attrs skip that whole target/group write so related arrays are not partially updated.
    Normal edits preserve generated-schema attrs and do not create new USD attrs.

    Args:
        stage: USD stage containing the targets.
        prim_paths: Target prim paths to write.
        logical_group_definition: Suffix definition for the grouped attrs.
        group_id: Full USD base name for the logical group.
        payload: Complete suffix-keyed payload to write.
    """
    if not _payload_has_required_suffixes(payload, logical_group_definition):
        return

    with defer_usd_notices(stage):
        for prim_path in prim_paths:
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                carb.log_warn(f"Skipping grouped-key primvar write: prim no longer valid at {prim_path}")
                continue
            attrs = _get_attrs_for_group(prim, logical_group_definition, group_id)
            if attrs is None:
                continue
            for suffix, attr in attrs.items():
                value = payload[suffix]
                if value is None:
                    attr.Clear()
                    continue
                if normalize_value_for_signature(attr.Get()) == normalize_value_for_signature(value):
                    continue
                attr.Set(value)  # pyright: ignore[reportCallIssue]


def _restore_targets(
    stage: Usd.Stage,
    logical_group_definition: LogicalGroupDefinition,
    group_id: str,
    old_values_by_prim: dict[str, GroupedKeysPayload],
) -> None:
    """Restore grouped-key payloads captured before a command write.

    Args:
        stage: USD stage containing the targets.
        logical_group_definition: Suffix definition for the grouped attrs.
        group_id: Full USD base name for the logical group.
        old_values_by_prim: Mapping of prim path to payload captured before the write.
    """
    with defer_usd_notices(stage):
        for prim_path, old_values in old_values_by_prim.items():
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                carb.log_warn(f"Cannot undo grouped-key primvars: prim no longer valid at {prim_path}")
                continue
            attrs = _get_attrs_for_group(prim, logical_group_definition, group_id)
            if attrs is None:
                continue
            if not _payload_has_required_suffixes(old_values, logical_group_definition):
                continue
            for suffix, attr in attrs.items():
                old_value = old_values[suffix]
                if old_value is None:
                    attr.Clear()
                    continue
                if normalize_value_for_signature(attr.Get()) == normalize_value_for_signature(old_value):
                    continue
                attr.Set(old_value)  # pyright: ignore[reportCallIssue]


class SetDataPrimvarsCommand(omni.kit.commands.Command):
    """Atomically set a full grouped-key primvar payload with undo support."""

    def __init__(
        self,
        prim_paths: list[str],
        group_id: str,
        payload: GroupedKeysPayload,
        logical_group_definition: LogicalGroupDefinition | None = None,
        usd_context_name: str = "",
        stage: Usd.Stage | None = None,
        old_values: dict[str, GroupedKeysPayload] | None = None,
    ) -> None:
        """Store command inputs and infer the logical group definition when callers omit it.

        Args:
            prim_paths: Target prim paths to write.
            group_id: Full USD base name for the logical group.
            payload: Complete suffix-keyed payload to write.
            logical_group_definition: Optional explicit grouped-key schema.
            usd_context_name: USD context containing targets when ``stage`` is not supplied.
            stage: Optional stage override, mainly for tests and already-resolved callers.
            old_values: Optional pre-captured undo payloads keyed by prim path.
        """
        self._prim_paths = list(prim_paths)
        self._group_id = group_id
        self._payload = {suffix: _copy_snapshot_value(value) for suffix, value in payload.items()}
        self._logical_group_definition = logical_group_definition or _infer_logical_group_definition(self._payload)
        self._usd_context_name = usd_context_name
        self._stage = stage
        self._old_values = (
            {
                prim_path: {suffix: _copy_snapshot_value(value) for suffix, value in prim_payload.items()}
                for prim_path, prim_payload in old_values.items()
            }
            if old_values is not None
            else None
        )

    def do(self) -> None:
        """Capture undo data if needed, then write the grouped payload to each target."""
        stage = self._stage or omni.usd.get_context(self._usd_context_name).get_stage()  # pyright: ignore[reportAttributeAccessIssue]
        if self._old_values is None:
            self._old_values = _snapshot_targets(
                stage,
                self._prim_paths,
                self._logical_group_definition,
                self._group_id,
            )
        _write_payload_to_targets(
            stage,
            self._prim_paths,
            self._logical_group_definition,
            self._group_id,
            self._payload,
        )

    def undo(self) -> None:
        """Restore the per-target grouped payloads captured before ``do``."""
        if self._old_values is None:
            return
        stage = self._stage or omni.usd.get_context(self._usd_context_name).get_stage()  # pyright: ignore[reportAttributeAccessIssue]
        _restore_targets(stage, self._logical_group_definition, self._group_id, self._old_values)
