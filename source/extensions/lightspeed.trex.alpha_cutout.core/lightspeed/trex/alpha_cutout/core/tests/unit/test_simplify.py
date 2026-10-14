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
"""

__all__ = ["TestSimplifyRingMinimal"]

import numpy as np
from lightspeed.trex.alpha_cutout.core.simplify import simplify_ring_minimal
from omni.kit.test import AsyncTestCase
from shapely.geometry import LineString, Point, Polygon

_TOLERANCE = 1.0


def _max_deviation(original: np.ndarray, simplified: np.ndarray) -> float:
    outline = LineString(np.concatenate((simplified, simplified[:1]), axis=0))
    return max(outline.distance(Point(point)) for point in original)


def _jittered_circle(count: int, radius: float, seed: int = 7) -> np.ndarray:
    angles = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False)
    radii = radius + np.random.default_rng(seed).uniform(-0.3, 0.3, count)
    return np.column_stack((radii * np.cos(angles), radii * np.sin(angles)))


class TestSimplifyRingMinimal(AsyncTestCase):
    """Test the minimal vertex ring simplification."""

    async def test_simplify_ring_minimal_with_square_and_collinear_points_returns_the_corners(self):
        # Arrange
        ring = np.array([(0, 0), (5, 0), (10, 0), (10, 5), (10, 10), (5, 10), (0, 10), (0, 5)], dtype=float)

        # Act
        result = simplify_ring_minimal(ring, _TOLERANCE)

        # Assert
        self.assertEqual(result.shape[0], 4)
        self.assertEqual({tuple(point) for point in result}, {(0, 0), (10, 0), (10, 10), (0, 10)})

    async def test_simplify_ring_minimal_with_noise_under_tolerance_drops_the_noise(self):
        # Arrange
        ring = np.array([(0, 0), (3, 0.4), (6, -0.4), (10, 0), (10, 10), (5, 10.3), (0, 10)], dtype=float)

        # Act
        result = simplify_ring_minimal(ring, _TOLERANCE)

        # Assert
        self.assertEqual(result.shape[0], 4)

    async def test_simplify_ring_minimal_keeps_every_vertex_within_tolerance(self):
        # Arrange
        ring = _jittered_circle(400, 40.0)

        # Act
        result = simplify_ring_minimal(ring, _TOLERANCE)

        # Assert
        self.assertLessEqual(_max_deviation(ring, result), _TOLERANCE + 1e-9)

    async def test_simplify_ring_minimal_uses_no_more_vertices_than_douglas_peucker(self):
        # Arrange
        ring = _jittered_circle(400, 40.0)
        douglas_peucker = Polygon(ring).simplify(_TOLERANCE, preserve_topology=True)

        # Act
        result = simplify_ring_minimal(ring, _TOLERANCE)

        # Assert
        self.assertLessEqual(result.shape[0], len(douglas_peucker.exterior.coords) - 1)

    async def test_simplify_ring_minimal_with_triangle_returns_the_input(self):
        # Arrange
        ring = np.array([(0, 0), (4, 0), (0, 3)], dtype=float)

        # Act
        result = simplify_ring_minimal(ring, _TOLERANCE)

        # Assert
        np.testing.assert_array_equal(result, ring)

    async def test_simplify_ring_minimal_with_zero_tolerance_returns_the_input(self):
        # Arrange
        ring = np.array([(0, 0), (5, 0), (10, 0), (10, 10), (0, 10)], dtype=float)

        # Act
        result = simplify_ring_minimal(ring, 0.0)

        # Assert
        np.testing.assert_array_equal(result, ring)
