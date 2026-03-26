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

Shared tick/interval calculation for grid, timeline ruler, and value ruler.

Provides DRY logic for computing nice intervals and generating tick positions
that can be used by any component needing evenly-spaced markers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from collections.abc import Callable, Iterator

__all__ = [
    "TickConfig",
    "TickInfo",
    "compute_nice_interval",
    "format_value",
    "generate_ticks",
]


@dataclass
class TickInfo:
    """Information about a single tick mark."""

    position: float  # Position in model space (time or value)
    pixel: float  # Position in pixel space
    is_major: bool  # True for major ticks, False for minor
    label: str  # Formatted label text


@dataclass
class TickConfig:
    """Configuration for tick generation."""

    interval: float  # Spacing between minor ticks in model units
    major_every: int  # Number of minor ticks per major tick
    label_precision: int  # Decimal places for labels (0 for integers)

    @property
    def major_interval(self) -> float:
        """Spacing between major ticks."""
        return self.interval * self.major_every


def compute_nice_interval(
    range_size: float,
    target_divisions: int = 10,
) -> TickConfig:
    """
    Compute a nice interval for tick marks.

    Uses the 1-2-5 pattern common in scientific visualization to pick
    intervals that are easy to read (e.g., 0.1, 0.2, 0.5, 1, 2, 5, 10, ...).

    Args:
        range_size: The visible range (max - min) in model units.
        target_divisions: Approximate number of divisions desired.

    Returns:
        TickConfig with interval, major_every, and label_precision.
    """
    if range_size <= 0 or target_divisions <= 0:
        return TickConfig(interval=1.0, major_every=5, label_precision=0)

    # Calculate rough interval
    rough = range_size / target_divisions

    # Find order of magnitude
    if rough <= 0:
        return TickConfig(interval=1.0, major_every=5, label_precision=0)

    exponent = math.floor(math.log10(rough))
    magnitude = math.pow(10, exponent)
    normalized = rough / magnitude

    # Snap to the nearest 1-2-5 sequence value (ISO 3, aka "preferred numbers").
    # Within each decade only 1, 2, and 5 are used because they subdivide
    # evenly into 10 and produce human-readable tick labels on any axis.
    if normalized < 1.5:
        interval = magnitude
        major_every = 5
    elif normalized < 3.5:
        interval = 2 * magnitude
        major_every = 5
    elif normalized < 7.5:
        interval = 5 * magnitude
        major_every = 2
    else:
        interval = 10 * magnitude
        major_every = 5

    if interval >= 1:
        label_precision = 0
    else:
        label_precision = max(0, -int(math.floor(math.log10(interval))))

    return TickConfig(
        interval=interval,
        major_every=major_every,
        label_precision=label_precision,
    )


def generate_ticks(
    range_min: float,
    range_max: float,
    config: TickConfig,
    model_to_pixel: Callable[[float], float],
    pixel_margin: float = 2.0,
    pixel_max: float | None = None,
) -> Iterator[TickInfo]:
    """
    Generate tick marks for a given range.

    Args:
        range_min: Minimum value in model space.
        range_max: Maximum value in model space.
        config: TickConfig from compute_nice_interval().
        model_to_pixel: Function to convert model position to pixel position.
        pixel_margin: Margin from edges to skip ticks (prevents overflow).
        pixel_max: Maximum pixel value (for bounds checking).

    Yields:
        TickInfo for each tick in the range.
    """
    interval = config.interval
    start = math.floor(range_min / interval) * interval
    tick_idx = int(round(start / interval))

    current = start
    while current <= range_max:
        pixel = model_to_pixel(current)
        if pixel_max is not None and (pixel < pixel_margin or pixel >= pixel_max - pixel_margin):
            current += interval
            tick_idx += 1
            continue

        is_major = tick_idx % config.major_every == 0

        # Format label
        if config.label_precision == 0:
            label = str(int(round(current)))
        else:
            label = f"{current:.{config.label_precision}f}"

        yield TickInfo(
            position=current,
            pixel=pixel,
            is_major=is_major,
            label=label,
        )

        current += interval
        tick_idx += 1


def format_value(value: float, precision: int) -> str:
    """
    Format a value with the given precision.

    Args:
        value: The value to format.
        precision: Number of decimal places (0 for integer).

    Returns:
        Formatted string.
    """
    if precision == 0:
        return str(int(round(value)))
    return f"{value:.{precision}f}"
