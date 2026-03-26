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

Viewport state for coordinate transformations.

Handles conversions between model space (time, value) and pixel space (x, y).
This is internal to FCurveWidget for rendering - zoom/pan gestures are handled
by the hosting editor, which then sets time_range/value_range on FCurveWidget.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ViewportState"]


@dataclass
class ViewportState:
    """
    Coordinate transformation state for curve rendering.

    Maps between model coordinates (time, value) and pixel coordinates (x, y).
    The hosting editor controls the visible range via set_time_range/set_value_range.
    """

    time_min: float = 0.0
    time_max: float = 1.0
    value_min: float = 0.0
    value_max: float = 1.0
    width: float = 100.0
    height: float = 100.0

    # ─────────────────────────────────────────────────────────────────────────
    # Time (X-axis) transforms
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def time_range(self) -> float:
        """Get the visible time range."""
        return self.time_max - self.time_min

    @property
    def time_scale(self) -> float:
        """Get pixels per time unit."""
        if self.time_range == 0:
            return 1.0
        return self.width / self.time_range

    def time_to_x(self, time: float) -> float:
        """Convert time to X pixel coordinate."""
        return (time - self.time_min) * self.time_scale

    def x_to_time(self, x: float) -> float:
        """Convert X pixel coordinate to time."""
        if self.time_scale == 0:
            return self.time_min
        return self.time_min + x / self.time_scale

    # ─────────────────────────────────────────────────────────────────────────
    # Value (Y-axis) transforms
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def value_range(self) -> float:
        """Get the visible value range."""
        return self.value_max - self.value_min

    @property
    def value_scale(self) -> float:
        """Get pixels per value unit."""
        if self.value_range == 0:
            return 1.0
        return self.height / self.value_range

    def value_to_y(self, value: float) -> float:
        """Convert value to Y pixel coordinate (Y inverted)."""
        return self.height - (value - self.value_min) * self.value_scale

    def y_to_value(self, y: float) -> float:
        """Convert Y pixel coordinate to value."""
        if self.value_scale == 0:
            return self.value_min
        return self.value_min + (self.height - y) / self.value_scale

    # ─────────────────────────────────────────────────────────────────────────
    # Combined transforms
    # ─────────────────────────────────────────────────────────────────────────

    def model_to_pixel(self, time: float, value: float) -> tuple[float, float]:
        """Convert model coordinates to pixel coordinates."""
        return self.time_to_x(time), self.value_to_y(value)

    def pixel_to_model(self, x: float, y: float) -> tuple[float, float]:
        """Convert pixel coordinates to model coordinates."""
        return self.x_to_time(x), self.y_to_value(y)

    # ─────────────────────────────────────────────────────────────────────────
    # Range setters (called by FCurveWidget when editor sets time_range/value_range)
    # ─────────────────────────────────────────────────────────────────────────

    def set_time_range(self, time_min: float, time_max: float) -> None:
        """Set the visible time range."""
        self.time_min = time_min
        self.time_max = time_max

    def set_value_range(self, value_min: float, value_max: float) -> None:
        """Set the visible value range."""
        self.value_min = value_min
        self.value_max = value_max

    def set_size(self, width: float, height: float) -> None:
        """Set the canvas size in pixels."""
        self.width = max(1.0, width)
        self.height = max(1.0, height)
