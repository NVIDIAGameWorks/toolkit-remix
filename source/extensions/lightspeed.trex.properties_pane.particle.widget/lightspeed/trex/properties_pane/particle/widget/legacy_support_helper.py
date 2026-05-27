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
import omni.usd
from lightspeed.common.constants import PARTICLE_SCHEMA_NAME
from lightspeed.trex.schemas.utils import get_schema_prim
from omni.flux.fcurve.widget import FCurve, FCurveKey
from omni.flux.utils.common.types import RealNumber
from pxr import Sdf, Usd

from .particle_edit_groups import PARTICLE_LEGACY_ANIMATION_MAPPINGS

__all__ = [
    "animated_attr_has_usable_keys",
    "normalize_scalar_value",
    "seed_current_animated_attr_from_legacy",
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


def seed_current_animated_attr_from_legacy(
    animated_attr_name: str,
    context_name: str,
    prim_path: str,
) -> bool:
    """Seed one empty animated particle attr from mapped legacy values.

    Existing animated keys are authoritative and are never overwritten.

    Args:
        animated_attr_name: Animated curve or gradient base primvar to seed.
        context_name: USD context name.
        prim_path: Particle prim path.

    Returns:
        ``True`` when the attr was seeded, otherwise ``False``.
    """
    context: Any = omni.usd.get_context(context_name)
    stage = context.get_stage() if context else None
    prim = stage.GetPrimAtPath(prim_path) if stage else None
    if prim is None or not prim.IsValid():
        return False

    _schema_layer, schema_prim = get_schema_prim(PARTICLE_SCHEMA_NAME)
    kind, points, has_non_default_legacy = _get_seed_points_for_animated(prim, schema_prim, animated_attr_name)
    has_keys = animated_attr_has_usable_keys(prim, animated_attr_name, kind) if kind else False
    if kind not in ("curve", "gradient") or not points or not has_non_default_legacy:
        return False
    if has_keys:
        return False

    match kind:
        case "curve":
            curve_id = animated_attr_name.removeprefix("primvars:")
            curve = FCurve(
                id=curve_id,
                keys=[FCurveKey(time=float(time), value=float(value)) for time, value in points],
            )
            omni.kit.commands.execute(
                "SetCurvePrimvars",
                prim_path=prim_path,
                curve_id=curve_id,
                curve=curve,
                usd_context_name=context_name,
            )
            return True
        case "gradient":
            omni.kit.commands.execute(
                "SetGradientPrimvars",
                prim_path=prim_path,
                base_name=animated_attr_name,
                times=[float(time) for time, _value in points],
                values=[value for _time, value in points],
                usd_context_name=context_name,
            )
            return True
        case _:
            carb.log_warn(
                f"Unhandled legacy seed kind {kind!r} for {animated_attr_name!r}; "
                "update seed_current_animated_attr_from_legacy when adding new mapping kinds."
            )
            return False
