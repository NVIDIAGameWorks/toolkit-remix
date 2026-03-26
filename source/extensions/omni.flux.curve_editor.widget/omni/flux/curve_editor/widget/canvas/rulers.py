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

Ruler components for the curve editor canvas.

Provides:
- Ruler: Base class with common tick/label rendering logic
- TimelineRuler: Horizontal ruler for time axis (top of canvas)
- ValueRuler: Vertical ruler for value axis (left of canvas)

Uses shared tick calculation from ticks.py for consistent intervals with grid.

Visual appearance cascades from the parent's name-based style via widget
names ``CurveEditorRulerLabel``, ``CurveEditorRulerTick``, ``CurveEditorRulerBg``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from omni import ui

from .ticks import TickInfo, compute_nice_interval, generate_ticks
from .viewport import ViewportState

__all__ = [
    "Ruler",
    "RulerOrientation",
    "TimelineRuler",
    "ValueRuler",
]

_TICK_MAJOR = 12
_TICK_MINOR = 6
_H_LABEL_WIDTH = 40
_V_LABEL_HEIGHT = 16
_LABEL_OFFSET = 2
_MIN_LENGTH = 10
_MARGIN = 4


class RulerOrientation(Enum):
    """Ruler orientation."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class Ruler(ABC):
    """
    Base class for rulers with tick marks and labels.

    Subclasses implement orientation-specific layout and viewport extraction.
    Build in constructor (omni.ui style) -- instantiate within a UI context.

    Args:
        orientation: HORIZONTAL or VERTICAL.
        viewport: Shared viewport state (read on each rebuild).
        ruler_size: Width/height of the ruler bar in pixels.
        time_divisions: Target number of time-axis grid divisions.
        value_divisions: Target number of value-axis grid divisions.
    """

    def __init__(
        self,
        orientation: RulerOrientation,
        viewport: ViewportState,
        ruler_size: int = 24,
        time_divisions: int = 15,
        value_divisions: int = 10,
    ):
        self._orientation = orientation
        self._viewport = viewport
        self._size = ruler_size
        self._time_divisions = time_divisions
        self._value_divisions = value_divisions

        self._length = 0.0

        if orientation == RulerOrientation.HORIZONTAL:
            self._frame = ui.Frame(
                height=ui.Pixel(self._size),
                horizontal_clipping=True,
                vertical_clipping=True,
            )
        else:
            self._frame = ui.Frame(
                width=ui.Pixel(self._size),
                horizontal_clipping=True,
                vertical_clipping=True,
            )

        with self._frame:
            with ui.ZStack():
                ui.Rectangle(name="CurveEditorRulerBg")
                self._content_frame = ui.Frame()
                self._content_frame.set_build_fn(self._build_ticks)

        self._frame.set_computed_content_size_changed_fn(self._on_size_changed)

    def _on_size_changed(self) -> None:
        if self._frame:
            if self._orientation == RulerOrientation.HORIZONTAL:
                self._length = self._frame.computed_content_width
            else:
                self._length = self._frame.computed_content_height

    @abstractmethod
    def _get_range(self) -> tuple[float, float]:
        pass

    @abstractmethod
    def _get_range_size(self) -> float:
        pass

    @abstractmethod
    def _model_to_pixel(self, value: float) -> float:
        pass

    def rebuild(self) -> None:
        if self._content_frame:
            self._content_frame.rebuild()

    def _build_ticks(self) -> None:
        length = self._length
        if length < _MIN_LENGTH:
            return

        range_size = self._get_range_size()
        target_divisions = (
            self._time_divisions if self._orientation == RulerOrientation.HORIZONTAL else self._value_divisions
        )
        config = compute_nice_interval(range_size, target_divisions=target_divisions)

        range_min, range_max = self._get_range()

        with ui.ZStack():
            for tick in generate_ticks(
                range_min,
                range_max,
                config,
                self._model_to_pixel,
                pixel_margin=_MARGIN,
                pixel_max=length,
            ):
                self._render_tick(tick)

    def _render_tick(self, tick: TickInfo) -> None:
        tick_size = _TICK_MAJOR if tick.is_major else _TICK_MINOR

        if self._orientation == RulerOrientation.HORIZONTAL:
            self._render_horizontal_tick(tick, tick_size)
        else:
            self._render_vertical_tick(tick, tick_size)

    def _render_horizontal_tick(self, tick: TickInfo, tick_size: int) -> None:
        with ui.Placer(offset_x=tick.pixel, offset_y=self._size - tick_size):
            ui.Rectangle(name="CurveEditorRulerTick", width=1, height=tick_size)

        if tick.is_major:
            label_width = _H_LABEL_WIDTH
            label_offset = max(0, min(tick.pixel - label_width / 2, self._length - label_width))
            with ui.Placer(offset_x=label_offset, offset_y=_LABEL_OFFSET):
                ui.Label(
                    tick.label,
                    name="CurveEditorRulerLabel",
                    width=label_width,
                    height=self._size - _TICK_MAJOR - _MARGIN,
                    alignment=ui.Alignment.CENTER,
                )

    def _render_vertical_tick(self, tick: TickInfo, tick_size: int) -> None:
        with ui.Placer(offset_x=self._size - tick_size, offset_y=tick.pixel):
            ui.Rectangle(name="CurveEditorRulerTick", width=tick_size, height=1)

        if tick.is_major:
            label_height = _V_LABEL_HEIGHT
            label_offset = max(0, min(tick.pixel - label_height / 2, self._length - label_height))
            with ui.Placer(offset_x=_LABEL_OFFSET, offset_y=label_offset):
                ui.Label(
                    tick.label,
                    name="CurveEditorRulerLabel",
                    width=self._size - _TICK_MAJOR - _MARGIN,
                    height=label_height,
                    alignment=ui.Alignment.RIGHT_CENTER,
                )


class TimelineRuler(Ruler):
    """
    Horizontal ruler for the time axis (displayed at top of canvas).

    Shows time values with tick marks and labels synchronized with grid.
    """

    def __init__(
        self,
        viewport: ViewportState,
        ruler_size: int = 24,
        time_divisions: int = 15,
        value_divisions: int = 10,
    ):
        super().__init__(
            orientation=RulerOrientation.HORIZONTAL,
            viewport=viewport,
            ruler_size=ruler_size,
            time_divisions=time_divisions,
            value_divisions=value_divisions,
        )

    def _get_range(self) -> tuple[float, float]:
        return self._viewport.time_min, self._viewport.time_max

    def _get_range_size(self) -> float:
        return self._viewport.time_range

    def _model_to_pixel(self, value: float) -> float:
        return self._viewport.time_to_x(value)


class ValueRuler(Ruler):
    """
    Vertical ruler for the value axis (displayed at left of canvas).

    Shows value labels with tick marks synchronized with grid.
    """

    def __init__(
        self,
        viewport: ViewportState,
        ruler_size: int = 24,
        time_divisions: int = 15,
        value_divisions: int = 10,
    ):
        super().__init__(
            orientation=RulerOrientation.VERTICAL,
            viewport=viewport,
            ruler_size=ruler_size,
            time_divisions=time_divisions,
            value_divisions=value_divisions,
        )

    def _get_range(self) -> tuple[float, float]:
        return self._viewport.value_min, self._viewport.value_max

    def _get_range_size(self) -> float:
        return self._viewport.value_range

    def _model_to_pixel(self, value: float) -> float:
        return self._viewport.value_to_y(value)
