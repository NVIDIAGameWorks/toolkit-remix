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

Primvar serialization for curve data.

Handles reading and writing FCurve data to/from USD primvars.
"""

from __future__ import annotations

from typing import Any

import carb
from pxr import Sdf, Usd

from omni.flux.fcurve.widget import FCurve, FCurveKey, InfinityType, TangentType

__all__ = [
    "curve_exists_in_primvars",
    "read_curve_from_primvars",
    "snapshot_primvar_values",
    "write_curve_to_prim",
]


class _Suffix:
    """Primvar attribute name suffixes for FCurve serialization."""

    TIMES = "times"
    VALUES = "values"
    IN_TANGENT_TIMES = "inTangentTimes"
    IN_TANGENT_VALUES = "inTangentValues"
    IN_TANGENT_TYPES = "inTangentTypes"
    OUT_TANGENT_TIMES = "outTangentTimes"
    OUT_TANGENT_VALUES = "outTangentValues"
    OUT_TANGENT_TYPES = "outTangentTypes"
    TANGENT_BROKENS = "tangentBrokens"
    PRE_INFINITY = "preInfinity"
    POST_INFINITY = "postInfinity"

    ALL: tuple[str, ...] = (
        TIMES,
        VALUES,
        IN_TANGENT_TIMES,
        IN_TANGENT_VALUES,
        IN_TANGENT_TYPES,
        OUT_TANGENT_TIMES,
        OUT_TANGENT_VALUES,
        OUT_TANGENT_TYPES,
        TANGENT_BROKENS,
        PRE_INFINITY,
        POST_INFINITY,
    )

    DOUBLE_ARRAYS: frozenset[str] = frozenset(
        {
            TIMES,
            VALUES,
            IN_TANGENT_TIMES,
            IN_TANGENT_VALUES,
            OUT_TANGENT_TIMES,
            OUT_TANGENT_VALUES,
        }
    )
    TOKEN_ARRAYS: frozenset[str] = frozenset({IN_TANGENT_TYPES, OUT_TANGENT_TYPES})
    BOOL_ARRAYS: frozenset[str] = frozenset({TANGENT_BROKENS})
    TOKENS: frozenset[str] = frozenset({PRE_INFINITY, POST_INFINITY})


def _tangent_type_to_token(t: TangentType) -> str:
    """Convert TangentType enum to USD token string."""
    return t.name.lower()


def _token_to_tangent_type(token: str) -> TangentType:
    """Convert USD token string to TangentType enum."""
    try:
        return TangentType[token.upper()]
    except KeyError:
        carb.log_warn(f"Unknown tangent type '{token}', defaulting to LINEAR")
        return TangentType.LINEAR


def _infinity_type_to_token(i: InfinityType) -> str:
    """Convert InfinityType enum to USD token string."""
    return i.name.lower()


def _token_to_infinity_type(token: str) -> InfinityType:
    """Convert USD token string to InfinityType enum."""
    try:
        return InfinityType[token.upper()]
    except KeyError:
        carb.log_warn(f"Unknown infinity type '{token}', defaulting to CONSTANT")
        return InfinityType.CONSTANT


def _get_primvar_names(curve_id: str) -> list[str]:
    """Get the list of primvar attribute names for a curve."""
    prefix = f"primvars:{curve_id}"
    return [f"{prefix}:{s}" for s in _Suffix.ALL]


def curve_to_primvar_data(curve_id: str, curve: FCurve) -> dict[str, Any]:
    """Convert FCurve to primvar attribute values dict."""
    keys = curve.keys
    prefix = f"primvars:{curve_id}"
    s = _Suffix

    return {
        f"{prefix}:{s.TIMES}": [k.time for k in keys],
        f"{prefix}:{s.VALUES}": [k.value for k in keys],
        f"{prefix}:{s.IN_TANGENT_TIMES}": [k.in_tangent_x for k in keys],
        f"{prefix}:{s.IN_TANGENT_VALUES}": [k.in_tangent_y for k in keys],
        f"{prefix}:{s.IN_TANGENT_TYPES}": [_tangent_type_to_token(k.in_tangent_type) for k in keys],
        f"{prefix}:{s.OUT_TANGENT_TIMES}": [k.out_tangent_x for k in keys],
        f"{prefix}:{s.OUT_TANGENT_VALUES}": [k.out_tangent_y for k in keys],
        f"{prefix}:{s.OUT_TANGENT_TYPES}": [_tangent_type_to_token(k.out_tangent_type) for k in keys],
        f"{prefix}:{s.TANGENT_BROKENS}": [k.tangent_broken for k in keys],
        f"{prefix}:{s.PRE_INFINITY}": _infinity_type_to_token(curve.pre_infinity),
        f"{prefix}:{s.POST_INFINITY}": _infinity_type_to_token(curve.post_infinity),
    }


def write_primvar_data(prim: Usd.Prim, data: dict[str, Any]) -> None:
    """Write primvar values to prim with uniform variability."""
    s = _Suffix
    for attr_name, value in data.items():
        if value is None:
            attr = prim.GetAttribute(attr_name)
            if attr and attr.IsValid():
                prim.RemoveProperty(attr_name)
            continue

        suffix = attr_name.rsplit(":", 1)[-1]
        if suffix in s.DOUBLE_ARRAYS:
            value_type = Sdf.ValueTypeNames.DoubleArray
        elif suffix in s.TOKEN_ARRAYS:
            value_type = Sdf.ValueTypeNames.TokenArray
        elif suffix in s.BOOL_ARRAYS:
            value_type = Sdf.ValueTypeNames.BoolArray
        elif suffix in s.TOKENS:
            value_type = Sdf.ValueTypeNames.Token
        else:
            raise ValueError(f"Unknown primvar attribute: {attr_name}")

        attr = prim.GetAttribute(attr_name)
        if not attr or not attr.IsValid():
            attr = prim.CreateAttribute(attr_name, value_type, custom=False, variability=Sdf.VariabilityUniform)

        attr.Set(value)


def restore_primvar_data(prim: Usd.Prim, old_values: dict[str, Any]) -> None:
    """Restore cached primvar values (for undo).

    Mirrors :func:`write_primvar_data`'s creation logic so that attributes
    removed by an interleaved command are recreated if needed.
    """
    s = _Suffix
    for attr_name, old_value in old_values.items():
        if old_value is None:
            attr = prim.GetAttribute(attr_name)
            if attr and attr.IsValid():
                prim.RemoveProperty(attr_name)
        else:
            attr = prim.GetAttribute(attr_name)
            if not attr or not attr.IsValid():
                suffix = attr_name.rsplit(":", 1)[-1]
                if suffix in s.DOUBLE_ARRAYS:
                    value_type = Sdf.ValueTypeNames.DoubleArray
                elif suffix in s.TOKEN_ARRAYS:
                    value_type = Sdf.ValueTypeNames.TokenArray
                elif suffix in s.BOOL_ARRAYS:
                    value_type = Sdf.ValueTypeNames.BoolArray
                elif suffix in s.TOKENS:
                    value_type = Sdf.ValueTypeNames.Token
                else:
                    continue
                attr = prim.CreateAttribute(attr_name, value_type, custom=False, variability=Sdf.VariabilityUniform)
            attr.Set(old_value)


def snapshot_primvar_values(prim: Usd.Prim, curve_id: str) -> dict[str, Any]:
    """Snapshot all current primvar values for a curve.

    Returns a dict of {attr_name: value} suitable for undo restoration.
    Missing attributes are recorded as None.
    """
    result = {}
    for attr_name in _get_primvar_names(curve_id):
        attr = prim.GetAttribute(attr_name)
        if attr and attr.IsValid():
            result[attr_name] = attr.Get()
        else:
            result[attr_name] = None
    return result


def write_curve_to_prim(prim: Usd.Prim, curve_id: str, curve: FCurve) -> None:
    """Write an FCurve to USD primvars directly (no command, no undo entry).

    Used during continuous edits (drag) for real-time visual feedback.
    """
    data = curve_to_primvar_data(curve_id, curve)
    write_primvar_data(prim, data)


def read_curve_from_primvars(prim: Usd.Prim, curve_id: str) -> FCurve | None:
    """
    Read an FCurve from USD primvars.

    Args:
        prim: The USD prim containing the primvars.
        curve_id: Curve identifier (e.g., "particle:opacity:x").

    Returns:
        FCurve object if primvars exist, None otherwise.
    """
    if not prim or not prim.IsValid():
        return None

    s = _Suffix
    prefix = f"primvars:{curve_id}"

    def _get(suffix: str) -> Any:
        attr = prim.GetAttribute(f"{prefix}:{suffix}")
        return attr.Get() if attr and attr.IsValid() else None

    times = _get(s.TIMES) or []
    values = _get(s.VALUES) or []

    if not times or not values or len(times) != len(values):
        return None

    in_tangent_times = _get(s.IN_TANGENT_TIMES) or []
    in_tangent_values = _get(s.IN_TANGENT_VALUES) or []
    in_tangent_types = _get(s.IN_TANGENT_TYPES) or []
    out_tangent_times = _get(s.OUT_TANGENT_TIMES) or []
    out_tangent_values = _get(s.OUT_TANGENT_VALUES) or []
    out_tangent_types = _get(s.OUT_TANGENT_TYPES) or []
    tangent_brokens = _get(s.TANGENT_BROKENS) or []
    pre_infinity = _get(s.PRE_INFINITY) or "constant"
    post_infinity = _get(s.POST_INFINITY) or "constant"

    keys = []
    for i, (t, v) in enumerate(zip(times, values)):
        in_tt = _token_to_tangent_type(in_tangent_types[i]) if i < len(in_tangent_types) else TangentType.LINEAR
        out_tt = _token_to_tangent_type(out_tangent_types[i]) if i < len(out_tangent_types) else TangentType.LINEAR

        in_tan_x = float(in_tangent_times[i]) if i < len(in_tangent_times) else -0.1
        in_tan_y = float(in_tangent_values[i]) if i < len(in_tangent_values) else 0.0
        out_tan_x = float(out_tangent_times[i]) if i < len(out_tangent_times) else 0.1
        out_tan_y = float(out_tangent_values[i]) if i < len(out_tangent_values) else 0.0

        broken = bool(tangent_brokens[i]) if i < len(tangent_brokens) else False

        keys.append(
            FCurveKey(
                time=float(t),
                value=float(v),
                in_tangent_type=in_tt,
                out_tangent_type=out_tt,
                in_tangent_x=in_tan_x,
                in_tangent_y=in_tan_y,
                out_tangent_x=out_tan_x,
                out_tangent_y=out_tan_y,
                tangent_broken=broken,
            )
        )

    return FCurve(
        id=curve_id,
        keys=keys,
        pre_infinity=_token_to_infinity_type(pre_infinity),
        post_infinity=_token_to_infinity_type(post_infinity),
    )


def curve_exists_in_primvars(prim: Usd.Prim, curve_id: str) -> bool:
    """
    Check if a curve exists in USD primvars.

    Args:
        prim: The USD prim to check.
        curve_id: Curve identifier.

    Returns:
        True if the curve's primvars exist with data.
    """
    if not prim or not prim.IsValid():
        return False

    times_attr = prim.GetAttribute(f"primvars:{curve_id}:{_Suffix.TIMES}")
    if not times_attr or not times_attr.IsValid():
        return False

    return times_attr.Get() is not None
