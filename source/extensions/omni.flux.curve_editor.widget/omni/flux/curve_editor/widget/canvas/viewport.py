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

Viewport state and coordinate transformations for the curve editor canvas.

Handles conversions between model space (time, value) and pixel space (x, y),
as well as pan/zoom operations.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ViewportState"]


@dataclass
class ViewportState:
    """
    Viewport state for coordinate transformations.

    Manages the mapping between model coordinates (time, value) and
    pixel coordinates (x, y) on the canvas.

    Attributes:
        time_min: Minimum visible time.
        time_max: Maximum visible time.
        value_min: Minimum visible value.
        value_max: Maximum visible value.
        width: Canvas width in pixels.
        height: Canvas height in pixels.
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
        """
        Convert value to Y pixel coordinate.

        Note: Y is inverted (0 at top, increases downward), so high values
        map to low Y coordinates.
        """
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
    # Viewport manipulation
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

    def pan(self, delta_time: float, delta_value: float) -> None:
        """
        Pan the viewport by the given amounts.

        Args:
            delta_time: Amount to pan in time (positive = right).
            delta_value: Amount to pan in value (positive = up).
        """
        self.time_min += delta_time
        self.time_max += delta_time
        self.value_min += delta_value
        self.value_max += delta_value

    def zoom(
        self,
        scale_x: float,
        scale_y: float,
        center_x: float | None = None,
        center_y: float | None = None,
    ) -> None:
        """
        Zoom the viewport around a center point.

        The point under the mouse cursor stays at the same pixel location
        after zooming.

        Args:
            scale_x: X-axis zoom factor (>1 = zoom in, <1 = zoom out).
            scale_y: Y-axis zoom factor (>1 = zoom in, <1 = zoom out).
            center_x: X pixel coordinate of zoom center (default: canvas center).
            center_y: Y pixel coordinate of zoom center (default: canvas center).
        """
        if center_x is None:
            center_x = self.width / 2
        if center_y is None:
            center_y = self.height / 2

        # Convert center to model space - this point stays fixed on screen
        center_time = self.x_to_time(center_x)
        center_value = self.y_to_value(center_y)

        # Calculate distances from center to current edges
        dist_to_min_time = center_time - self.time_min
        dist_to_max_time = self.time_max - center_time
        dist_to_min_value = center_value - self.value_min
        dist_to_max_value = self.value_max - center_value

        # Scale the distances (larger scale = smaller distances = zoom in)
        new_dist_to_min_time = dist_to_min_time / scale_x
        new_dist_to_max_time = dist_to_max_time / scale_x
        new_dist_to_min_value = dist_to_min_value / scale_y
        new_dist_to_max_value = dist_to_max_value / scale_y

        # Apply new edges - center point stays at same pixel location
        self.time_min = center_time - new_dist_to_min_time
        self.time_max = center_time + new_dist_to_max_time
        self.value_min = center_value - new_dist_to_min_value
        self.value_max = center_value + new_dist_to_max_value

    def zoom_x(self, scale: float, center_x: float | None = None) -> None:
        """Zoom only the X (time) axis."""
        self.zoom(scale, 1.0, center_x, None)

    def zoom_y(self, scale: float, center_y: float | None = None) -> None:
        """Zoom only the Y (value) axis."""
        self.zoom(1.0, scale, None, center_y)
