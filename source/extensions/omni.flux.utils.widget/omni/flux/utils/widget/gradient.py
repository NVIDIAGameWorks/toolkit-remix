"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def _find_surrounding_stops(stops: Sequence[tuple[float, tuple]], time: float) -> tuple[int, int, float]:
    """Find the indices of stops surrounding a given time and interpolation fraction.

    Args:
        stops: Sequence of ``(time, data)`` tuples sorted by time.
        time: The time position to find surrounding stops for.

    Returns:
        A tuple ``(left_idx, right_idx, frac)`` where:
        - left_idx: Index of the stop at or before time
        - right_idx: Index of the stop at or after time
        - frac: Interpolation fraction in [0, 1] between the two stops
    """
    if not stops or len(stops) == 1:
        return (0, 0, 0.0)

    # Find the first stop at or after the target time
    right_idx = 0
    for idx, (stop_t, _) in enumerate(stops):
        if stop_t >= time:
            right_idx = idx
            break
    else:
        right_idx = len(stops) - 1

    left_idx = max(right_idx - 1, 0)
    t_left, _ = stops[left_idx]
    t_right, _ = stops[right_idx]

    # Handle edge cases
    if left_idx == right_idx or t_right == t_left:
        return (left_idx, right_idx, 0.0)

    # Calculate interpolation fraction
    frac = (time - t_left) / (t_right - t_left)
    return (left_idx, right_idx, max(0.0, min(1.0, frac)))


def create_gradient_1d(width: int, height: int, int1: int, int2: int, is_horizontal: bool) -> np.ndarray:
    """
    Create a 1d gradient

    Args:
        width: width of the gradient
        height: height of the gradient
        int1: start number of the gradient, like 0
        int2: end number of the gradient, like 255
        is_horizontal: horizontal or vertical gradient

    Returns:
        The 1d gradient
    """
    if is_horizontal:
        return np.tile(np.linspace(int1, int2, width, dtype=np.uint8), (height, 1))
    return np.tile(np.linspace(int1, int2, height, dtype=np.uint8), (width, 1)).T


def create_gradient(
    width: int, height: int, values1: tuple[int, ...], values2: tuple[int, ...], is_horizontal_list: tuple[bool, ...]
) -> np.ndarray:
    """
    Create a gradient (like a RGBA) of any dimension

    Args:
        width: width of the gradient
        height: height of the gradient
        values1: start values (like (0, 0, 0, 255)) of the gradient. Work with any dimension.
        values2: end values (like (255, 255, 255, 255)) of the gradient. Work with any dimension.
        is_horizontal_list: horizontal or vertical gradient (like (True, True, True, True))

    Returns:
        The gradient values
    """
    result = np.zeros((height, width, len(values1)), dtype=np.uint8)

    for i, (value1, value2, is_horizontal) in enumerate(zip(values1, values2, is_horizontal_list)):
        result[:, :, i] = create_gradient_1d(width, height, value1, value2, is_horizontal)

    return result


def create_multi_stop_gradient(
    width: int,
    height: int,
    stops: Sequence[tuple[float, tuple[int, int, int, int]]],
) -> np.ndarray:
    """Create a horizontal RGBA gradient with multiple color stops.

    Each stop is a ``(time, (r, g, b, a))`` pair where *time* is in [0, 1]
    and the color channels are integers in [0, 255].  Stops must be sorted
    by *time*.  The function linearly interpolates between adjacent stops to
    fill a ``(height, width, 4)`` uint8 array suitable for
    ``ui.ByteImageProvider.set_bytes_data``.

    If fewer than two stops are provided the entire image is filled with the
    single stop color (or transparent black when the list is empty).

    Args:
        width: Pixel width of the output image.
        height: Pixel height of the output image.
        stops: Sequence of ``(time, (r, g, b, a))`` tuples sorted by time.

    Returns:
        A ``numpy.ndarray`` of shape ``(height, width, 4)`` and dtype uint8.
    """
    result = np.zeros((height, width, 4), dtype=np.uint8)
    if width == 0 or height == 0:
        return result

    if not stops:
        return result

    if len(stops) == 1:
        for ch in range(4):
            result[:, :, ch] = stops[0][1][ch]
        return result

    # Build a 1-D row of width pixels by lerping between adjacent stops.
    row = np.zeros((width, 4), dtype=np.float64)
    for col in range(width):
        t = col / max(width - 1, 1)
        left_idx, right_idx, frac = _find_surrounding_stops(stops, t)

        color_left = stops[left_idx][1]
        color_right = stops[right_idx][1]

        for ch in range(4):
            row[col, ch] = color_left[ch] * (1.0 - frac) + color_right[ch] * frac

    row_uint8 = np.clip(row, 0, 255).astype(np.uint8)
    result[:] = row_uint8[np.newaxis, :, :]
    return result


def create_checkerboard(width: int, height: int, cell_size: int = 4) -> np.ndarray:
    """Create an RGBA checkerboard pattern (light/dark gray) for alpha previews.

    Args:
        width: Pixel width of the output image.
        height: Pixel height of the output image.
        cell_size: Size of each checker cell in pixels.

    Returns:
        A ``numpy.ndarray`` of shape ``(height, width, 4)`` and dtype uint8.
    """
    result = np.zeros((height, width, 4), dtype=np.uint8)
    if width == 0 or height == 0:
        return result
    ys, xs = np.mgrid[:height, :width]
    mask = ((xs // cell_size) + (ys // cell_size)) % 2 == 0
    result[mask] = [180, 180, 180, 255]
    result[~mask] = [120, 120, 120, 255]
    return result


def sample_gradient_at_time(
    stops: Sequence[tuple[float, tuple[float, float, float, float]]], time: float
) -> tuple[float, float, float, float]:
    """Sample a multi-stop gradient at a specific time using linear interpolation.

    This is a shared utility function used both for rendering gradients and
    for sampling colors when adding new keyframes.

    Args:
        stops: Sequence of ``(time, (r, g, b, a))`` tuples where time is in [0, 1]
              and color channels are floats in [0, 1]. Must be sorted by time.
        time: The time position to sample at, in [0, 1].

    Returns:
        A tuple ``(r, g, b, a)`` with interpolated color values as floats in [0, 1].
    """
    if not stops:
        return (0.0, 0.0, 0.0, 0.0)
    if len(stops) == 1:
        return stops[0][1]

    left_idx, right_idx, frac = _find_surrounding_stops(stops, time)
    color_left = stops[left_idx][1]
    color_right = stops[right_idx][1]

    return tuple(color_left[ch] * (1.0 - frac) + color_right[ch] * frac for ch in range(4))
