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

Bezier curve math utilities.

Internal module providing curve evaluation and automatic tangent computation.
These functions are used by the widget internals and are not part of the public API.
"""

from __future__ import annotations

import math as _math
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ..model import CurveBounds, FCurve, FCurveKey

from ..model import TangentType

__all__ = [
    "BoundingRect",
    "KeyframeGestureData",
    "Vector2",
    "clamp",
    "compute_keyframe_tangents",
    "lerp",
    "process_curve",
    "process_keyframes",
]


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between a and b."""
    return a + (b - a) * t


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value to range [min_val, max_val]."""
    return max(min_val, min(max_val, value))


class Vector2:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

    def __add__(self, other: Vector2) -> Vector2:
        return Vector2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vector2) -> Vector2:
        return Vector2(self.x - other.x, self.y - other.y)

    def __neg__(self) -> Vector2:
        return Vector2(-self.x, -self.y)

    def __mul__(self, other: float) -> Vector2:
        return Vector2(self.x * other, self.y * other)

    def __truediv__(self, other: float) -> Vector2:
        return Vector2(self.x / other, self.y / other)

    def __str__(self) -> str:
        return f"Vector2({self.x}, {self.y})"

    def __repr__(self) -> str:
        return self.__str__()

    def length(self) -> float:
        return _math.sqrt(self.x * self.x + self.y * self.y)

    def normalized(self) -> Vector2:
        length = self.length()
        if length < 1e-10:
            return Vector2(0.0, 0.0)
        return Vector2(self.x / length, self.y / length)

    def angle(self) -> float:
        if self.x == 0.0 and self.y == 0.0:
            return 0.0
        return _math.atan2(self.y, self.x)

    def clamped(self, lower: Vector2, upper: Vector2) -> Vector2:
        return Vector2(clamp(self.x, lower.x, upper.x), clamp(self.y, lower.y, upper.y))

    @staticmethod
    def from_polar(angle: float, length: float) -> Vector2:
        return Vector2(length * _math.cos(angle), length * _math.sin(angle))


def _elliptical_scale(direction: Vector2, semi_axes: Vector2) -> Vector2:
    """Project direction onto an ellipse with the given semi-axes.

    Finds the point on ellipse (x/rx)^2 + (y/ry)^2 = 1 along the ray from
    origin in the given direction. This preserves the direction's angle in a
    space where each axis is independently scaled, avoiding the axis-bias
    that unit-circle normalization introduces when axes have different ranges.

    Args:
        direction: The direction vector (sign is preserved in the result).
        semi_axes: Ellipse semi-axes (rx, ry). Absolute values are used.
    """
    rx = max(abs(semi_axes.x), 1e-12)
    ry = max(abs(semi_axes.y), 1e-12)
    denom = _math.sqrt((direction.x / rx) ** 2 + (direction.y / ry) ** 2)
    if denom < 1e-12:
        return Vector2(0.0, 0.0)
    t = 1.0 / denom
    return Vector2(direction.x * t, direction.y * t)


class BoundingRect:
    """
    A rectangle defined by two points.
    """

    def __init__(self, min_pt: Vector2, max_pt: Vector2):
        self.min: Vector2 = Vector2(min_pt.x, min_pt.y)
        self.max: Vector2 = Vector2(max_pt.x, max_pt.y)

    def offset(self, offset: Vector2) -> BoundingRect:
        return BoundingRect(self.min + offset, self.max + offset)

    def is_inside(self, point: Vector2) -> bool:
        return self.min.x <= point.x <= self.max.x and self.min.y <= point.y <= self.max.y

    def raycast(self, origin: Vector2, end: Vector2) -> Vector2 | None:
        """Ray-AABB intersection using the slab method.

        Returns the closest intersection point between the segment origin->end
        and this rectangle, or None if the segment misses entirely.
        """
        d = end - origin
        t_min = 0.0
        t_max = 1.0

        for axis in (0, 1):
            o = origin.x if axis == 0 else origin.y
            di = d.x if axis == 0 else d.y
            lo = self.min.x if axis == 0 else self.min.y
            hi = self.max.x if axis == 0 else self.max.y

            if abs(di) < 1e-12:
                if o < lo or o > hi:
                    return None
            else:
                t1 = (lo - o) / di
                t2 = (hi - o) / di
                if t1 > t2:
                    t1, t2 = t2, t1
                t_min = max(t_min, t1)
                t_max = min(t_max, t2)
                if t_min > t_max:
                    return None

        return origin + d * t_min


def compute_keyframe_tangents(
    prev_key: FCurveKey | None,
    key: FCurveKey,
    next_key: FCurveKey | None,
    in_tangent_handle: Vector2,
    out_tangent_handle: Vector2,
    in_tangent_handle_dominates: bool,
    tangents_broken: bool,
    bounds: BoundingRect,
    x_flip_threshold: float,
) -> bool:
    """
    Receives UI + curve data and computes the tangents for a keyframe.

    Args:
        prev_key: The previous keyframe.
        key: The current keyframe.
        next_key: The next keyframe.
        in_tangent_handle: The in-tangent handle delta position from the keyframe.
        out_tangent_handle: The out-tangent handle delta position from the keyframe.
        in_tangent_handle_dominates: If in-tangent copies out-tangent or vice-versa. I.e: The dragged widget dominates.
        tangents_broken: If the tangents are broken or mirrored/linked.
        bounds: The bounds of the curve.
        x_flip_threshold: The minimum distance a tangent must keep from its own keyframe to not flip X axis.

    Returns:
        True if the active (dragged) tangent handle is outside its allowed bounds.
    """
    in_tangent = Vector2(-1.0, 0.0)
    out_tangent = Vector2(1.0, 0.0)
    prev_diff = Vector2(prev_key.time, prev_key.value) - Vector2(key.time, key.value) if prev_key else None
    next_diff = Vector2(next_key.time, next_key.value) - Vector2(key.time, key.value) if next_key else None

    mirrored = not tangents_broken and prev_key is not None and next_key is not None  # Boundary keyframes don't mirror.
    # Mirroring the UI handles and tangent types first.
    if mirrored:
        # Preserves the legnth while mirroring the angle.
        if in_tangent_handle_dominates:
            key.out_tangent_type = key.in_tangent_type
            out_tangent_handle = -in_tangent_handle.normalized() * out_tangent_handle.length()
        else:
            key.in_tangent_type = key.out_tangent_type
            in_tangent_handle = -out_tangent_handle.normalized() * in_tangent_handle.length()

    # In Tangents
    if prev_key is not None and prev_diff is not None:
        # Previous key's out tangent being STEP overrules all other tangent types.
        if prev_key.out_tangent_type == TangentType.STEP:
            in_tangent = Vector2(prev_diff.x / 2.0, 0.0)
        elif key.in_tangent_type == TangentType.LINEAR:
            in_tangent = prev_diff / 2.0
        elif key.in_tangent_type == TangentType.FLAT:
            in_tangent = Vector2(prev_diff.x / 2.0, 0.0)
        elif key.in_tangent_type == TangentType.STEP:
            # Falls back to LINEAR
            in_tangent = prev_diff / 2.0
        elif key.in_tangent_type == TangentType.AUTO:
            if next_key is not None:
                neighbor_diff = Vector2(next_key.time, next_key.value) - Vector2(prev_key.time, prev_key.value)
                in_tangent = -_elliptical_scale(neighbor_diff, prev_diff / 2.0)
            else:
                in_tangent = prev_diff / 2.0  # fallback to LINEAR
        elif key.in_tangent_type == TangentType.SMOOTH:
            in_tangent = _elliptical_scale(in_tangent_handle, prev_diff / 2.0)
        elif key.in_tangent_type == TangentType.CUSTOM:
            in_tangent = Vector2(in_tangent_handle.x, in_tangent_handle.y)

    # Out Tangents
    if next_key is not None and next_diff is not None:
        next_diff = Vector2(next_key.time, next_key.value) - Vector2(key.time, key.value)
        out_tangent = next_diff / 2.0
        if key.out_tangent_type == TangentType.LINEAR:
            out_tangent = next_diff / 2.0
        elif key.out_tangent_type == TangentType.FLAT:
            out_tangent = Vector2(next_diff.x / 2.0, 0.0)
        elif key.out_tangent_type == TangentType.STEP:
            out_tangent = Vector2(next_diff.x / 2.0, 0.0)  # Ignored since STEP is not a bezier curve.
        elif key.out_tangent_type == TangentType.AUTO:
            if prev_key is not None:
                neighbor_diff = Vector2(next_key.time, next_key.value) - Vector2(prev_key.time, prev_key.value)
                out_tangent = _elliptical_scale(neighbor_diff, next_diff / 2.0)
            else:
                out_tangent = next_diff / 2.0  # fallback to LINEAR
        elif key.out_tangent_type == TangentType.SMOOTH:
            out_tangent = _elliptical_scale(out_tangent_handle, next_diff / 2.0)
        elif key.out_tangent_type == TangentType.CUSTOM:
            out_tangent = Vector2(out_tangent_handle.x, out_tangent_handle.y)

    # Mirroring.
    if mirrored:
        # Preserves the legnth while mirroring the angle.
        if in_tangent_handle_dominates:
            out_tangent = -in_tangent.normalized() * out_tangent.length()
        else:
            in_tangent = -out_tangent.normalized() * in_tangent.length()

    # Bounds clamping.
    bound_min_diff = bounds.min - Vector2(key.time, key.value)
    bound_max_diff = bounds.max - Vector2(key.time, key.value)

    if prev_diff:
        in_bounds = BoundingRect(Vector2(prev_diff.x, bound_min_diff.y), Vector2(-x_flip_threshold, bound_max_diff.y))
        if not in_bounds.is_inside(in_tangent):
            hit = in_bounds.raycast(in_tangent, Vector2(0.0, 0.0))
            if hit:
                in_tangent = hit
            else:
                in_tangent = in_tangent.clamped(
                    Vector2(prev_diff.x, bound_min_diff.y), Vector2(-x_flip_threshold, bound_max_diff.y)
                )

    if next_diff:
        out_bounds = BoundingRect(Vector2(x_flip_threshold, bound_min_diff.y), Vector2(next_diff.x, bound_max_diff.y))
        if not out_bounds.is_inside(out_tangent):
            hit = out_bounds.raycast(out_tangent, Vector2(0.0, 0.0))
            if hit:
                out_tangent = hit
            else:
                out_tangent = out_tangent.clamped(
                    Vector2(x_flip_threshold, bound_min_diff.y), Vector2(next_diff.x, bound_max_diff.y)
                )

    # Write back to the keyframe. Boundary tangents (no neighbor) are zeroed.
    if prev_key is not None:
        key.in_tangent_x = in_tangent.x
        key.in_tangent_y = in_tangent.y
    else:
        key.in_tangent_x = 0.0
        key.in_tangent_y = 0.0
    if next_key is not None:
        key.out_tangent_x = out_tangent.x
        key.out_tangent_y = out_tangent.y
    else:
        key.out_tangent_x = 0.0
        key.out_tangent_y = 0.0

    # Returns if the tangent handle being dragged is outside their allowed bounds.
    if in_tangent_handle_dominates:
        in_tangent_bounds = BoundingRect(
            Vector2(bound_min_diff.x, bound_min_diff.y), Vector2(-x_flip_threshold, bound_max_diff.y)
        )
        return not in_tangent_bounds.is_inside(in_tangent_handle)
    out_tangent_bounds = BoundingRect(
        Vector2(x_flip_threshold, bound_min_diff.y), Vector2(bound_max_diff.x, bound_max_diff.y)
    )
    return not out_tangent_bounds.is_inside(out_tangent_handle)


class KeyframeGestureData:
    """
    Keyframe interaction data like UI handles position.

    Attributes:
        key: The FCurveKey reference.
        keyframe_handle: The position of the UI keyframe handle.
        in_tangent_handle: The position of the UI in-tangent handle.
        out_tangent_handle: The position of the UI out-tangent handle.
        in_tangent_handle_dominates: If in-tangent copies out-tangent or vice-versa. I.e: The dragged widget dominates.
    """

    def __init__(
        self,
        key: FCurveKey,
        keyframe_handle: Vector2,
        in_tangent_handle: Vector2,
        out_tangent_handle: Vector2,
        in_tangent_handle_dominates: bool,
    ):
        self.key: FCurveKey = key
        self.keyframe_handle: Vector2 = keyframe_handle
        self.in_tangent_handle: Vector2 = in_tangent_handle
        self.out_tangent_handle: Vector2 = out_tangent_handle
        self.in_tangent_handle_dominates: bool = in_tangent_handle_dominates


def process_keyframes(
    keyframes_data: list[KeyframeGestureData],
    bounds: BoundingRect,
    x_flip_threshold: float,
):
    """
    Processes a list of keyframes and computes the tangents for each keyframe.

    Args:
        keyframes_data: The list of keyframes and their interaction data.
        bounds: The bounds of the curve.
        x_flip_threshold: The minimum distance a tangent must keep from its own keyframe to not flip X axis.
    """
    padded_data = [None, *keyframes_data, None]

    # Correct keyframe positioning first.
    for prev_key, current, next_key in zip(padded_data, padded_data[1:], padded_data[2:]):
        # Bounds clamping.
        keyframe_pos = Vector2(current.keyframe_handle.x, current.keyframe_handle.y)
        keyframe_bounds = BoundingRect(bounds.min, bounds.max)
        if prev_key is not None:
            keyframe_bounds.min.x = prev_key.key.time + x_flip_threshold  # Leave a gap for the tangents.
        if next_key is not None:
            keyframe_bounds.max.x = next_key.key.time - x_flip_threshold  # Leave a gap for the tangents.

        keyframe_pos = keyframe_pos.clamped(keyframe_bounds.min, keyframe_bounds.max)
        current.key.time = keyframe_pos.x
        current.key.value = keyframe_pos.y

    # Process tangents.
    for prev_key, current, next_key in zip(padded_data, padded_data[1:], padded_data[2:]):
        compute_keyframe_tangents(
            prev_key=prev_key.key if prev_key else None,
            key=current.key,
            next_key=next_key.key if next_key else None,
            in_tangent_handle=current.in_tangent_handle,
            out_tangent_handle=current.out_tangent_handle,
            in_tangent_handle_dominates=current.in_tangent_handle_dominates,
            tangents_broken=current.key.tangent_broken,
            bounds=bounds,
            x_flip_threshold=x_flip_threshold,
        )


def process_curve(
    curve: FCurve,
    bounds: CurveBounds,
    x_flip_threshold: float,
    key_positions: dict[int, tuple[float, float]] | None = None,
    tangent_positions: dict[tuple[int, bool], tuple[float, float]] | None = None,
) -> None:
    """
    Process curve keyframes and tangents. Mutates curve.keys in place.

    Args:
        curve: The FCurve to process.
        bounds: Allowed X-Y range for keyframes and tangent handles.
        x_flip_threshold: Minimum distance a tangent must keep from its keyframe.
        key_positions: Override key positions (key_index -> (time, value)).
        tangent_positions: Override tangent handles ((key_index, is_in_tangent) -> (x, y)).
    """
    key_positions = key_positions or {}
    tangent_positions = tangent_positions or {}
    keys = curve.keys

    keyframes_data: list[KeyframeGestureData] = []
    for i, key in enumerate(keys):
        if i in key_positions:
            t, v = key_positions[i]
            keyframe_handle = Vector2(t, v)
        else:
            keyframe_handle = Vector2(key.time, key.value)

        in_key = (i, True)
        out_key = (i, False)
        in_tan = tangent_positions.get(in_key)
        out_tan = tangent_positions.get(out_key)

        # Which widget is being dragged? In-tangent override → in dominates; out only → out dominates.
        in_tangent_handle_dominates = in_tan is not None

        if in_tan is not None:
            in_tangent_handle = Vector2(in_tan[0], in_tan[1])
        else:
            in_tangent_handle = Vector2(key.in_tangent_x, key.in_tangent_y)

        if out_tan is not None:
            out_tangent_handle = Vector2(out_tan[0], out_tan[1])
        else:
            out_tangent_handle = Vector2(key.out_tangent_x, key.out_tangent_y)

        keyframes_data.append(
            KeyframeGestureData(
                key=key,
                keyframe_handle=keyframe_handle,
                in_tangent_handle=in_tangent_handle,
                out_tangent_handle=out_tangent_handle,
                in_tangent_handle_dominates=in_tangent_handle_dominates,
            )
        )

    rect = BoundingRect(
        Vector2(bounds.time_min, bounds.value_min),
        Vector2(bounds.time_max, bounds.value_max),
    )
    process_keyframes(keyframes_data, rect, x_flip_threshold)
