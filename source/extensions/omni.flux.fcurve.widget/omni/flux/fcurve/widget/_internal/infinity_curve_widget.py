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

Infinity line extending from one HandleWidget to a far-away point.
Pre-infinity extends left using the first key's out-tangent angle.
Post-infinity extends right using the last key's in-tangent angle.
Wraps its widgets in a ZStack so destroy() can clear() them.

Visual appearance cascades from the parent's name-based style via
``name="FCurveInfinity"``.  Per-curve ``color`` is applied as inline override.
"""

from __future__ import annotations

from omni import ui

from .math import Vector2
from ..model import InfinityType
from .handle_widget import HandleWidget

__all__ = ["InfinityCurveWidget"]

_FAR = 10000.0


class InfinityCurveWidget:
    def __init__(self, handle: HandleWidget, is_pre: bool, color: int):
        self._handle = handle
        self._is_pre = is_pre
        self._color = color

        self._container: ui.ZStack | None = ui.ZStack()
        self._far_placer: ui.Placer | None = None
        self._far_rect: ui.Rectangle | None = None
        self._line: ui.FreeLine | None = None
        self._build_contents()

    def update(
        self, anchor_x: float, anchor_y: float, tangent_dx: float, tangent_dy: float, mode: InfinityType
    ) -> None:
        pos = Vector2(anchor_x, anchor_y) - Vector2(tangent_dx, 0.0).normalized() * _FAR  # CONSTANT
        if mode == InfinityType.LINEAR:
            pos = Vector2(anchor_x, anchor_y) - Vector2(tangent_dx, tangent_dy).normalized() * _FAR
        far_x, far_y = pos.x, pos.y

        if self._far_placer:
            self._far_placer.offset_x = far_x
            self._far_placer.offset_y = far_y

    def set_line_thickness(self, thickness: float) -> None:
        if self._line:
            self._line.set_style({"color": self._color, "border_width": thickness})

    def destroy(self) -> None:
        self._clear_contents()
        self._container = None
        self._handle = None

    def _build_contents(self) -> None:
        handle_rect = self._handle.rect if self._handle else None
        if not self._container or not handle_rect:
            return
        with self._container:
            self._far_placer = ui.Placer(offset_x=0, offset_y=0, stable_size=True)
            with self._far_placer:
                with ui.Frame():
                    self._far_rect = ui.Rectangle(visible=False, width=0, height=0)
            self._line = ui.FreeLine(
                handle_rect,
                self._far_rect,
                name="FCurveInfinity",
                alignment=ui.Alignment.UNDEFINED,
                style={"color": self._color},
            )

    def _clear_contents(self) -> None:
        if self._container:
            self._container.clear()
        self._far_placer = self._far_rect = self._line = None
