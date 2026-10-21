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

Controller that spawns HandleWidgets + SegmentWidgets from an FCurve model.
Syncs widgets to model state: creates/destroys on key add/remove, moves on key drag.
Tangent handles only shown for SMOOTH/CUSTOM types on selected keyframes.

Each HandleWidget/SegmentWidget wraps its omni.ui widgets in its own ZStack.
destroy() calls container.clear() to remove children without nuking the canvas.
Selection changes are deferred to next frame (can't addChild during draw).
"""

from __future__ import annotations

from math import hypot, isclose, isfinite
from typing import TYPE_CHECKING

import carb.input
import omni.kit.app
from omni import ui

from .handle_widget import HandleWidget
from .infinity_curve_widget import InfinityCurveWidget
from .math import Vector2, bezier_parameter_at_time, lerp, process_curve
from .segment_widget import SegmentMode, SegmentWidget

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..model import CurveBounds, FCurve
    from .viewport import ViewportState

from ..model import FCurveKey, TangentType

__all__ = ["CurveWidgetsManager"]

_DEFAULT_X_FLIP_THRESHOLD = 0.001
_INSERTION_HIT_RADIUS_LOGICAL_PIXELS = 6.0
_KEY_POSITION_ROUND_TRIP_TOLERANCE_LOCAL_PIXELS = 1e-9
_DRAGGABLE_TANGENT_TYPES = {TangentType.SMOOTH, TangentType.CUSTOM}


def _tangent_visible(tangent_type: TangentType, key_selected: bool) -> bool:
    return key_selected and tangent_type in _DRAGGABLE_TANGENT_TYPES


class _KeyGroup:
    __slots__ = ("key_ref", "key_h", "in_h", "out_h", "in_seg", "out_seg")

    def __init__(self, key_ref: FCurveKey, key_h: HandleWidget):
        self.key_ref = key_ref
        self.key_h = key_h
        self.in_h: HandleWidget | None = None
        self.out_h: HandleWidget | None = None
        self.in_seg: SegmentWidget | None = None
        self.out_seg: SegmentWidget | None = None

    def destroy_tangents(self) -> None:
        if self.in_seg:
            self.in_seg.destroy()
            self.in_seg = None
        if self.in_h:
            self.in_h.destroy()
            self.in_h = None
        if self.out_seg:
            self.out_seg.destroy()
            self.out_seg = None
        if self.out_h:
            self.out_h.destroy()
            self.out_h = None

    def destroy(self) -> None:
        self.destroy_tangents()
        self.key_h.destroy()


class CurveWidgetsManager:
    def __init__(
        self,
        curve: FCurve,
        viewport: ViewportState,
        bounds: CurveBounds,
        curve_color: int,
        key_size: int = 8,
        tangent_size: int = 6,
        placer_size: int = 20,
        x_flip_threshold: float = _DEFAULT_X_FLIP_THRESHOLD,
        on_key_pressed: Callable[[int, int], None] | None = None,
        on_key_released: Callable[[int], None] | None = None,
        on_key_moved: Callable[[int], None] | None = None,
        on_tangent_moved: Callable[[int, bool], None] | None = None,
        on_tangent_released: Callable[[int, bool], None] | None = None,
        on_selection_changed: Callable[[int], None] | None = None,
        on_insert_started: Callable[[], bool] | None = None,
        on_key_added: Callable[[int], None] | None = None,
        on_key_dragged: Callable[[int, tuple[float, float]], None] | None = None,
    ):
        self._curve = curve
        self._vp = viewport
        self._bounds = bounds
        self.x_flip_threshold = x_flip_threshold
        self._curve_color = curve_color
        self._key_size = key_size
        self._tangent_size = tangent_size
        self._placer_size = placer_size
        self._on_key_pressed = on_key_pressed
        self._on_key_released = on_key_released
        self._on_key_moved_cb = on_key_moved
        self._on_tangent_moved_cb = on_tangent_moved
        self._on_tangent_released_cb = on_tangent_released
        self._on_selection_changed_cb = on_selection_changed
        self._on_insert_started = on_insert_started
        self._on_key_added = on_key_added
        self._on_key_dragged = on_key_dragged

        self._stack: ui.ZStack | None = None
        self._segment_stack: ui.ZStack | None = None
        self._groups: list[_KeyGroup] = []
        self._curve_segments: list[SegmentWidget] = []
        self._pre_infinity: InfinityCurveWidget | None = None
        self._post_infinity: InfinityCurveWidget | None = None
        self._positions_dirty: bool = False
        self._tangents_dirty: bool = False
        self._topology_dirty = False
        self._selected_indices: set[int] = set()
        self._inserted_key: FCurveKey | None = None
        self._insert_pointer_offset = (0.0, 0.0)
        self._update_sub = None
        self._zoom: float = 1.0

    @property
    def key_handles(self) -> list[HandleWidget]:
        return [g.key_h for g in self._groups]

    @property
    def is_inserting_key(self) -> bool:
        """Whether a native segment press owns an inserted key."""
        return self._inserted_key is not None

    def build(self, stack: ui.ZStack, segment_stack: ui.ZStack | None = None) -> None:
        """Build handles and segments in their supplied input layers."""
        self._stack = stack
        self._segment_stack = segment_stack or stack
        process_curve(self._curve, self._bounds, self.x_flip_threshold)
        self._update_sub = (
            omni.kit.app.get_app()
            .get_update_event_stream()
            .create_subscription_to_pop(self._on_update, name="CurveWidgetsManager")
        )
        self._sync()

    def sync(self) -> None:
        self._sync()

    def request_position_sync(self) -> None:
        """Synchronize changed key positions on the next Kit update without rebuilding handles."""
        self._positions_dirty = True

    def sync_viewport(self) -> None:
        """Position-only sync for viewport changes (pan/zoom/resize). No rebuild."""
        self._sync_positions()
        self._apply_zoom()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = zoom
        self._apply_zoom()

    def _apply_zoom(self) -> None:
        placer_size = self._placer_size / self._zoom
        line_thickness = 1.5 / self._zoom
        for g in self._groups:
            g.key_h.set_size(placer_size)
            if g.in_h:
                g.in_h.set_size(placer_size)
            if g.out_h:
                g.out_h.set_size(placer_size)
            if g.in_seg:
                g.in_seg.set_line_thickness(line_thickness)
            if g.out_seg:
                g.out_seg.set_line_thickness(line_thickness)
        for seg in self._curve_segments:
            seg.set_line_thickness(line_thickness)
        for inf in (self._pre_infinity, self._post_infinity):
            if inf:
                inf.set_line_thickness(line_thickness)

    def set_selection(self, selected_indices: set[int]) -> None:
        """Cache selection immediately and apply it when key handles match the model."""
        self._selected_indices = set(selected_indices)
        if self._topology_dirty:
            return
        changed = False
        for i, g in enumerate(self._groups):
            should = i in selected_indices
            if g.key_h.selected != should:
                g.key_h.selected = should
                changed = True
        if changed:
            self._tangents_dirty = True

    def get_selected_indices(self) -> list[int]:
        """Return logical selection, including keys awaiting their first handle."""
        return sorted(self._selected_indices)

    def update_insertion(self, position: tuple[float, float] | None) -> None:
        """Move the inserted key in local pixels, or finish its original press."""
        if self._inserted_key is None:
            return
        if position is None:
            key, self._inserted_key = self._inserted_key, None
            if self._on_key_released:
                self._on_key_released(self._curve.keys.index(key))
        else:
            offset_x, offset_y = self._insert_pointer_offset
            self._move_key(self._inserted_key, (position[0] + offset_x, position[1] + offset_y))

    def destroy(self) -> None:
        self.update_insertion(None)
        self._update_sub = None
        for inf in (self._pre_infinity, self._post_infinity):
            if inf:
                inf.destroy()
        self._pre_infinity = self._post_infinity = None
        for seg in self._curve_segments:
            seg.destroy()
        self._curve_segments.clear()
        for g in self._groups:
            g.destroy()
        self._groups.clear()
        self._stack = None
        self._segment_stack = None

    def _on_update(self, _event) -> None:
        """Apply deferred topology, selection, and position changes outside drawing."""
        if self._topology_dirty:
            self._sync()
        if self._tangents_dirty:
            self._tangents_dirty = False
            self._rebuild_tangents()
            self._sync_positions()
            self._apply_zoom()
        if self._positions_dirty:
            self._positions_dirty = False
            self._sync_positions()

    # ── Core sync ───────────────────────────────────────────────────────────

    def _sync(self) -> None:
        """Synchronize handles before applying selection and rebuilding segments."""
        topology_changed = self._sync_topology(self._curve.keys)
        self._topology_dirty = False
        self.set_selection(self._selected_indices)
        if topology_changed:
            self._rebuild_curve_segments()
            self._rebuild_infinity()
        self._rebuild_tangents()
        self._tangents_dirty = False
        self._sync_positions()
        self._positions_dirty = False
        self._apply_zoom()

    def _sync_topology(self, keys: list) -> bool:
        changed = False
        i = 0
        while i < max(len(keys), len(self._groups)):
            cur_key = keys[i] if i < len(keys) else None
            cur_group = self._groups[i] if i < len(self._groups) else None
            if cur_group and cur_group.key_ref is cur_key:
                i += 1
                continue
            if cur_group:
                cur_group.destroy()
                self._groups.pop(i)
                changed = True
            if cur_key is not None:
                if self._stack:
                    with self._stack:
                        self._groups.insert(i, self._create_key_group(cur_key))
                    changed = True
                i += 1
        return changed

    def _sync_positions(self) -> None:
        for g in self._groups:
            key = g.key_ref
            g.key_h.set_position(*self._vp.model_to_pixel(key.time, key.value))
            if g.in_h:
                g.in_h.set_position(*self._vp.model_to_pixel(key.time + key.in_tangent_x, key.value + key.in_tangent_y))
            if g.out_h:
                g.out_h.set_position(
                    *self._vp.model_to_pixel(key.time + key.out_tangent_x, key.value + key.out_tangent_y)
                )
        self._update_curve_segments()
        self._update_infinity()

    def _rebuild_tangents(self) -> None:
        """Destroy + recreate tangent handles based on current selection/type.

        Safe to call from _on_update (outside draw pass) since addChild is allowed there.
        Each HandleWidget/SegmentWidget.destroy() calls container.clear() to free omni.ui widgets.
        """
        if not self._stack:
            return
        last = len(self._groups) - 1
        with self._stack:
            for i, g in enumerate(self._groups):
                key = g.key_ref
                selected = g.key_h.selected
                g.destroy_tangents()

                if i > 0 and _tangent_visible(key.in_tangent_type, selected):
                    itx, ity = self._vp.model_to_pixel(key.time + key.in_tangent_x, key.value + key.in_tangent_y)
                    g.in_h = HandleWidget(
                        itx,
                        ity,
                        color=self._curve_color,
                        handle_name="FCurveTangent",
                        handle_size=self._tangent_size,
                        on_moved=lambda h, _k=key: self._on_tangent_moved(h, _k, is_in=True),
                        on_pressed=lambda _h, mod, _k=key: self._on_handle_pressed(_k, mod),
                        on_released=lambda h, _m, _k=key: self._on_tangent_released(h, _k, is_in=True),
                    )
                    g.in_seg = SegmentWidget(
                        SegmentMode.LINE,
                        g.key_h,
                        g.in_h,
                        segment_name="FCurveTangentLine",
                    )

                if i < last and _tangent_visible(key.out_tangent_type, selected):
                    otx, oty = self._vp.model_to_pixel(key.time + key.out_tangent_x, key.value + key.out_tangent_y)
                    g.out_h = HandleWidget(
                        otx,
                        oty,
                        color=self._curve_color,
                        handle_name="FCurveTangent",
                        handle_size=self._tangent_size,
                        on_moved=lambda h, _k=key: self._on_tangent_moved(h, _k, is_in=False),
                        on_pressed=lambda _h, mod, _k=key: self._on_handle_pressed(_k, mod),
                        on_released=lambda h, _m, _k=key: self._on_tangent_released(h, _k, is_in=False),
                    )
                    g.out_seg = SegmentWidget(
                        SegmentMode.LINE,
                        g.key_h,
                        g.out_h,
                        segment_name="FCurveTangentLine",
                    )

    # ── Build ───────────────────────────────────────────────────────────────

    def _create_key_group(self, key: FCurveKey) -> _KeyGroup:
        kx, ky = self._vp.model_to_pixel(key.time, key.value)
        kh = HandleWidget(
            kx,
            ky,
            color=self._curve_color,
            handle_name="FCurveKey",
            handle_size=self._key_size,
            on_moved=self._on_key_moved,
            on_released=self._on_key_released_internal,
            on_pressed=lambda _h, mod: self._on_handle_pressed(key, mod),
            on_selection_changed=self._on_key_selection_changed,
        )
        return _KeyGroup(key, kh)

    def _rebuild_curve_segments(self) -> None:
        """Rebuild finite segments after the shared handle layer."""
        for seg in self._curve_segments:
            seg.destroy()
        self._curve_segments.clear()
        if not self._stack:
            return
        with self._segment_stack:
            for i in range(len(self._groups) - 1):
                mode = self._segment_mode_for(i)
                self._curve_segments.append(
                    SegmentWidget(
                        mode,
                        self._groups[i].key_h,
                        self._groups[i + 1].key_h,
                        color=self._curve_color,
                        on_pressed=lambda parameter, x, y, index=i: self._insert_key(index, parameter, x, y),
                    )
                )

    def _update_curve_segments(self) -> None:
        for i, seg in enumerate(self._curve_segments):
            mode = self._segment_mode_for(i)
            if seg.mode != mode:
                seg.set_mode(mode)
            if seg.mode == SegmentMode.BEZIER:
                k, nk = self._curve.keys[i], self._curve.keys[i + 1]
                kx, ky = self._vp.model_to_pixel(k.time, k.value)
                nkx, nky = self._vp.model_to_pixel(nk.time, nk.value)
                otx, oty = self._vp.model_to_pixel(k.time + k.out_tangent_x, k.value + k.out_tangent_y)
                itx, ity = self._vp.model_to_pixel(nk.time + nk.in_tangent_x, nk.value + nk.in_tangent_y)
                seg.set_tangents(otx - kx, oty - ky, itx - nkx, ity - nky)
            elif seg.mode == SegmentMode.STEP:
                seg.update_step_elbow()

    def _rebuild_infinity(self) -> None:
        """Rebuild the noninteractive infinity segments."""
        for inf in (self._pre_infinity, self._post_infinity):
            if inf:
                inf.destroy()
        self._pre_infinity = self._post_infinity = None
        if not self._stack or not self._groups:
            return
        with self._segment_stack:
            self._pre_infinity = InfinityCurveWidget(self._groups[0].key_h, is_pre=True, color=self._curve_color)
            self._post_infinity = InfinityCurveWidget(self._groups[-1].key_h, is_pre=False, color=self._curve_color)

    def _update_infinity(self) -> None:
        keys = self._curve.keys
        if self._pre_infinity and keys:
            k = keys[0]
            ax, ay = self._groups[0].key_h.position
            tx, ty = self._vp.model_to_pixel(k.time + k.out_tangent_x, k.value + k.out_tangent_y)
            self._pre_infinity.update(ax, ay, tx - ax, ty - ay, self._curve.pre_infinity)
        if self._post_infinity and keys:
            k = keys[-1]
            ax, ay = self._groups[-1].key_h.position
            tx, ty = self._vp.model_to_pixel(k.time + k.in_tangent_x, k.value + k.in_tangent_y)
            self._post_infinity.update(ax, ay, tx - ax, ty - ay, self._curve.post_infinity)

    def _segment_mode_for(self, i: int) -> SegmentMode:
        return SegmentMode.STEP if self._curve.keys[i].out_tangent_type == TangentType.STEP else SegmentMode.BEZIER

    def _insert_key(self, index: int, parameter: float, x: float, y: float) -> None:
        """Split a native segment without changing its shape and begin a held edit."""
        curve = self._curve
        if (
            self._on_insert_started is None
            or self.is_inserting_key
            or curve.locked
            or not curve.visible
            or not 0.0 <= parameter <= 1.0
            or not 0 <= index < len(curve.keys) - 1
        ):
            return

        start, end = curve.keys[index : index + 2]
        is_step = start.out_tangent_type == TangentType.STEP
        pointer_x = (x - self._stack.screen_position_x) / self._zoom
        pointer_y = (y - self._stack.screen_position_y) / self._zoom
        for attempt in range(2):
            if attempt:
                if is_step:
                    return
                # ponytail: Pointer-time retry is not a nearest-point solve; expand only for measured remaining misses.
                time = self._vp.x_to_time(pointer_x)
                if not start.time < time < end.time:
                    return
                parameter = bezier_parameter_at_time(start, end, time)
            if not 0.0 < parameter < 1.0:
                continue
            if is_step:
                position = Vector2(lerp(start.time, end.time, parameter), start.value)
            else:
                start_point = Vector2(start.time, start.value)
                end_point = Vector2(end.time, end.value)
                start_control = start_point + Vector2(start.out_tangent_x, start.out_tangent_y)
                end_control = end_point + Vector2(end.in_tangent_x, end.in_tangent_y)
                first = start_point + (start_control - start_point) * parameter
                middle = start_control + (end_control - start_control) * parameter
                last = end_control + (end_point - end_control) * parameter
                incoming = first + (middle - first) * parameter
                outgoing = middle + (last - middle) * parameter
                position = incoming + (outgoing - incoming) * parameter
                start_tangent, end_tangent = first - start_point, last - end_point
                incoming_tangent, outgoing_tangent = incoming - position, outgoing - position
                left_width, right_width = position.x - start.time, end.time - position.x

            if not isfinite(position.x) or not isfinite(position.y) or not start.time < position.x < end.time:
                return
            key_x, key_y = self._vp.model_to_pixel(position.x, position.y)
            pointer_offset = (key_x - pointer_x, key_y - pointer_y)
            if hypot(*pointer_offset) * self._zoom <= _INSERTION_HIT_RADIUS_LOGICAL_PIXELS:
                break
        else:
            return
        if any(abs(key.time - position.x) < self.x_flip_threshold or key.time == position.x for key in curve.keys):
            carb.log_info(f"Key insertion skipped on curve '{curve.id}': the time is too close to an existing key.")
            return
        # Reject splits whose handles would change shape when process_curve clamps them.
        if not is_step and not (
            self.x_flip_threshold <= start_tangent.x <= left_width
            and self.x_flip_threshold <= -incoming_tangent.x <= left_width
            and self.x_flip_threshold <= outgoing_tangent.x <= right_width
            and self.x_flip_threshold <= -end_tangent.x <= right_width
        ):
            carb.log_info(
                f"Key insertion skipped on curve '{curve.id}': preserving the curve shape would exceed tangent limits."
            )
            return
        if not self._on_insert_started():
            return

        inserted = FCurveKey(time=position.x, value=position.y)
        if is_step:
            inserted.in_tangent_type = inserted.out_tangent_type = TangentType.STEP
        else:
            start.out_tangent_x, start.out_tangent_y = start_tangent.x, start_tangent.y
            end.in_tangent_x, end.in_tangent_y = end_tangent.x, end_tangent.y
            inserted.in_tangent_x, inserted.in_tangent_y = incoming_tangent.x, incoming_tangent.y
            inserted.out_tangent_x, inserted.out_tangent_y = outgoing_tangent.x, outgoing_tangent.y
            start.out_tangent_type = end.in_tangent_type = TangentType.CUSTOM
            inserted.in_tangent_type = inserted.out_tangent_type = TangentType.CUSTOM

        # AUTO depends on both neighbors; linked tangents also copy the opposite type.
        if index > 0 and (start.in_tangent_type == TangentType.AUTO or (not is_step and not start.tangent_broken)):
            start.in_tangent_type = TangentType.CUSTOM
        if index + 2 < len(curve.keys):
            if not is_step and not end.tangent_broken and end.out_tangent_type == TangentType.STEP:
                end.tangent_broken = True
            elif end.out_tangent_type == TangentType.AUTO or (not is_step and not end.tangent_broken):
                end.out_tangent_type = TangentType.CUSTOM
                if not end.tangent_broken:
                    end.in_tangent_type = TangentType.CUSTOM

        curve.keys.insert(index + 1, inserted)
        self._inserted_key = inserted
        self._insert_pointer_offset = pointer_offset
        self._topology_dirty = True
        if self._on_key_added:
            self._on_key_added(index + 1)

    # ── Drag callbacks ──────────────────────────────────────────────────────

    def _group_for(self, handle: HandleWidget) -> tuple[_KeyGroup | None, int]:
        for i, g in enumerate(self._groups):
            if g.key_h is handle:
                return g, i
        return None, -1

    def _on_handle_pressed(self, key: FCurveKey, mod: int) -> None:
        """Claim key and tangent presses through the existing edit callback."""
        if self._on_key_pressed:
            self._on_key_pressed(self._curve.keys.index(key), mod)

    def _on_key_moved(self, handle: HandleWidget) -> None:
        """Delegate held key movement to the selection owner when supplied."""
        group, index = self._group_for(handle)
        if group:
            if self._on_key_dragged:
                # Release snaps the placer to its model position; it is not another pointer delta.
                if handle.is_dragging:
                    self._on_key_dragged(index, handle.raw_px)
            else:
                self._move_key(group.key_ref, handle.raw_px)

    def _move_key(self, key: FCurveKey, position: tuple[float, float]) -> None:
        """Constrain a dragged key and publish its changed position."""
        # Ignore floating-point round trips before reprocessing automatic tangents.
        if all(
            isclose(a, b, rel_tol=0.0, abs_tol=_KEY_POSITION_ROUND_TRIP_TOLERANCE_LOCAL_PIXELS)
            for a, b in zip(position, self._vp.model_to_pixel(key.time, key.value))
        ):
            return
        raw_t, raw_v = self._vp.pixel_to_model(*position)
        idx = self._curve.keys.index(key)
        process_curve(self._curve, self._bounds, self.x_flip_threshold, key_positions={idx: (raw_t, raw_v)})
        self._positions_dirty = True
        if self._on_key_moved_cb:
            self._on_key_moved_cb(idx)

    def _on_key_released_internal(self, handle: HandleWidget, mod: int) -> None:
        _, idx = self._group_for(handle)
        self._positions_dirty = True
        if idx >= 0 and self._on_key_released:
            self._on_key_released(idx)

    def _on_key_selection_changed(self, handle: HandleWidget, mod: int) -> None:
        """Update logical selection from native handle selection."""
        multi = bool(mod & carb.input.KEYBOARD_MODIFIER_FLAG_SHIFT)
        if handle.selected and not multi:
            for g in self._groups:
                if g.key_h is not handle and g.key_h.selected:
                    g.key_h.selected = False
        self._selected_indices = {i for i, group in enumerate(self._groups) if group.key_h.selected}
        # Defer tangent rebuild to next frame -- can't addChild during draw callback
        self._tangents_dirty = True
        if self._on_selection_changed_cb:
            self._on_selection_changed_cb(mod)

    def _on_tangent_moved(self, handle: HandleWidget, key: FCurveKey, *, is_in: bool) -> None:
        idx = self._curve.keys.index(key)
        raw_t, raw_v = self._vp.pixel_to_model(*handle.raw_px)
        offset = (raw_t - key.time, raw_v - key.value)
        process_curve(self._curve, self._bounds, self.x_flip_threshold, tangent_positions={(idx, is_in): offset})
        self._positions_dirty = True
        if self._on_tangent_moved_cb:
            self._on_tangent_moved_cb(idx, is_in)

    def _on_tangent_released(self, handle: HandleWidget, key: FCurveKey, *, is_in: bool) -> None:
        self._positions_dirty = True
        if self._on_tangent_released_cb:
            idx = self._curve.keys.index(key)
            self._on_tangent_released_cb(idx, is_in)
