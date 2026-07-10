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

from collections.abc import Iterable, Iterator
from typing import Any

import carb
import omni.kit.commands
import omni.kit.undo
import omni.usd
from lightspeed.common.constants import PARTICLE_SCHEMA_NAME
from lightspeed.trex.schemas.utils import get_schema_prim
from omni.flux.utils.common.types import RealNumber
from pxr import Sdf, Usd

from .particle_edit_groups import PARTICLE_LEGACY_ANIMATION_MAPPINGS

__all__ = [
    "animated_attr_has_usable_keys",
    "get_legacy_seed_payload",
    "normalize_scalar_value",
    "seed_current_animated_attrs_from_legacy",
    "seed_current_animated_attrs_from_payload",
    "values_equal",
]

_FLOAT_TOLERANCE = 1e-6


def normalize_scalar_value(value: Any) -> Any:
    """Normalize scalar-like USD values for comparison.

    Args:
        value: Raw scalar, vector, sequence, or unsupported value.

    Returns:
        Numeric scalars unchanged, USD vector-like values as lists, and
        unsupported/non-iterable values unchanged.
    """
    if value is None or isinstance(value, (RealNumber, str, bytes, dict, Sdf.AssetPath)):
        return value
    try:
        return list(value)
    except TypeError:
        return value


def values_equal(left: Any, right: Any) -> bool:
    """Compare particle values with vector/color support and float tolerance.

    Args:
        left: First scalar or sequence value.
        right: Second scalar or sequence value.

    Returns:
        ``True`` when values are equal within particle float tolerance.
    """
    left = normalize_scalar_value(left)
    right = normalize_scalar_value(right)
    if isinstance(left, RealNumber) and isinstance(right, RealNumber):
        return abs(float(left) - float(right)) <= _FLOAT_TOLERANCE

    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        if len(left) != len(right):
            return False
        return all(values_equal(left_item, right_item) for left_item, right_item in zip(left, right))

    return left == right


def _has_usable_key_data(times: Iterable[Any] | None, values: Iterable[Any] | None) -> bool:
    """Return whether animated key arrays are non-empty and aligned.

    Args:
        times: Animated key times, or ``None``.
        values: Animated key values, or ``None``.

    Returns:
        ``True`` when both arrays are non-empty and have the same length.
    """
    if times is None or values is None:
        return False
    times_list = list(times)
    values_list = list(values)
    return bool(times_list) and bool(values_list) and len(times_list) == len(values_list)


def animated_attr_has_usable_keys(prim: Usd.Prim, animated_base_name: str, _kind: str) -> bool:
    """Return whether an animated curve/gradient base attr has usable key data.

    Args:
        prim: Particle prim containing the animated attrs.
        animated_base_name: Animated curve or gradient base primvar name.
        _kind: Mapping kind. Reserved for future kind-specific checks.

    Returns:
        ``True`` when the base attr has aligned ``:times`` and ``:values`` data.
    """
    times_attr = prim.GetAttribute(f"{animated_base_name}:times")
    values_attr = prim.GetAttribute(f"{animated_base_name}:values")
    times = times_attr.Get() if times_attr and times_attr.IsValid() else None  # pyright: ignore[reportCallIssue]
    values = values_attr.Get() if values_attr and values_attr.IsValid() else None  # pyright: ignore[reportCallIssue]
    return _has_usable_key_data(times, values)


def _get_seed_value(raw_value: Any, channel_index: int, kind: str) -> Any:
    """Extract an animated seed value from a legacy particle attr value.

    Args:
        raw_value: Legacy attr value read from USD. Can be scalar, vector-like,
            or color-like.
        channel_index: Channel index to extract for scalar curve animation.
        kind: Animated target kind, either ``"curve"`` or ``"gradient"``.

    Returns:
        A float for curve keyframes, or a tuple of floats for gradient colors.
    """
    raw_value = normalize_scalar_value(raw_value)
    if kind == "gradient":
        if not isinstance(raw_value, (list, tuple)):
            return (float(raw_value),)
        return tuple(float(component) for component in raw_value)
    if isinstance(raw_value, (list, tuple)):
        return float(raw_value[channel_index])
    return float(raw_value)


def _iter_mappings_for_animated(animated_attr_name: str) -> Iterator[tuple[str, dict, int]]:
    """Yield legacy mappings that feed a given animated attr.

    Args:
        animated_attr_name: Animated curve or gradient base primvar name.

    Yields:
        ``(legacy_attr_name, mapping, channel_index)`` tuples for matching
        legacy attrs.
    """
    for legacy_attr_name, mapping in PARTICLE_LEGACY_ANIMATION_MAPPINGS.items():
        for channel_index, mapped_animated_attr_name in mapping["animated"].items():
            if mapped_animated_attr_name == animated_attr_name:
                yield legacy_attr_name, mapping, channel_index


def _get_seed_points_for_animated(
    prim: Usd.Prim, schema_prim: Sdf.PrimSpec, animated_attr_name: str
) -> tuple[str | None, list[tuple[float, Any]], bool]:
    """Collect legacy values used to seed one animated attr.

    Args:
        prim: Particle prim holding legacy and animated particle attrs.
        schema_prim: Particle schema prim used for default-value comparison.
        animated_attr_name: Animated curve or gradient base primvar name.

    Returns:
        Tuple of ``(kind, points, has_non_default_legacy)`` where ``points`` is
        sorted as ``[(time, value), ...]``.
    """
    points = []
    has_non_default_legacy = False
    kind = None

    for legacy_attr_name, mapping, channel_index in _iter_mappings_for_animated(animated_attr_name):
        legacy_attr = prim.GetAttribute(legacy_attr_name)
        if not legacy_attr or not legacy_attr.IsValid():
            continue
        kind = mapping["kind"]
        schema_attr = schema_prim.properties.get(legacy_attr_name)
        legacy_value = legacy_attr.Get()  # pyright: ignore[reportCallIssue]
        legacy_matches_default = bool(schema_attr and values_equal(legacy_value, schema_attr.default))
        has_non_default_legacy = has_non_default_legacy or not legacy_matches_default
        points.append((mapping["time"], _get_seed_value(legacy_value, channel_index, mapping["kind"])))

    points.sort(key=lambda point: point[0])
    return kind, points, has_non_default_legacy


def _normalize_animated_attr_names(animated_attr_names: str | Iterable[str] | None) -> list[str]:
    """Normalize optional single/multiple animated attr names into a list.

    Args:
        animated_attr_names: One animated attr name, several names, or ``None``.

    Returns:
        List of animated attr names to seed.
    """
    if animated_attr_names is None:
        return []
    if isinstance(animated_attr_names, str):
        return [animated_attr_names]
    return list(animated_attr_names)


def get_legacy_seed_payload(
    animated_attr_names: str | Iterable[str] | None,
    context_name: str,
    target_paths: list[str],
) -> list[dict[str, Any]]:
    """Build a read-only legacy migration payload for selected particle targets.

    Hidden legacy attrs may still be authored directly in ASCII USDA files. This returns the curve/gradient
    seed data needed to populate currently empty animated attrs before the editor opens.

    Args:
        animated_attr_names: Animated curve/gradient attrs to inspect.
        context_name: USD context containing selected particles.
        target_paths: Ordered selected particle prim paths.

    Returns:
        Seed entries for empty animated attrs with non-default legacy values.
    """
    names_to_seed = _normalize_animated_attr_names(animated_attr_names)
    if not names_to_seed or not target_paths:
        return []

    context: Any = omni.usd.get_context(context_name)
    stage = context.get_stage() if context else None
    if stage is None:
        return []

    _schema_layer, schema_prim = get_schema_prim(PARTICLE_SCHEMA_NAME)
    if schema_prim is None:
        return []
    payload: list[dict[str, Any]] = []
    for prim_path in target_paths:
        prim = stage.GetPrimAtPath(prim_path)
        if prim is None or not prim.IsValid():
            continue
        for animated_attr_name in names_to_seed:
            kind, points, has_non_default_legacy = _get_seed_points_for_animated(prim, schema_prim, animated_attr_name)
            if kind not in ("curve", "gradient") or not points or not has_non_default_legacy:
                continue
            if animated_attr_has_usable_keys(prim, animated_attr_name, kind):
                continue
            payload.append(
                {
                    "prim_path": str(prim.GetPath()),
                    "animated_attr_name": animated_attr_name,
                    "kind": kind,
                    "points": points,
                }
            )
    return payload


def seed_current_animated_attrs_from_payload(payload: list[dict[str, Any]], context_name: str) -> bool:
    """Author a previously planned legacy seed payload through the shared grouped-key command.

    Args:
        payload: Seed entries from ``get_legacy_seed_payload``.
        context_name: USD context containing selected particles.

    Returns:
        ``True`` when at least one animated attr was seeded.
    """
    if not payload:
        return False

    seeded_any = False
    with omni.kit.undo.group():  # pyright: ignore[reportAttributeAccessIssue]
        for entry in payload:
            animated_attr_name = entry["animated_attr_name"]
            points = entry["points"]
            match entry["kind"]:
                case "curve":
                    omni.kit.commands.execute(
                        "SetDataPrimvars",
                        prim_paths=[entry["prim_path"]],
                        group_id=animated_attr_name,
                        payload={
                            "times": [float(time) for time, _value in points],
                            "values": [float(value) for _time, value in points],
                        },
                        usd_context_name=context_name,
                    )
                    seeded_any = True
                case "gradient":
                    omni.kit.commands.execute(
                        "SetDataPrimvars",
                        prim_paths=[entry["prim_path"]],
                        group_id=animated_attr_name,
                        payload={
                            "times": [float(time) for time, _value in points],
                            "values": [value for _time, value in points],
                        },
                        usd_context_name=context_name,
                    )
                    seeded_any = True
                case _:
                    carb.log_warn(
                        f"Unhandled legacy seed kind {entry['kind']!r} for {animated_attr_name!r}; "
                        "update seed_current_animated_attrs_from_payload when adding new mapping kinds."
                    )
    return seeded_any


def seed_current_animated_attrs_from_legacy(
    animated_attr_names: str | Iterable[str] | None,
    context_name: str,
    target_paths: list[str],
) -> bool:
    """Seed selected empty animated particle attrs from mapped legacy values, if any exist.

    Args:
        animated_attr_names: Animated curve/gradient attrs to inspect.
        context_name: USD context containing selected particles.
        target_paths: Ordered selected particle prim paths.

    Returns:
        ``True`` when at least one animated attr was seeded.
    """
    payload = get_legacy_seed_payload(animated_attr_names, context_name, target_paths)
    return seed_current_animated_attrs_from_payload(payload, context_name)
