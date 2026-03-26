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
from ._internal.math import process_curve
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
        self._curves = dict(curves)
        self._clear_selection()
        self._rebuild_managers()

    def update_curve(self, curve: FCurve) -> None:
        self._curves[curve.id] = curve
        self._rebuild_managers()

    def remove_curve(self, curve_id: str) -> None:
        del self._curves[curve_id]
        self._selected_keys = [k for k in self._selected_keys if k.curve_id != curve_id]
        self._selected_tangents = [t for t in self._selected_tangents if t.curve_id != curve_id]
        self._rebuild_managers()

    def set_curve_visible(self, curve_id: str, visible: bool) -> None:
        self._curves[curve_id].visible = visible
        self._rebuild_managers()

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

    def add_key(self, curve_id: str, time: float, value: float) -> FCurveKey:
        curve = self._curves[curve_id]
        if curve.locked:
            raise ValueError(f"Curve '{curve_id}' is locked")
        insert_idx = sum(1 for k in curve.keys if k.time <= time)
        new_key = FCurveKey(time=time, value=value)
        curve.keys.insert(insert_idx, new_key)
        self.__on_key_added(KeyAddedEvent(curve_id=curve_id, key_index=insert_idx, time=time, value=value))
        self._notify_curve_changed(curve_id)
        self._rebuild_managers()
        return new_key

    def delete_selected_keys(self) -> int:
        if not self._selected_keys:
            return 0
        by_curve: dict[str, list[int]] = {}
        for ref in self._selected_keys:
            by_curve.setdefault(ref.curve_id, []).append(ref.key_index)
        deleted = 0
        affected: set[str] = set()
        for curve_id, indices in by_curve.items():
            curve = self._curves.get(curve_id)
            if not curve or curve.locked:
                continue
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
        if not self._selected_keys:
            return 0
        modified = 0
        affected: set[str] = set()
        for ref in self._selected_keys:
            curve = self._curves.get(ref.curve_id)
            if not curve or curve.locked or ref.key_index >= len(curve.keys):
                continue
            key = curve.keys[ref.key_index]
            if in_tangent:
                key.in_tangent_type = tangent_type
            if out_tangent:
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
        if not self._selected_keys:
            return 0
        modified = 0
        affected: set[str] = set()
        for ref in self._selected_keys:
            curve = self._curves.get(ref.curve_id)
            if not curve or curve.locked or ref.key_index >= len(curve.keys):
                continue
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

    # ── Public: viewport fitting ────────────────────────────────────────────

    def fit_to_data(self) -> None:
        times, values = [], []
        for c in self._curves.values():
            if not c.visible:
                continue
            for k in c.keys:
                times.append(k.time)
                values.append(k.value)
        if not times:
            return
        pt = (max(times) - min(times)) * 0.1 or 0.1
        pv = (max(values) - min(values)) * 0.1 or 0.1
        self.time_range = (min(times) - pt, max(times) + pt)
        self.value_range = (min(values) - pv, max(values) + pv)

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
        self._destroy_managers()
        if not self._stack:
            return
        with self._stack:
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
                    on_key_released=lambda idx, _cid=cid: self._handle_key_released(_cid, idx),
                    on_key_moved=lambda idx, _cid=cid: self._handle_key_moved(_cid, idx),
                    on_tangent_moved=lambda idx, is_in, _cid=cid: self._handle_tangent_moved(_cid, idx, is_in),
                    on_tangent_released=lambda idx, is_in, _cid=cid: self._handle_tangent_released(_cid, idx, is_in),
                    on_selection_changed=lambda mod, _cid=cid: self._handle_selection_changed(_cid, mod),
                )
                mgr.build(self._stack)
                self._managers[cid] = mgr

    def _destroy_managers(self) -> None:
        for mgr in self._managers.values():
            mgr.destroy()
        self._managers.clear()
        if self._stack:
            self._stack.clear()

    # ── Internal: callbacks from CurveWidgetsManager ────────────────────────

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
        self._dragging_curve_id = None

    def _handle_key_moved(self, curve_id: str, key_index: int) -> None:
        if self._dragging_curve_id is None:
            self._dragging_curve_id = curve_id
            if self._on_drag_started:
                self._on_drag_started(curve_id)

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

    def _handle_key_released(self, curve_id: str, key_index: int) -> None:
        if self._dragging_curve_id:
            cid = self._dragging_curve_id
            self._dragging_curve_id = None
            if self._on_drag_ended:
                self._on_drag_ended(cid)

    def _handle_tangent_moved(self, curve_id: str, key_index: int, is_in: bool) -> None:
        if self._dragging_curve_id is None:
            self._dragging_curve_id = curve_id
            if self._on_drag_started:
                self._on_drag_started(curve_id)

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

    def _handle_tangent_released(self, curve_id: str, key_index: int, is_in: bool) -> None:
        if self._dragging_curve_id:
            cid = self._dragging_curve_id
            self._dragging_curve_id = None
            if self._on_drag_ended:
                self._on_drag_ended(cid)

    # ── Internal: notifications ─────────────────────────────────────────────

    def _notify_curve_changed(self, curve_id: str) -> None:
        if self._on_commit and curve_id in self._curves:
            self._on_commit(curve_id, self._curves[curve_id])
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
