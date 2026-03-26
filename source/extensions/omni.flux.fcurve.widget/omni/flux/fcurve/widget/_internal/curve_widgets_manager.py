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

from typing import TYPE_CHECKING

import carb.input
import omni.kit.app
from omni import ui

from .handle_widget import HandleWidget
from .infinity_curve_widget import InfinityCurveWidget
from .math import process_curve
from .segment_widget import SegmentMode, SegmentWidget

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..model import CurveBounds, FCurve, FCurveKey
    from .viewport import ViewportState

from ..model import TangentType

__all__ = ["CurveWidgetsManager"]

_DEFAULT_X_FLIP_THRESHOLD = 0.001
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

        self._stack: ui.ZStack | None = None
        self._groups: list[_KeyGroup] = []
        self._curve_segments: list[SegmentWidget] = []
        self._pre_infinity: InfinityCurveWidget | None = None
        self._post_infinity: InfinityCurveWidget | None = None
        self._positions_dirty: bool = False
        self._tangents_dirty: bool = False
        self._update_sub = None
        self._zoom: float = 1.0

    @property
    def key_handles(self) -> list[HandleWidget]:
        return [g.key_h for g in self._groups]

    def build(self, stack: ui.ZStack) -> None:
        self._stack = stack
        process_curve(self._curve, self._bounds, self.x_flip_threshold)
        self._update_sub = (
            omni.kit.app.get_app()
            .get_update_event_stream()
            .create_subscription_to_pop(self._on_update, name="CurveWidgetsManager")
        )
        self._sync()

    def sync(self) -> None:
        self._sync()

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
        changed = False
        for i, g in enumerate(self._groups):
            should = i in selected_indices
            if g.key_h.selected != should:
                g.key_h.selected = should
                changed = True
        if changed:
            self._tangents_dirty = True

    def get_selected_indices(self) -> list[int]:
        return [i for i, g in enumerate(self._groups) if g.key_h.selected]

    def destroy(self) -> None:
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

    def _on_update(self, _event) -> None:
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
        topology_changed = self._sync_topology(self._curve.keys)
        if topology_changed:
            self._rebuild_curve_segments()
            self._rebuild_infinity()
        self._rebuild_tangents()
        self._tangents_dirty = False
        self._sync_positions()
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
            on_pressed=self._on_key_pressed_internal,
            on_selection_changed=self._on_key_selection_changed,
        )
        return _KeyGroup(key, kh)

    def _rebuild_curve_segments(self) -> None:
        for seg in self._curve_segments:
            seg.destroy()
        self._curve_segments.clear()
        if not self._stack:
            return
        with self._stack:
            for i in range(len(self._groups) - 1):
                mode = self._segment_mode_for(i)
                self._curve_segments.append(
                    SegmentWidget(mode, self._groups[i].key_h, self._groups[i + 1].key_h, color=self._curve_color)
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
        for inf in (self._pre_infinity, self._post_infinity):
            if inf:
                inf.destroy()
        self._pre_infinity = self._post_infinity = None
        if not self._stack or not self._groups:
            return
        with self._stack:
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

    # ── Drag callbacks ──────────────────────────────────────────────────────

    def _group_for(self, handle: HandleWidget) -> tuple[_KeyGroup | None, int]:
        for i, g in enumerate(self._groups):
            if g.key_h is handle:
                return g, i
        return None, -1

    def _on_key_pressed_internal(self, handle: HandleWidget, mod: int) -> None:
        _, idx = self._group_for(handle)
        if idx >= 0 and self._on_key_pressed:
            self._on_key_pressed(idx, mod)

    def _on_key_moved(self, handle: HandleWidget) -> None:
        _, idx = self._group_for(handle)
        if idx < 0:
            return
        raw_t, raw_v = self._vp.pixel_to_model(*handle.raw_px)
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
        multi = bool(mod & carb.input.KEYBOARD_MODIFIER_FLAG_SHIFT)
        if handle.selected and not multi:
            for g in self._groups:
                if g.key_h is not handle and g.key_h.selected:
                    g.key_h.selected = False
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
