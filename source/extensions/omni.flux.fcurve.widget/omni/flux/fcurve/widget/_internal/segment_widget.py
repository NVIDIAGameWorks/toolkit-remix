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

Segment connecting two HandleWidgets: line, bezier curve, or step elbow.
Connects directly to HandleWidget.rect (no owned anchors needed).
Each instance wraps its widgets in its own ZStack so destroy() can clear() it.
Constructor = build: call inside a parent ``with`` context.

Visual appearance cascades from the parent's name-based style via
the ``segment_name`` parameter (e.g. ``"FCurveSegment"`` or
``"FCurveTangentLine"``).  When ``color`` is provided it is applied as an
inline override; when ``None`` the color comes entirely from the style.
"""

from __future__ import annotations

from enum import IntEnum

from omni import ui

from .handle_widget import HandleWidget

__all__ = ["SegmentMode", "SegmentWidget"]


class SegmentMode(IntEnum):
    LINE = 0
    BEZIER = 1
    STEP = 2


class SegmentWidget:
    def __init__(
        self,
        mode: SegmentMode,
        start: HandleWidget,
        end: HandleWidget,
        color: int | None = None,
        segment_name: str = "FCurveSegment",
    ):
        self._start = start
        self._end = end
        self._color = color
        self._segment_name = segment_name
        self._mode = mode

        self._container: ui.ZStack | None = None
        self._bezier: ui.FreeBezierCurve | None = None
        self._line: ui.FreeLine | None = None
        self._step_h: ui.FreeLine | None = None
        self._step_v: ui.FreeLine | None = None
        self._elbow_placer: ui.Placer | None = None
        self._elbow_rect: ui.Rectangle | None = None

        self._build_mode()

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def mode(self) -> SegmentMode:
        return self._mode

    @property
    def start(self) -> HandleWidget:
        return self._start

    @property
    def end(self) -> HandleWidget:
        return self._end

    def set_mode(self, mode: SegmentMode) -> None:
        if mode == self._mode:
            return
        self._clear_mode()
        self._mode = mode
        self._build_mode()

    def set_tangents(self, start_dx: float, start_dy: float, end_dx: float, end_dy: float) -> None:
        if self._bezier:
            self._bezier.start_tangent_width = ui.Pixel(start_dx)
            self._bezier.start_tangent_height = ui.Pixel(start_dy)
            self._bezier.end_tangent_width = ui.Pixel(end_dx)
            self._bezier.end_tangent_height = ui.Pixel(end_dy)

    def update_step_elbow(self) -> None:
        if self._mode == SegmentMode.STEP and self._elbow_placer:
            ex, _ = self._end.position
            _, sy = self._start.position
            self._elbow_placer.offset_x, self._elbow_placer.offset_y = ex, sy

    def set_line_thickness(self, thickness: float) -> None:
        s: dict = {"border_width": thickness}
        if self._color is not None:
            s["color"] = self._color
        for widget in (self._line, self._bezier, self._step_h, self._step_v):
            if widget:
                widget.set_style(s)

    def destroy(self) -> None:
        self._clear_mode()
        self._container = None
        self._start = self._end = None

    # ── Internal ────────────────────────────────────────────────────────────

    def _build_mode(self) -> None:
        s_rect, e_rect = self._start.rect, self._end.rect
        if not s_rect or not e_rect:
            return
        inline_style = {"color": self._color} if self._color is not None else {}
        name = self._segment_name

        if not self._container:
            self._container = ui.ZStack()
        with self._container:
            if self._mode == SegmentMode.LINE:
                self._line = ui.FreeLine(
                    s_rect,
                    e_rect,
                    name=name,
                    alignment=ui.Alignment.UNDEFINED,
                    style=inline_style,
                )

            elif self._mode == SegmentMode.BEZIER:
                self._bezier = ui.FreeBezierCurve(
                    s_rect,
                    e_rect,
                    name=name,
                    style=inline_style,
                )

            elif self._mode == SegmentMode.STEP:
                sx, sy = self._start.position
                ex, ey = self._end.position
                self._elbow_placer = ui.Placer(offset_x=ex, offset_y=sy, stable_size=True)
                with self._elbow_placer:
                    with ui.Frame():
                        self._elbow_rect = ui.Rectangle(visible=False, width=0, height=0)
                self._step_h = ui.FreeLine(
                    s_rect,
                    self._elbow_rect,
                    name=name,
                    alignment=ui.Alignment.UNDEFINED,
                    style=inline_style,
                )
                self._step_v = ui.FreeLine(
                    self._elbow_rect,
                    e_rect,
                    name=name,
                    alignment=ui.Alignment.UNDEFINED,
                    style=inline_style,
                )

    def _clear_mode(self) -> None:
        if self._container:
            self._container.clear()
        self._bezier = self._line = None
        self._step_h = self._step_v = self._elbow_placer = self._elbow_rect = None
