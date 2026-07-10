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

import carb
from omni.flux.fcurve.widget import FCurve, FCurveKey, InfinityType, TangentType
from omni.flux.utils.widget import GroupedKeysPayload

__all__ = ["curve_to_payload", "payload_to_curve"]


def _token_to_tangent_type(token: str) -> TangentType:
    """Convert a persisted tangent token into an ``FCurve`` tangent enum.

    Args:
        token: Persisted tangent type token.

    Returns:
        Matching tangent enum, or ``LINEAR`` for unknown tokens.
    """
    try:
        return TangentType[str(token).upper()]
    except KeyError:
        carb.log_warn(f"Unknown tangent type '{token}', defaulting to LINEAR")
        return TangentType.LINEAR


def _token_to_infinity_type(token: str) -> InfinityType:
    """Convert a persisted infinity token into an ``FCurve`` infinity enum.

    Args:
        token: Persisted infinity type token.

    Returns:
        Matching infinity enum, or ``CONSTANT`` for unknown tokens.
    """
    try:
        return InfinityType[str(token).upper()]
    except KeyError:
        carb.log_warn(f"Unknown infinity type '{token}', defaulting to CONSTANT")
        return InfinityType.CONSTANT


def curve_to_payload(curve: FCurve) -> GroupedKeysPayload:
    """Convert an ``FCurve`` into the shared suffix-keyed grouped payload.

    The curve editor owns FCurve semantics; USD-backed callers persist only the returned generic payload.

    Args:
        curve: Curve editor data model to serialize.

    Returns:
        Suffix-keyed payload containing key values, tangent data, and infinity modes.
    """
    keys = curve.keys
    return {
        "times": [key.time for key in keys],
        "values": [key.value for key in keys],
        "inTangentTimes": [key.in_tangent_x for key in keys],
        "inTangentValues": [key.in_tangent_y for key in keys],
        "inTangentTypes": [key.in_tangent_type.name.lower() for key in keys],
        "outTangentTimes": [key.out_tangent_x for key in keys],
        "outTangentValues": [key.out_tangent_y for key in keys],
        "outTangentTypes": [key.out_tangent_type.name.lower() for key in keys],
        "tangentBrokens": [key.tangent_broken for key in keys],
        "preInfinity": curve.pre_infinity.name.lower(),
        "postInfinity": curve.post_infinity.name.lower(),
    }


def payload_to_curve(group_id: str, payload: GroupedKeysPayload | None) -> FCurve | None:
    """Convert a shared suffix-keyed payload into an ``FCurve`` for rendering/editing.

    Args:
        group_id: Curve id to assign to the returned ``FCurve``.
        payload: Suffix-keyed grouped payload, or ``None``.

    Returns:
        Converted ``FCurve``, or ``None`` when payload data is missing or malformed.
    """
    if payload is None:
        return None

    times = payload.get("times") or []
    values = payload.get("values") or []
    if len(times) != len(values):
        return None

    in_tangent_times = payload.get("inTangentTimes") or []
    in_tangent_values = payload.get("inTangentValues") or []
    in_tangent_types = payload.get("inTangentTypes") or []
    out_tangent_times = payload.get("outTangentTimes") or []
    out_tangent_values = payload.get("outTangentValues") or []
    out_tangent_types = payload.get("outTangentTypes") or []
    tangent_brokens = payload.get("tangentBrokens") or []

    keys = []
    for index, (time, value) in enumerate(zip(times, values)):
        keys.append(
            FCurveKey(
                time=float(time),
                value=float(value),
                in_tangent_type=(
                    _token_to_tangent_type(in_tangent_types[index])
                    if index < len(in_tangent_types)
                    else TangentType.LINEAR
                ),
                out_tangent_type=(
                    _token_to_tangent_type(out_tangent_types[index])
                    if index < len(out_tangent_types)
                    else TangentType.LINEAR
                ),
                in_tangent_x=float(in_tangent_times[index]) if index < len(in_tangent_times) else -0.1,
                in_tangent_y=float(in_tangent_values[index]) if index < len(in_tangent_values) else 0.0,
                out_tangent_x=float(out_tangent_times[index]) if index < len(out_tangent_times) else 0.1,
                out_tangent_y=float(out_tangent_values[index]) if index < len(out_tangent_values) else 0.0,
                tangent_broken=bool(tangent_brokens[index]) if index < len(tangent_brokens) else False,
            )
        )

    return FCurve(
        id=group_id,
        keys=keys,
        pre_infinity=_token_to_infinity_type(payload.get("preInfinity") or "constant"),
        post_infinity=_token_to_infinity_type(payload.get("postInfinity") or "constant"),
    )
