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

__all__ = ["TestEarclip"]

import numpy as np
from lightspeed.trex.alpha_cutout.core.triangulate import earclip_polygon_with_holes, triangulate_shapely_polygon
from omni.kit.test import AsyncTestCase
from shapely.geometry import Polygon


def _triangle_areas(vertices: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Return the signed area of every triangle."""
    a = vertices[triangles[:, 0]]
    b = vertices[triangles[:, 1]]
    c = vertices[triangles[:, 2]]
    return 0.5 * ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))


class TestEarclip(AsyncTestCase):
    """Test the ear clipping triangulator."""

    async def test_earclip_convex_polygon_returns_n_minus_2_counter_clockwise_triangles(self):
        # Arrange
        outer = np.array([(0, 0), (4, 0), (5, 2), (4, 4), (0, 4), (-1, 2)], dtype=float)

        # Act
        vertices, triangles = earclip_polygon_with_holes(outer, [])

        # Assert
        self.assertEqual(triangles.shape, (4, 3))
        self.assertTrue((_triangle_areas(vertices, triangles) > 0).all())

    async def test_earclip_clockwise_input_returns_counter_clockwise_triangles(self):
        # Arrange
        outer = np.array([(0, 0), (0, 4), (4, 4), (4, 0)], dtype=float)

        # Act
        vertices, triangles = earclip_polygon_with_holes(outer, [])

        # Assert
        self.assertEqual(triangles.shape, (2, 3))
        self.assertTrue((_triangle_areas(vertices, triangles) > 0).all())

    async def test_earclip_concave_polygon_triangles_cover_polygon_area(self):
        # Arrange
        outer = np.array([(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (4, 3), (4, 4), (0, 4)], dtype=float)

        # Act
        vertices, triangles = earclip_polygon_with_holes(outer, [])

        # Assert
        self.assertAlmostEqual(float(_triangle_areas(vertices, triangles).sum()), 10.0)
        self.assertTrue((_triangle_areas(vertices, triangles) > 0).all())

    async def test_earclip_polygon_with_hole_excludes_hole_area(self):
        # Arrange
        outer = np.array([(0, 0), (4, 0), (4, 4), (0, 4)], dtype=float)
        hole = np.array([(1, 1), (1, 3), (3, 3), (3, 1)], dtype=float)

        # Act
        vertices, triangles = earclip_polygon_with_holes(outer, [hole])

        # Assert
        self.assertEqual(vertices.shape, (8, 2))
        self.assertAlmostEqual(float(_triangle_areas(vertices, triangles).sum()), 12.0)
        self.assertTrue((_triangle_areas(vertices, triangles) > 0).all())

    async def test_earclip_polygon_with_two_holes_bridges_each_hole(self):
        # Arrange
        outer = np.array([(0, 0), (10, 0), (10, 4), (0, 4)], dtype=float)
        holes = [
            np.array([(1, 1), (1, 3), (3, 3), (3, 1)], dtype=float),
            np.array([(6, 1), (6, 3), (8, 3), (8, 1)], dtype=float),
        ]

        # Act
        vertices, triangles = earclip_polygon_with_holes(outer, holes)

        # Assert
        self.assertAlmostEqual(float(_triangle_areas(vertices, triangles).sum()), 40.0 - 8.0)
        self.assertTrue((_triangle_areas(vertices, triangles) > 0).all())

    async def test_earclip_degenerate_collinear_polygon_returns_no_triangles(self):
        # Arrange
        outer = np.array([(0, 0), (1, 0), (2, 0), (3, 0)], dtype=float)

        # Act
        _, triangles = earclip_polygon_with_holes(outer, [])

        # Assert
        self.assertEqual(triangles.shape, (0, 3))

    async def test_earclip_with_fewer_than_three_vertices_returns_no_triangles(self):
        # Arrange
        outer = np.array([(0, 0), (1, 0)], dtype=float)

        # Act
        _, triangles = earclip_polygon_with_holes(outer, [])

        # Assert
        self.assertEqual(triangles.shape, (0, 3))

    async def test_triangulate_shapely_polygon_with_hole_matches_polygon_area(self):
        # Arrange
        polygon = Polygon([(0, 0), (6, 0), (6, 6), (0, 6)], [[(2, 2), (2, 4), (4, 4), (4, 2)]])

        # Act
        vertices, triangles = triangulate_shapely_polygon(polygon)

        # Assert
        self.assertAlmostEqual(float(_triangle_areas(vertices, triangles).sum()), polygon.area)
