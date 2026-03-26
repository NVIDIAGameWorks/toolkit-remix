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
Grid renderer for the curve editor canvas.

Renders adaptive grid lines that adjust density based on zoom level.
Uses shared tick calculation from ticks.py for DRY interval logic.

Visual appearance cascades from the parent's name-based style via widget
names ``CurveEditorGrid``, ``CurveEditorGridMajor``, and ``CurveEditorAxis``.
"""

from __future__ import annotations

from omni import ui

from .ticks import compute_nice_interval, generate_ticks
from .viewport import ViewportState

__all__ = ["GridRenderer"]


class GridRenderer:
    """Renders grid lines on the curve editor canvas.

    Build in constructor (omni.ui style) - instantiate within a UI context.
    Uses shared tick calculation for consistent intervals with timeline/value rulers.

    Args:
        viewport: Shared viewport state (read on each rebuild).
        time_divisions: Target number of time-axis divisions.
        value_divisions: Target number of value-axis divisions.
        line_width: Grid line width in pixels.
        axis_width: Axis line width in pixels.
        margin: Pixel margin around the grid.
        min_viewport_size: Minimum viewport dimension before grid is hidden.
    """

    def __init__(
        self,
        viewport: ViewportState,
        time_divisions: int = 15,
        value_divisions: int = 10,
        line_width: int = 1,
        axis_width: int = 2,
        margin: int = 2,
        min_viewport_size: int = 10,
    ):
        self._viewport = viewport
        self._line_width = line_width
        self._axis_width = axis_width
        self._margin = margin
        self._min_viewport_size = min_viewport_size
        self._time_divisions = time_divisions
        self._value_divisions = value_divisions

        self._frame = ui.Frame()
        self._frame.set_build_fn(self._build)

    def rebuild(self) -> None:
        """Rebuild grid lines for the current viewport state."""
        if self._frame:
            self._frame.rebuild()

    def _build(self) -> None:
        """Build grid lines for the current viewport."""
        viewport = self._viewport
        if viewport.width < self._min_viewport_size or viewport.height < self._min_viewport_size:
            return

        time_config = compute_nice_interval(viewport.time_range, target_divisions=self._time_divisions)
        value_config = compute_nice_interval(viewport.value_range, target_divisions=self._value_divisions)

        margin = self._margin
        max_x = viewport.width - margin
        max_y = viewport.height - margin

        with ui.ZStack():
            for tick in generate_ticks(
                viewport.time_min,
                viewport.time_max,
                time_config,
                viewport.time_to_x,
                pixel_margin=margin,
                pixel_max=viewport.width,
            ):
                name = "CurveEditorGridMajor" if tick.is_major else "CurveEditorGrid"
                with ui.Placer(offset_x=tick.pixel, offset_y=0):
                    ui.Rectangle(name=name, width=self._line_width, height=max_y)

            for tick in generate_ticks(
                viewport.value_min,
                viewport.value_max,
                value_config,
                viewport.value_to_y,
                pixel_margin=margin,
                pixel_max=viewport.height,
            ):
                name = "CurveEditorGridMajor" if tick.is_major else "CurveEditorGrid"
                with ui.Placer(offset_x=0, offset_y=tick.pixel):
                    ui.Rectangle(name=name, width=max_x, height=self._line_width)

            if viewport.time_min <= 0 <= viewport.time_max:
                x = viewport.time_to_x(0)
                if margin <= x < max_x:
                    with ui.Placer(offset_x=x, offset_y=0):
                        ui.Rectangle(name="CurveEditorAxis", width=self._axis_width, height=max_y)

            if viewport.value_min <= 0 <= viewport.value_max:
                y = viewport.value_to_y(0)
                if margin <= y < max_y:
                    with ui.Placer(offset_x=0, offset_y=y):
                        ui.Rectangle(name="CurveEditorAxis", width=max_x, height=self._axis_width)
