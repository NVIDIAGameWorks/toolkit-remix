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

Data model for FCurve widget.

This module defines the core data types used by FCurveWidget:
- FCurveKey: A single keyframe with time, value, and tangent data
- FCurve: A collection of keyframes forming a bezier curve
- CurveBounds: Allowed X-Y range for keyframes and tangent handles
- TangentType: Enum for tangent interpolation modes
- InfinityType: Enum for curve extrapolation beyond keyframes
- KeyReference: Identifier for a specific keyframe
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

__all__ = [
    "CurveBounds",
    "FCurve",
    "FCurveKey",
    "InfinityType",
    "KeyAddedEvent",
    "KeyChangedEvent",
    "KeyDeletedEvent",
    "KeyReference",
    "SelectionChangedEvent",
    "SelectionInfo",
    "TangentChangedEvent",
    "TangentReference",
    "TangentType",
]


class TangentType(IntEnum):
    """
    Tangent interpolation type for keyframes.

    Controls how the curve approaches and leaves a keyframe.
    """

    FLAT = 0
    """Horizontal tangent (zero slope)."""

    STEP = 1
    """Step function (hold value until next key)."""

    LINEAR = 2
    """Linear interpolation (straight line to neighbor)."""

    AUTO = 3
    """Automatically compute smooth tangents from neighbors, Catmull-Rom style."""

    SMOOTH = 4
    """Smooth spline tangent. Angle controlled by user, length is auto computed."""

    CUSTOM = 5
    """User-defined tangent angle and length."""


class InfinityType(IntEnum):
    """
    Extrapolation mode for curve values outside the keyframe range.

    Controls what value the curve returns before the first key
    and after the last key.
    """

    CONSTANT = 0
    """Hold the first/last key value."""

    LINEAR = 1
    """Continue with the tangent slope at the first/last key."""


@dataclass
class FCurveKey:
    """
    A single keyframe in an FCurve.

    Represents a control point with position (time, value) and tangent data
    for bezier curve interpolation.

    Attributes:
        time: The time position of the keyframe.
        value: The value at this keyframe.
        in_tangent_x: X component of incoming tangent (time offset, usually negative).
        in_tangent_y: Y component of incoming tangent (value offset).
        out_tangent_x: X component of outgoing tangent (time offset, usually positive).
        out_tangent_y: Y component of outgoing tangent (value offset).
        in_tangent_type: Interpolation type for incoming tangent.
        out_tangent_type: Interpolation type for outgoing tangent.
        tangent_broken: If True, in/out tangents can have independent angles.
    """

    time: float = 0.0
    value: float = 0.0

    in_tangent_x: float = -0.1
    in_tangent_y: float = 0.0
    out_tangent_x: float = 0.1
    out_tangent_y: float = 0.0

    in_tangent_type: TangentType = TangentType.LINEAR
    out_tangent_type: TangentType = TangentType.LINEAR

    tangent_broken: bool = True


@dataclass
class FCurve:
    """
    A function curve (bezier spline).

    Represents a single curve mapping time to value, composed of
    FCurveKey control points connected by bezier segments.

    Attributes:
        id: Unique identifier for this curve.
        keys: List of keyframes in time order.
        color: Display color as 0xAABBGGRR (omni.ui ABGR).
        pre_infinity: Extrapolation mode before the first key.
        post_infinity: Extrapolation mode after the last key.
        visible: Whether the curve is displayed.
        locked: Whether the curve can be edited.
    """

    id: str = ""
    keys: list[FCurveKey] = field(default_factory=list)
    color: int = 0xFFFFFFFF
    pre_infinity: InfinityType = InfinityType.CONSTANT
    post_infinity: InfinityType = InfinityType.CONSTANT
    visible: bool = True
    locked: bool = False


@dataclass
class CurveBounds:
    """
    Defines the allowed X-Y range for curve keyframes and tangent handles.

    All keyframes and tangent handles must be clamped to stay within these bounds.
    This is separate from the viewport display range (which can pan/zoom).

    Attributes:
        time_min: Minimum allowed time (X) value.
        time_max: Maximum allowed time (X) value.
        value_min: Minimum allowed value (Y).
        value_max: Maximum allowed value (Y).
    """

    time_min: float = 0.0
    time_max: float = 1.0
    value_min: float = 0.0
    value_max: float = 1.0


@dataclass(frozen=True)
class KeyReference:
    """
    Reference to a specific keyframe.

    Immutable identifier used for selection and event payloads.

    Attributes:
        curve_id: ID of the curve containing the key.
        key_index: Index of the key within the curve's key list.
    """

    curve_id: str
    key_index: int


@dataclass(frozen=True)
class TangentReference:
    """
    Reference to a specific tangent handle.

    Attributes:
        curve_id: ID of the curve containing the key.
        key_index: Index of the key within the curve's key list.
        is_in_tangent: True for incoming tangent, False for outgoing.
    """

    curve_id: str
    key_index: int
    is_in_tangent: bool


# ─────────────────────────────────────────────────────────────────────────────
# Event Payloads
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class KeyChangedEvent:
    """
    Event payload when a keyframe is modified.

    Attributes:
        curve_id: ID of the affected curve.
        key_index: Index of the modified key.
        old_time: Previous time value.
        old_value: Previous value.
        new_time: New time value.
        new_value: New value.
    """

    curve_id: str
    key_index: int
    old_time: float
    old_value: float
    new_time: float
    new_value: float


@dataclass(frozen=True)
class KeyAddedEvent:
    """
    Event payload when a keyframe is added.

    Attributes:
        curve_id: ID of the affected curve.
        key_index: Index where the new key was inserted.
        time: Time of the new key.
        value: Value of the new key.
    """

    curve_id: str
    key_index: int
    time: float
    value: float


@dataclass(frozen=True)
class KeyDeletedEvent:
    """
    Event payload when a keyframe is deleted.

    Attributes:
        curve_id: ID of the affected curve.
        key_index: Index of the deleted key (before deletion).
        time: Time of the deleted key.
        value: Value of the deleted key.
    """

    curve_id: str
    key_index: int
    time: float
    value: float


@dataclass(frozen=True)
class TangentChangedEvent:
    """
    Event payload when a tangent handle is modified.

    Attributes:
        curve_id: ID of the affected curve.
        key_index: Index of the key whose tangent changed.
        is_in_tangent: True if incoming tangent, False if outgoing.
        old_x: Previous tangent X component.
        old_y: Previous tangent Y component.
        new_x: New tangent X component.
        new_y: New tangent Y component.
    """

    curve_id: str
    key_index: int
    is_in_tangent: bool
    old_x: float
    old_y: float
    new_x: float
    new_y: float


@dataclass(frozen=True)
class SelectionChangedEvent:
    """
    Event payload when selection changes.

    Attributes:
        selected_keys: List of currently selected keyframe references.
        selected_tangents: List of currently selected tangent references.
    """

    selected_keys: tuple[KeyReference, ...]
    selected_tangents: tuple[TangentReference, ...]


@dataclass
class SelectionInfo:
    """
    Selection state for UI updates (toolbar, comboboxes, etc.).

    Unlike SelectionChangedEvent, this is a mutable dataclass with
    helper properties for common UI queries.

    Attributes:
        keys: List of selected keyframe references.
        tangents: List of selected tangent handle references.
    """

    keys: list[KeyReference] = field(default_factory=list)
    tangents: list[TangentReference] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True if nothing is selected."""
        return not self.keys and not self.tangents

    @property
    def curve_ids(self) -> set[str]:
        """Get unique curve IDs in selection (for multi-curve support)."""
        ids = {k.curve_id for k in self.keys}
        ids.update(t.curve_id for t in self.tangents)
        return ids

    @property
    def has_single_key(self) -> bool:
        """True if exactly one key is selected (no tangents)."""
        return len(self.keys) == 1 and not self.tangents

    @property
    def key_count(self) -> int:
        """Number of selected keys."""
        return len(self.keys)

    @property
    def tangent_count(self) -> int:
        """Number of selected tangent handles."""
        return len(self.tangents)
