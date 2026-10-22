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


FCurveWidget - A self-contained function curve widget.

Public API for rendering and editing bezier curves.
Constructor = build: call inside a parent `with` context.

Example:
    >>> with ui.ZStack():
    ...     widget = FCurveWidget()
    >>> widget.set_curves({"c": FCurve(id="c", keys=[...])})
"""

from __future__ import annotations


from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import replace
from math import isfinite, isnan, nextafter

import carb.input
from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription

from .model import (
    CurveBounds,
    FCurve,
    FCurveKey,
    InfinityType,
    KeyAddedEvent,
    KeyChangedEvent,
    KeyDeletedEvent,
    KeyReference,
    SelectionChangedEvent,
    SelectionInfo,
    TangentChangedEvent,
    TangentReference,
    TangentType,
)
from .style import DEFAULT_STYLE

from ._internal.curve_widgets_manager import CurveWidgetsManager
from ._internal.math import is_key_time_gap_valid, process_curve
from ._internal.viewport import ViewportState

__all__ = ["FCurveWidget"]


class FCurveWidget:
    """
    Self-contained function curve widget.

    Constructor = build. Must be called inside a parent ``with`` context.
    Visual appearance is controlled via omni.ui name-based style selectors
    (see ``DEFAULT_STYLE``).  Override by wrapping in a parent frame::

        with ui.Frame(style={"Rectangle::FCurveKey": {"border_radius": 4}}):
            widget = FCurveWidget()

    Args:
        time_range: Initial (min, max) time range for the viewport.
        value_range: Initial (min, max) value range for the viewport.
        viewport_size: Initial (width, height) in pixels.
        curve_bounds: Allowed X-Y range for keyframes and tangent handles.
        key_size: Keyframe handle size in pixels.
        tangent_size: Tangent handle size in pixels.
        placer_size: Hit-test placer size in pixels (affects drag target area).
        keyframe_clamp_threshold: Minimum time distance between keyframes.
        on_commit: Called with (curve_id, curve) when curve data changes.
        on_drag_started: Called with (curve_id) when a drag begins.
        on_drag_ended: Called with (curve_id) when a drag ends.
        on_hover_changed: Called with curve_id or None on hover change.
    """

    def __init__(
        self,
        time_range: tuple[float, float] = (0.0, 1.0),
        value_range: tuple[float, float] = (0.0, 1.0),
        viewport_size: tuple[float, float] | None = None,
        curve_bounds: CurveBounds | None = None,
        per_curve_bounds: dict[str, CurveBounds] | None = None,
        key_size: int = 8,
        tangent_size: int = 6,
        placer_size: int = 20,
        keyframe_clamp_threshold: float = 0.001,
        on_commit: Callable[[str, FCurve], None] | None = None,
        on_drag_started: Callable[[str], None] | None = None,
        on_drag_ended: Callable[[str], None] | None = None,
        on_hover_changed: Callable[[str | None], None] | None = None,
    ):
        self._key_size = key_size
        self._tangent_size = tangent_size
        self._placer_size = placer_size
        self._default_bounds = curve_bounds or CurveBounds(
            time_min=time_range[0],
            time_max=time_range[1],
            value_min=value_range[0],
            value_max=value_range[1],
        )
        self._per_curve_bounds: dict[str, CurveBounds] = dict(per_curve_bounds) if per_curve_bounds else {}
        self._threshold = keyframe_clamp_threshold
        self._on_commit = on_commit
        self._on_drag_started = on_drag_started
        self._on_drag_ended = on_drag_ended
        self._on_hover_changed = on_hover_changed

        self._curves: dict[str, FCurve] = {}
        self._managers: dict[str, CurveWidgetsManager] = {}
        self._selected_keys: list[KeyReference] = []
        self._selected_tangents: list[TangentReference] = []
        self._dragging_curve_id: str | None = None
        self._key_drag_selection: tuple[KeyReference, ...] = ()
        self._key_drag_baseline: dict[str, list[FCurveKey]] = {}

        self._viewport = ViewportState()
        self._viewport.set_time_range(time_range[0], time_range[1])
        self._viewport.set_value_range(value_range[0], value_range[1])
        if viewport_size:
            self._viewport.set_size(viewport_size[0], viewport_size[1])

        self.__on_key_changed = _Event()
        self.__on_key_added = _Event()
        self.__on_key_deleted = _Event()
        self.__on_tangent_changed = _Event()
        self.__on_selection_changed = _Event()
        self.__on_curve_changed = _Event()

        self._stack: ui.ZStack | None = (
            ui.ZStack(width=ui.Pixel(viewport_size[0]), height=ui.Pixel(viewport_size[1]), style=DEFAULT_STYLE)
            if viewport_size
            else ui.ZStack(style=DEFAULT_STYLE)
        )

    # ── Public: viewport ────────────────────────────────────────────────────

    @property
    def viewport(self) -> ViewportState:
        return self._viewport

    @property
    def time_range(self) -> tuple[float, float]:
        return (self._viewport.time_min, self._viewport.time_max)

    @time_range.setter
    def time_range(self, value: tuple[float, float]) -> None:
        self._viewport.set_time_range(value[0], value[1])
        for mgr in self._managers.values():
            mgr.sync_viewport()

    @property
    def value_range(self) -> tuple[float, float]:
        return (self._viewport.value_min, self._viewport.value_max)

    @value_range.setter
    def value_range(self, value: tuple[float, float]) -> None:
        self._viewport.set_value_range(value[0], value[1])
        for mgr in self._managers.values():
            mgr.sync_viewport()

    @property
    def curve_bounds(self) -> CurveBounds:
        return self._default_bounds

    @curve_bounds.setter
    def curve_bounds(self, value: CurveBounds) -> None:
        self._default_bounds = value

    def set_curve_bounds(self, curve_id: str, bounds: CurveBounds) -> None:
        """Set clamping bounds for a specific curve."""
        self._per_curve_bounds[curve_id] = bounds

    def bounds_for(self, curve_id: str) -> CurveBounds:
        """Return bounds for a specific curve, falling back to the default."""
        return self._per_curve_bounds.get(curve_id, self._default_bounds)

    def set_zoom(self, zoom: float) -> None:
        for mgr in self._managers.values():
            mgr.set_zoom(zoom)

    def set_viewport_size(self, width: float, height: float) -> None:
        self._viewport.set_size(width, height)
        for mgr in self._managers.values():
            mgr.sync_viewport()

    # ── Public: curves ──────────────────────────────────────────────────────

    @property
    def curves(self) -> dict[str, FCurve]:
        return dict(self._curves)

    def set_curves(self, curves: dict[str, FCurve]) -> None:
        self._finish_drag()
        self._curves = dict(curves)
        self._clear_selection()
        self._rebuild_managers()

    def update_curve(self, curve: FCurve) -> None:
        self._finish_drag()
        self._curves[curve.id] = curve
        self._rebuild_managers()

    def remove_curve(self, curve_id: str) -> None:
        self._finish_drag()
        del self._curves[curve_id]
        self._selected_keys = [k for k in self._selected_keys if k.curve_id != curve_id]
        self._selected_tangents = [t for t in self._selected_tangents if t.curve_id != curve_id]
        self._rebuild_managers()

    def set_curve_visible(self, curve_id: str, visible: bool) -> None:
        """Change curve visibility and notify selection eligibility listeners."""
        self._curves[curve_id].visible = visible
        self._rebuild_managers()
        self._emit_selection_changed()

    def set_curve_color(self, curve_id: str, color: int) -> None:
        self._curves[curve_id].color = color
        self._rebuild_managers()

    def set_curve_infinity(
        self, curve_id: str, pre_infinity: InfinityType | None = None, post_infinity: InfinityType | None = None
    ) -> None:
        curve = self._curves[curve_id]
        if pre_infinity is not None:
            curve.pre_infinity = pre_infinity
        if post_infinity is not None:
            curve.post_infinity = post_infinity
        if curve_id in self._managers:
            self._managers[curve_id].sync()
        self._notify_curve_changed(curve_id)

    # ── Public: editing ─────────────────────────────────────────────────────

    @property
    def is_inserting_key(self) -> bool:
        """Whether the active manager owns a key inserted by the current press."""
        manager = self._managers.get(self._dragging_curve_id)
        return manager is not None and manager.is_inserting_key

    def update_insertion(self, position: tuple[float, float] | None) -> None:
        """Advance insertion in canvas-local pixels, or finish without moving."""
        manager = self._managers.get(self._dragging_curve_id)
        if manager:
            manager.update_insertion(position)

    def prepare_key_offset(
        self,
        baseline: dict[str, list[FCurveKey]],
        selected_keys: tuple[KeyReference, ...],
        *,
        time_offset: float = 0.0,
        value_offset: float = 0.0,
    ) -> dict[KeyReference, tuple[float, float]]:
        """Prepare one shared, clamped offset without modifying curves.

        Args:
            baseline: Copies of every key, including tangents, in each participating curve.
            selected_keys: Key references captured at the start of the gesture.
            time_offset: Requested time displacement from the baseline.
            value_offset: Requested value displacement from the baseline.

        Returns:
            Target coordinates for unique selected keys on visible, unlocked curves.

        Raises:
            ValueError: If inputs, references, or baseline keys are invalid.
        """
        if not isfinite(time_offset) or not isfinite(value_offset):
            raise ValueError("Key offsets must be finite")
        selected = self._validate_key_baseline(baseline, selected_keys)
        time_lower, value_lower = -float("inf"), -float("inf")
        time_upper, value_upper = float("inf"), float("inf")
        for curve_id, indices in selected.items():
            keys = baseline[curve_id]
            bounds = self.bounds_for(curve_id)
            for index in indices:
                key = keys[index]
                minimum, maximum = bounds.time_min, bounds.time_max
                # Keep the validated baseline time feasible when a neighbor gap differs only by roundoff.
                if index > 0 and index - 1 not in indices:
                    minimum = max(minimum, min(key.time, keys[index - 1].time + self._threshold))
                if index + 1 < len(keys) and index + 1 not in indices:
                    maximum = min(maximum, max(key.time, keys[index + 1].time - self._threshold))
                lower, upper = self._key_offset_limits(key.time, minimum, maximum)
                time_lower, time_upper = max(time_lower, lower), min(time_upper, upper)
                lower, upper = self._key_offset_limits(key.value, bounds.value_min, bounds.value_max)
                value_lower, value_upper = max(value_lower, lower), min(value_upper, upper)
        if time_lower > time_upper or value_lower > value_upper:
            raise ValueError("Selected keys have no valid shared movement interval")
        time_offset = max(time_lower, min(time_upper, time_offset))
        value_offset = max(value_lower, min(value_upper, value_offset))
        time_offset = self._representable_time_offset(baseline, selected, time_offset, time_lower, time_upper)
        positions = {
            reference: (
                baseline[reference.curve_id][reference.key_index].time + time_offset,
                baseline[reference.curve_id][reference.key_index].value + value_offset,
            )
            for reference in selected_keys
            if reference.curve_id in selected
        }
        if any(not isfinite(value) for position in positions.values() for value in position):
            raise ValueError("Resulting key positions must be finite")
        return positions

    def _representable_time_offset(
        self,
        baseline: dict[str, list[FCurveKey]],
        selected: dict[str, set[int]],
        offset: float,
        lower: float,
        upper: float,
    ) -> float:
        """Keep one shared offset when translation roundoff narrows a minimum time gap."""
        if self._time_offset_is_valid(baseline, selected, offset):
            return offset
        candidates = {
            (baseline[curve_id][index].time + offset) - baseline[curve_id][index].time
            for curve_id, indices in selected.items()
            for index in indices
        }
        # shortcut: Rare roundoff fallback is quadratic in selected keys; optimize for measured dense-selection stalls.
        for candidate in sorted(candidates, reverse=offset > 0):
            if (
                candidate != offset
                and lower <= candidate <= upper
                and min(0.0, offset) <= candidate <= max(0.0, offset)
                and self._time_offset_is_valid(baseline, selected, candidate)
            ):
                return candidate
        raise ValueError("Requested time offset cannot be represented safely")

    def _time_offset_is_valid(
        self, baseline: dict[str, list[FCurveKey]], selected: dict[str, set[int]], offset: float
    ) -> bool:
        """Check translated times against shared minimum-gap and exact property limits."""
        for curve_id, indices in selected.items():
            times = [
                key.time + offset if index in indices else key.time for index, key in enumerate(baseline[curve_id])
            ]
            bounds = self.bounds_for(curve_id)
            if any(not isfinite(time) or not bounds.time_min <= time <= bounds.time_max for time in times):
                return False
            if any(not is_key_time_gap_valid(left, right, self._threshold) for left, right in zip(times, times[1:])):
                return False
        return True

    @staticmethod
    def _key_offset_limits(value: float, minimum: float, maximum: float) -> tuple[float, float]:
        """Return offset bounds whose reconstructed coordinates remain inside the limits."""
        lower, upper = minimum - value, maximum - value
        # Subtraction followed by addition can round one bit beyond a stationary neighbor or property limit.
        if value + lower < minimum:
            lower = nextafter(lower, float("inf"))
        if value + upper > maximum:
            upper = nextafter(upper, -float("inf"))
        return lower, upper

    def set_key_positions(
        self,
        positions: dict[KeyReference, tuple[float, float]],
        *,
        baseline: dict[str, list[FCurveKey]],
    ) -> None:
        """Apply validated positions together and commit each changed curve once.

        Args:
            positions: Target coordinates, normally returned by ``prepare_key_offset``.
            baseline: The same full-curve snapshot for every update in a gesture.
                Callers must stop the gesture if source curves or key identities change.

        Raises:
            ValueError: If references, baseline data, or resulting positions are invalid.

        Live key objects and lists retain their identity. All candidates are processed
        before live mutation; all live curves are updated before persistence callbacks,
        which all finish before curve-change events are emitted.
        """
        selected = self._validate_key_baseline(baseline, tuple(positions))
        if sum(len(indices) for indices in selected.values()) != len(positions):
            raise ValueError("Cannot edit hidden or locked curves")
        candidates: dict[str, FCurve] = {}
        for curve_id, indices in selected.items():
            curve = self._curves[curve_id]
            candidate = replace(curve, keys=[replace(key) for key in baseline[curve_id]])
            changed = False
            for index, key in enumerate(candidate.keys):
                current = curve.keys[index]
                if index in indices:
                    position = positions[KeyReference(curve_id, index)]
                    if len(position) != 2 or not all(isfinite(value) for value in position):
                        raise ValueError("Key positions must contain two finite coordinates")
                    key.time, key.value = position
                    changed |= (current.time, current.value) != position
                elif (current.time, current.value) != (key.time, key.value):
                    raise ValueError("An unselected key changed since the gesture began")
            self._validate_curve_keys(curve_id, candidate.keys)
            if changed:
                candidates[curve_id] = candidate
        for curve_id, candidate in candidates.items():
            coordinates = [(key.time, key.value) for key in candidate.keys]
            process_curve(candidate, self.bounds_for(curve_id), self._threshold)
            self._validate_curve_keys(curve_id, candidate.keys)
            if coordinates != [(key.time, key.value) for key in candidate.keys]:
                raise ValueError("Curve processing changed validated key positions")
        for curve_id, candidate in candidates.items():
            for current, key in zip(self._curves[curve_id].keys, candidate.keys):
                current.time = key.time
                current.value = key.value
                current.in_tangent_x = key.in_tangent_x
                current.in_tangent_y = key.in_tangent_y
                current.out_tangent_x = key.out_tangent_x
                current.out_tangent_y = key.out_tangent_y
                current.in_tangent_type = key.in_tangent_type
                current.out_tangent_type = key.out_tangent_type
                current.tangent_broken = key.tangent_broken
            if curve_id in self._managers:
                self._managers[curve_id].request_position_sync()
        self._notify_curve_changed(*candidates)

    def _validate_key_baseline(
        self, baseline: dict[str, list[FCurveKey]], references: tuple[KeyReference, ...]
    ) -> dict[str, set[int]]:
        """Validate captured references and snapshots, returning eligible index sets."""
        selected: dict[str, set[int]] = {}
        for reference in references:
            if not isinstance(reference, KeyReference) or not isinstance(reference.key_index, int):
                raise ValueError(f"Invalid key reference: {reference}")
            curve = self._curves.get(reference.curve_id)
            if curve is None or not 0 <= reference.key_index < len(curve.keys):
                raise ValueError(f"Invalid key reference: {reference}")
            if curve.visible and not curve.locked:
                selected.setdefault(reference.curve_id, set()).add(reference.key_index)
        for curve_id in selected:
            keys = baseline.get(curve_id)
            current = self._curves[curve_id].keys
            if not isinstance(keys, list) or len(keys) != len(current):
                raise ValueError(f"Missing or stale baseline for curve '{curve_id}'")
            if any(key is live for key, live in zip(keys, current)):
                raise ValueError("Baseline keys must be copies of the live keys")
            self._validate_curve_keys(curve_id, keys)
        return selected

    def _validate_curve_keys(self, curve_id: str, keys: list[FCurveKey]) -> None:
        """Reject invalid key data instead of repairing it during numeric editing."""
        bounds = self.bounds_for(curve_id)
        if (
            not isfinite(self._threshold)
            or self._threshold < 0
            or any(isnan(value) for value in (bounds.time_min, bounds.time_max, bounds.value_min, bounds.value_max))
            or bounds.time_min > bounds.time_max
            or bounds.value_min > bounds.value_max
        ):
            raise ValueError(f"Invalid bounds for curve '{curve_id}'")
        for index, key in enumerate(keys):
            if not isinstance(key, FCurveKey) or not all(
                isfinite(value)
                for value in (
                    key.time,
                    key.value,
                    key.in_tangent_x,
                    key.in_tangent_y,
                    key.out_tangent_x,
                    key.out_tangent_y,
                )
            ):
                raise ValueError(f"Non-finite or malformed key in curve '{curve_id}'")
            if (
                not bounds.time_min <= key.time <= bounds.time_max
                or not bounds.value_min <= key.value <= bounds.value_max
            ):
                raise ValueError(f"Key outside property bounds in curve '{curve_id}'")
            if not isinstance(key.in_tangent_type, TangentType) or not isinstance(key.out_tangent_type, TangentType):
                raise ValueError(f"Invalid tangent type in curve '{curve_id}'")
            if index and not is_key_time_gap_valid(keys[index - 1].time, key.time, self._threshold):
                raise ValueError(f"Invalid key ordering in curve '{curve_id}'")

    def add_key(self, curve_id: str, time: float, value: float) -> FCurveKey:
        """Insert a key and process bounds, spacing, and tangents before notifying listeners.

        Returns:
            The inserted key with its processed coordinates and tangent defaults.

        Raises:
            KeyError: If the curve does not exist.
            ValueError: If the curve is locked.
        """
        self._finish_drag()
        curve = self._curves[curve_id]
        if curve.locked:
            raise ValueError(f"Curve '{curve_id}' is locked")
        insert_idx = sum(1 for k in curve.keys if k.time <= time)
        new_key = FCurveKey(time=time, value=value)
        curve.keys.insert(insert_idx, new_key)
        process_curve(curve, self.bounds_for(curve_id), self._threshold)
        self._rebuild_managers()
        self.__on_key_added(
            KeyAddedEvent(
                curve_id=curve_id,
                key_index=insert_idx,
                time=new_key.time,
                value=new_key.value,
            )
        )
        self._notify_curve_changed(curve_id)
        return new_key

    def delete_selected_keys(self) -> int:
        """Delete selected keys on visible, unlocked curves, retaining at least one key per curve.

        Returns:
            Number of keys deleted.
        """
        self._finish_drag()
        if not self._selected_keys:
            return 0
        by_curve: dict[str, list[int]] = {}
        for ref in self.editable_selected_keys:
            by_curve.setdefault(ref.curve_id, []).append(ref.key_index)
        deleted = 0
        affected: set[str] = set()
        for curve_id, indices in by_curve.items():
            curve = self._curves[curve_id]
            max_del = len(curve.keys) - 1
            count = 0
            for idx in sorted(indices, reverse=True):
                if count >= max_del or idx >= len(curve.keys):
                    continue
                key = curve.keys[idx]
                del curve.keys[idx]
                self.__on_key_deleted(KeyDeletedEvent(curve_id=curve_id, key_index=idx, time=key.time, value=key.value))
                deleted += 1
                count += 1
                affected.add(curve_id)
        for cid in affected:
            self._notify_curve_changed(cid)
        self._clear_selection()
        self._rebuild_managers()
        return deleted

    def set_key_tangent_type(
        self,
        curve_id: str,
        key_index: int,
        in_tangent_type: TangentType | None = None,
        out_tangent_type: TangentType | None = None,
        in_tangent_x: float | None = None,
        in_tangent_y: float | None = None,
        out_tangent_x: float | None = None,
        out_tangent_y: float | None = None,
    ) -> None:
        curve = self._curves[curve_id]
        key = curve.keys[key_index]
        if in_tangent_type is not None:
            key.in_tangent_type = in_tangent_type
        if out_tangent_type is not None:
            key.out_tangent_type = out_tangent_type
        if in_tangent_x is not None:
            key.in_tangent_x = in_tangent_x
        if in_tangent_y is not None:
            key.in_tangent_y = in_tangent_y
        if out_tangent_x is not None:
            key.out_tangent_x = out_tangent_x
        if out_tangent_y is not None:
            key.out_tangent_y = out_tangent_y
        process_curve(curve, self.bounds_for(curve_id), self._threshold)
        if curve_id in self._managers:
            self._managers[curve_id].sync()
        self._notify_curve_changed(curve_id)

    def set_selected_keys_tangent_type(
        self, tangent_type: TangentType, in_tangent: bool = True, out_tangent: bool = True
    ) -> int:
        """Set selected tangent types according to each editable key's link state.

        Linked keys apply the requested type to both sides; broken keys apply it
        only to requested sides. Existing STEP and CUSTOM processing still applies.
        Requesting neither side leaves data unchanged and sends no notifications.

        Args:
            tangent_type: Tangent type to apply.
            in_tangent: Whether to request the incoming side.
            out_tangent: Whether to request the outgoing side.

        Returns:
            Number of selected keys processed on visible, unlocked curves, or zero
            when neither side is requested.
        """
        if not self._selected_keys or not (in_tangent or out_tangent):
            return 0
        modified = 0
        affected: set[str] = set()
        for ref in self.editable_selected_keys:
            curve = self._curves[ref.curve_id]
            key = curve.keys[ref.key_index]
            if in_tangent or not key.tangent_broken:
                key.in_tangent_type = tangent_type
            if out_tangent or not key.tangent_broken:
                key.out_tangent_type = tangent_type
            modified += 1
            affected.add(ref.curve_id)
        for cid in affected:
            process_curve(self._curves[cid], self.bounds_for(cid), self._threshold)
            if cid in self._managers:
                self._managers[cid].sync()
            self._notify_curve_changed(cid)
        return modified

    def set_selected_keys_tangent_broken(self, broken: bool, source: str = "average") -> int:
        """Link or break tangents on selected keys of visible, unlocked curves."""
        if not self._selected_keys:
            return 0
        modified = 0
        affected: set[str] = set()
        for ref in self.editable_selected_keys:
            curve = self._curves[ref.curve_id]
            key = curve.keys[ref.key_index]
            if broken and not key.tangent_broken:
                key.tangent_broken = True
                if key.in_tangent_type == TangentType.STEP:
                    key.in_tangent_type = TangentType.AUTO
                process_curve(curve, self.bounds_for(ref.curve_id), self._threshold)
                modified += 1
                affected.add(ref.curve_id)
            elif not broken and key.tangent_broken:
                key.tangent_broken = False
                src_type = key.out_tangent_type if source != "in" else key.in_tangent_type
                if src_type == TangentType.STEP:
                    key.in_tangent_type = TangentType.AUTO
                    key.out_tangent_type = TangentType.STEP
                else:
                    key.in_tangent_type = src_type
                    key.out_tangent_type = src_type
                tangent_positions = {
                    (ref.key_index, source == "in"): (
                        key.in_tangent_x if source == "in" else key.out_tangent_x,
                        key.in_tangent_y if source == "in" else key.out_tangent_y,
                    )
                }
                process_curve(
                    curve, self.bounds_for(ref.curve_id), self._threshold, tangent_positions=tangent_positions
                )
                modified += 1
                affected.add(ref.curve_id)
        for cid in affected:
            if cid in self._managers:
                self._managers[cid].sync()
            self._notify_curve_changed(cid)
        return modified

    # ── Public: selection ───────────────────────────────────────────────────

    @property
    def selected_keys(self) -> list[KeyReference]:
        return list(self._selected_keys)

    @property
    def editable_selected_keys(self) -> tuple[KeyReference, ...]:
        """Return distinct valid selected keys on visible, unlocked curves."""
        return tuple(
            reference
            for reference in dict.fromkeys(self._selected_keys)
            if (curve := self._curves.get(reference.curve_id)) is not None
            and curve.visible
            and not curve.locked
            and 0 <= reference.key_index < len(curve.keys)
        )

    @property
    def selected_tangents(self) -> list[TangentReference]:
        return list(self._selected_tangents)

    @property
    def selection(self) -> SelectionInfo:
        return SelectionInfo(keys=list(self._selected_keys), tangents=list(self._selected_tangents))

    def get_selection_tangent_type(self) -> tuple[TangentType | None, TangentType | None]:
        if not self._selected_keys:
            return (None, None)
        in_types: set[TangentType] = set()
        out_types: set[TangentType] = set()
        for ref in self._selected_keys:
            curve = self._curves.get(ref.curve_id)
            if not curve or ref.key_index >= len(curve.keys):
                continue
            key = curve.keys[ref.key_index]
            in_types.add(key.in_tangent_type)
            out_types.add(key.out_tangent_type)
        return (in_types.pop() if len(in_types) == 1 else None, out_types.pop() if len(out_types) == 1 else None)

    def select_keys(self, refs: list[KeyReference]) -> None:
        self._selected_keys = list(refs)
        self._selected_tangents = []
        self._sync_selection_to_managers()
        self._emit_selection_changed()

    def select_all(self) -> None:
        self._selected_keys = [
            KeyReference(curve_id=c.id, key_index=i)
            for c in self._curves.values()
            if c.visible and not c.locked
            for i in range(len(c.keys))
        ]
        self._selected_tangents = []
        self._sync_selection_to_managers()
        self._emit_selection_changed()

    def clear_selection(self) -> None:
        self._clear_selection()

    def _clear_selection(self) -> None:
        self._selected_keys = []
        self._selected_tangents = []
        self._sync_selection_to_managers()
        self._emit_selection_changed()

    def _sync_selection_to_managers(self) -> None:
        selected_per_curve: dict[str, set[int]] = {}
        for ref in self._selected_keys:
            selected_per_curve.setdefault(ref.curve_id, set()).add(ref.key_index)
        for cid, mgr in self._managers.items():
            mgr.set_selection(selected_per_curve.get(cid, set()))

    # ── Events (subscribe API) ──────────────────────────────────────────────

    def subscribe_key_changed(self, callback: Callable[[KeyChangedEvent], None]) -> _EventSubscription:
        return _EventSubscription(self.__on_key_changed, callback)

    def subscribe_key_added(self, callback: Callable[[KeyAddedEvent], None]) -> _EventSubscription:
        return _EventSubscription(self.__on_key_added, callback)

    def subscribe_key_deleted(self, callback: Callable[[KeyDeletedEvent], None]) -> _EventSubscription:
        return _EventSubscription(self.__on_key_deleted, callback)

    def subscribe_tangent_changed(self, callback: Callable[[TangentChangedEvent], None]) -> _EventSubscription:
        return _EventSubscription(self.__on_tangent_changed, callback)

    def subscribe_selection_changed(self, callback: Callable[[SelectionChangedEvent], None]) -> _EventSubscription:
        return _EventSubscription(self.__on_selection_changed, callback)

    def subscribe_curve_changed(self, callback: Callable[[str], None]) -> _EventSubscription:
        return _EventSubscription(self.__on_curve_changed, callback)

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def destroy(self) -> None:
        self._destroy_managers()
        self._curves.clear()
        self._selected_keys.clear()
        self._selected_tangents.clear()
        self._stack = None
        for ev in (
            self.__on_key_changed,
            self.__on_key_added,
            self.__on_key_deleted,
            self.__on_tangent_changed,
            self.__on_selection_changed,
            self.__on_curve_changed,
        ):
            ev.clear()

    # ── Internal: managers ──────────────────────────────────────────────────

    def _rebuild_managers(self) -> None:
        """Rebuild visible curve widgets and restore their key selection highlighting."""
        self._destroy_managers()
        if not self._stack:
            return
        with self._stack:
            # Handles must claim an overlapping press before any segment can insert.
            handle_stack = ui.ZStack()
            segment_stack = ui.ZStack()
            for curve in self._curves.values():
                if not curve.visible:
                    continue
                cid = curve.id
                mgr = CurveWidgetsManager(
                    curve,
                    self._viewport,
                    self.bounds_for(cid),
                    curve_color=curve.color,
                    key_size=self._key_size,
                    tangent_size=self._tangent_size,
                    placer_size=self._placer_size,
                    x_flip_threshold=self._threshold,
                    on_key_pressed=lambda idx, mod, _cid=cid: self._handle_key_pressed(_cid, idx, mod),
                    on_key_released=lambda _idx: self._finish_drag(),
                    on_key_moved=lambda idx, _cid=cid: self._handle_key_moved(_cid, idx),
                    on_tangent_moved=lambda idx, is_in, _cid=cid: self._handle_tangent_moved(_cid, idx, is_in),
                    on_tangent_released=lambda _idx, _is_in: self._finish_drag(),
                    on_selection_changed=lambda mod, _cid=cid: self._handle_selection_changed(_cid, mod),
                    on_insert_started=lambda _cid=cid: self._handle_drag_started(_cid),
                    on_key_added=lambda idx, _cid=cid: self._handle_key_added(_cid, idx),
                    on_key_dragged=lambda idx, position, _cid=cid: self._handle_key_dragged(_cid, idx, position),
                )
                mgr.build(handle_stack, segment_stack)
                self._managers[cid] = mgr
        self._sync_selection_to_managers()

    def _destroy_managers(self) -> None:
        self._finish_drag()
        for mgr in self._managers.values():
            mgr.destroy()
        self._managers.clear()
        if self._stack:
            self._stack.clear()

    # ── Internal: callbacks from CurveWidgetsManager ────────────────────────

    def _handle_drag_started(self, curve_id: str) -> bool:
        """Claim a press and snapshot its edit before the manager changes keys."""
        if self._dragging_curve_id is not None:
            return False
        self._dragging_curve_id = curve_id
        if self._on_drag_started:
            self._on_drag_started(curve_id)
        return True

    def _finish_drag(self) -> None:
        """Finish the active gesture and every participating edit transaction once."""
        curve_id, self._dragging_curve_id = self._dragging_curve_id, None
        curve_ids = tuple(dict.fromkeys((curve_id, *self._key_drag_baseline)))
        self._key_drag_selection = ()
        self._key_drag_baseline = {}
        if curve_id is None:
            return

        with ExitStack() as edits:
            if self._on_drag_ended:
                for participating_id in reversed(curve_ids):
                    edits.callback(self._on_drag_ended, participating_id)
            manager = self._managers.get(curve_id)
            if manager is not None:
                manager.update_insertion(None)

    def _handle_key_added(self, curve_id: str, key_index: int) -> None:
        """Publish and select a native insertion before committing its payload."""
        key = self._curves[curve_id].keys[key_index]
        self.__on_key_added(KeyAddedEvent(curve_id=curve_id, key_index=key_index, time=key.time, value=key.value))
        self.select_keys([KeyReference(curve_id=curve_id, key_index=key_index)])
        self._notify_curve_changed(curve_id)

    def _handle_selection_changed(self, source_curve_id: str, mod: int) -> None:
        multi = bool(mod & carb.input.KEYBOARD_MODIFIER_FLAG_SHIFT)
        if not multi:
            for cid, mgr in self._managers.items():
                if cid != source_curve_id:
                    mgr.set_selection(set())
        self._selected_keys = [
            KeyReference(curve_id=cid, key_index=i)
            for cid, mgr in self._managers.items()
            for i in mgr.get_selected_indices()
        ]
        self._selected_tangents = []
        self._emit_selection_changed()

    def _handle_key_pressed(self, curve_id: str, key_index: int, mod: int) -> None:
        """Claim native handle presses before any overlapping curve can insert."""
        self.update_insertion(None)
        self._handle_drag_started(curve_id)

    def _handle_key_dragged(self, curve_id: str, key_index: int, position: tuple[float, float]) -> None:
        """Translate the press-time selection by one shared, constrained pointer offset."""
        if curve_id != self._dragging_curve_id:
            return
        try:
            if not self._key_drag_baseline:
                # Native selection follows the press callback but precedes the first movement.
                self._key_drag_selection = self.editable_selected_keys
                if KeyReference(curve_id, key_index) not in self._key_drag_selection:
                    return
                for participating_id in dict.fromkeys(
                    (curve_id, *(reference.curve_id for reference in self._key_drag_selection))
                ):
                    self._key_drag_baseline[participating_id] = [
                        replace(key) for key in self._curves[participating_id].keys
                    ]
                    if participating_id != curve_id and self._on_drag_started:
                        self._on_drag_started(participating_id)
            key = self._key_drag_baseline[curve_id][key_index]
            start_x, start_y = self._viewport.model_to_pixel(key.time, key.value)
            positions = self.prepare_key_offset(
                self._key_drag_baseline,
                self._key_drag_selection,
                time_offset=(position[0] - start_x) / self._viewport.time_scale,
                value_offset=(start_y - position[1]) / self._viewport.value_scale,
            )
            changes = []
            for reference, (time, value) in positions.items():
                current = self._curves[reference.curve_id].keys[reference.key_index]
                if (current.time, current.value) != (time, value):
                    changes.append(
                        KeyChangedEvent(
                            curve_id=reference.curve_id,
                            key_index=reference.key_index,
                            old_time=current.time,
                            old_value=current.value,
                            new_time=time,
                            new_value=value,
                        )
                    )
            self.set_key_positions(positions, baseline=self._key_drag_baseline)
            for change in changes:
                self.__on_key_changed(change)
        except Exception:
            self._finish_drag()
            raise

    def _handle_key_moved(self, curve_id: str, key_index: int) -> None:
        self._handle_drag_started(curve_id)

        curve = self._curves.get(curve_id)
        if not curve or key_index >= len(curve.keys):
            return
        key = curve.keys[key_index]
        self.__on_key_changed(
            KeyChangedEvent(
                curve_id=curve_id,
                key_index=key_index,
                old_time=key.time,
                old_value=key.value,
                new_time=key.time,
                new_value=key.value,
            )
        )
        self._notify_curve_changed(curve_id)

    def _handle_tangent_moved(self, curve_id: str, key_index: int, is_in: bool) -> None:
        self._handle_drag_started(curve_id)

        curve = self._curves.get(curve_id)
        if not curve or key_index >= len(curve.keys):
            return
        key = curve.keys[key_index]
        x = key.in_tangent_x if is_in else key.out_tangent_x
        y = key.in_tangent_y if is_in else key.out_tangent_y
        self.__on_tangent_changed(
            TangentChangedEvent(
                curve_id=curve_id,
                key_index=key_index,
                is_in_tangent=is_in,
                old_x=x,
                old_y=y,
                new_x=x,
                new_y=y,
            )
        )
        self._notify_curve_changed(curve_id)

    # ── Internal: notifications ─────────────────────────────────────────────

    def _notify_curve_changed(self, *curve_ids: str) -> None:
        """Persist all changed curves before notifying subscribers."""
        for curve_id in curve_ids:
            if self._on_commit and curve_id in self._curves:
                self._on_commit(curve_id, self._curves[curve_id])
        for curve_id in curve_ids:
            self.__on_curve_changed(curve_id)

    def _emit_selection_changed(self) -> None:
        self.__on_selection_changed(
            SelectionChangedEvent(
                selected_keys=tuple(self._selected_keys),
                selected_tangents=tuple(self._selected_tangents),
            )
        )

    @property
    def keyframe_clamp_threshold(self) -> float:
        return self._threshold

    @keyframe_clamp_threshold.setter
    def keyframe_clamp_threshold(self, value: float) -> None:
        self._threshold = max(0.0, value)
        for mgr in self._managers.values():
            mgr.x_flip_threshold = self._threshold
