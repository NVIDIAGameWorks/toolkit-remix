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

__all__ = ["TestMask"]

import tempfile
from pathlib import Path

import numpy as np
from lightspeed.trex.alpha_cutout.core.mask import (
    build_alpha_field,
    is_alpha_uniformly_opaque,
    load_alpha,
    mask_polygons_to_uv,
    trace_alpha_mask,
    union_geometries,
)
from omni.kit.test import AsyncTestCase
from PIL import Image
from shapely.geometry import Polygon

# A marching squares contour of a binary mask cuts an eighth of a texel off every convex corner and adds the
# same amount at every concave one.
_CORNER_AREA = 0.125
_LEVEL = 0.5


def _square_mask(size: int, low: int, high: int) -> np.ndarray:
    """Build a mask with one opaque square from ``low`` to ``high`` (exclusive)."""
    mask = np.zeros((size, size), dtype=bool)
    mask[low:high, low:high] = True
    return mask


class TestMask(AsyncTestCase):
    """Test the alpha field tracing."""

    async def test_load_alpha_with_rgba_png_returns_alpha_channel(self):
        # Arrange
        alpha = np.zeros((4, 6), dtype=np.uint8)
        alpha[1, 2] = 200
        rgba = np.dstack([np.full_like(alpha, 10), np.full_like(alpha, 20), np.full_like(alpha, 30), alpha])
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "alpha.png"
            Image.fromarray(rgba, "RGBA").save(path)

            # Act
            result = load_alpha(str(path))

        # Assert
        self.assertEqual(result.shape, (4, 6))
        self.assertEqual(int(result[1, 2]), 200)
        self.assertEqual(int(result.sum()), 200)

    async def test_is_alpha_uniformly_opaque_with_all_255_returns_true(self):
        # Arrange
        alpha = np.full((8, 8), 255, dtype=np.uint8)

        # Act
        result = is_alpha_uniformly_opaque(alpha)

        # Assert
        self.assertTrue(result)

    async def test_is_alpha_uniformly_opaque_with_one_transparent_texel_returns_false(self):
        # Arrange
        alpha = np.full((8, 8), 255, dtype=np.uint8)
        alpha[3, 3] = 254

        # Act
        result = is_alpha_uniformly_opaque(alpha)

        # Assert
        self.assertFalse(result)

    async def test_build_alpha_field_with_small_image_keeps_values(self):
        # Arrange
        alpha = np.array([[0, 127, 128, 255]], dtype=np.uint8)

        # Act
        field = build_alpha_field(alpha, trace_resolution=64)

        # Assert
        self.assertEqual(field.tolist(), [[0.0, 127.0, 128.0, 255.0]])

    async def test_build_alpha_field_with_large_image_downscales_longest_side_to_trace_resolution(self):
        # Arrange
        alpha = np.full((256, 512), 255, dtype=np.uint8)

        # Act
        field = build_alpha_field(alpha, trace_resolution=64)

        # Assert
        self.assertEqual(field.shape, (32, 64))
        self.assertTrue((field == 255).all())

    async def test_trace_alpha_mask_with_solid_square_returns_one_polygon_without_holes(self):
        # Arrange
        mask = _square_mask(16, 4, 12)

        # Act
        polygons = trace_alpha_mask(mask, _LEVEL, simplify_tolerance=0.0, edge_margin=0.0, min_island_area=0.0)

        # Assert
        self.assertEqual(len(polygons), 1)
        self.assertEqual(len(polygons[0].interiors), 0)
        self.assertAlmostEqual(polygons[0].area, 64.0 - 4 * _CORNER_AREA)
        self.assertEqual(polygons[0].bounds, (4.0, 4.0, 12.0, 12.0))

    async def test_trace_alpha_mask_with_minimal_outline_returns_valid_polygons_with_no_more_vertices(self):
        # Arrange
        rows, cols = np.mgrid[0:64, 0:64]
        mask = ((rows - 31.5) ** 2 + (cols - 31.5) ** 2) <= 24**2
        greedy = trace_alpha_mask(mask, _LEVEL, simplify_tolerance=1.0, edge_margin=0.0, min_island_area=0.0)

        # Act
        polygons = trace_alpha_mask(
            mask, _LEVEL, simplify_tolerance=1.0, edge_margin=0.0, min_island_area=0.0, minimal_outline=True
        )

        # Assert
        self.assertEqual(len(polygons), 1)
        self.assertTrue(polygons[0].is_valid)
        self.assertLessEqual(len(polygons[0].exterior.coords), len(greedy[0].exterior.coords))
        self.assertAlmostEqual(polygons[0].area, greedy[0].area, delta=0.05 * greedy[0].area)

    async def test_trace_alpha_mask_with_ring_returns_polygon_with_one_hole(self):
        # Arrange
        mask = _square_mask(16, 2, 14)
        mask[6:10, 6:10] = False

        # Act
        polygons = trace_alpha_mask(mask, _LEVEL, simplify_tolerance=0.0, edge_margin=0.0, min_island_area=0.0)

        # Assert
        self.assertEqual(len(polygons), 1)
        self.assertEqual(len(polygons[0].interiors), 1)
        self.assertAlmostEqual(polygons[0].area, 144.0 - 16.0)

    async def test_trace_alpha_mask_with_island_inside_hole_keeps_both_opaque_areas(self):
        # Arrange
        mask = _square_mask(20, 1, 19)
        mask[5:15, 5:15] = False
        mask[9:11, 9:11] = True

        # Act
        polygons = trace_alpha_mask(mask, _LEVEL, simplify_tolerance=0.0, edge_margin=0.0, min_island_area=0.0)

        # Assert
        self.assertEqual(len(polygons), 2)
        self.assertAlmostEqual(sum(polygon.area for polygon in polygons), 324.0 - 100.0 + 4.0 - 4 * _CORNER_AREA)

    async def test_trace_alpha_mask_drops_islands_below_min_island_area(self):
        # Arrange
        mask = _square_mask(16, 2, 10)
        mask[13, 13] = True

        # Act
        polygons = trace_alpha_mask(mask, _LEVEL, simplify_tolerance=0.0, edge_margin=0.0, min_island_area=2.0)

        # Assert
        self.assertEqual(len(polygons), 1)
        self.assertAlmostEqual(polygons[0].area, 64.0 - 4 * _CORNER_AREA)

    async def test_trace_alpha_mask_with_positive_edge_margin_grows_polygon(self):
        # Arrange
        mask = _square_mask(16, 4, 12)

        # Act
        polygons = trace_alpha_mask(mask, _LEVEL, simplify_tolerance=0.0, edge_margin=1.0, min_island_area=0.0)

        # Assert
        self.assertEqual(len(polygons), 1)
        self.assertGreater(polygons[0].area, 90.0)
        self.assertEqual(polygons[0].bounds, (3.0, 3.0, 13.0, 13.0))

    async def test_trace_alpha_mask_with_negative_edge_margin_shrinks_polygon(self):
        # Arrange
        mask = _square_mask(16, 4, 12)

        # Act
        polygons = trace_alpha_mask(mask, _LEVEL, simplify_tolerance=0.0, edge_margin=-1.0, min_island_area=0.0)

        # Assert
        self.assertEqual(len(polygons), 1)
        self.assertLess(polygons[0].area, 40.0)
        self.assertEqual(polygons[0].bounds, (5.0, 5.0, 11.0, 11.0))

    async def test_trace_alpha_mask_with_diagonal_edge_returns_straight_line(self):
        # Arrange
        size = 16
        rows, cols = np.mgrid[0:size, 0:size]
        mask = cols >= rows

        # Act
        polygons = trace_alpha_mask(mask, _LEVEL, simplify_tolerance=0.1, edge_margin=0.0, min_island_area=0.0)

        # Assert
        self.assertEqual(len(polygons), 1)
        self.assertLessEqual(len(polygons[0].exterior.coords), 10)

    async def test_trace_alpha_mask_with_soft_alpha_places_edge_between_texels(self):
        # Arrange
        field = np.zeros((8, 8), dtype=np.float32)
        field[:, 4:] = 255.0
        field[:, 3] = 128.0

        # Act
        polygons = trace_alpha_mask(field, 128.0, simplify_tolerance=0.0, edge_margin=0.0, min_island_area=0.0)

        # Assert
        self.assertEqual(len(polygons), 1)
        self.assertAlmostEqual(polygons[0].bounds[0], 3.5)

    async def test_trace_alpha_mask_with_empty_mask_returns_no_polygons(self):
        # Arrange
        mask = np.zeros((8, 8), dtype=bool)

        # Act
        polygons = trace_alpha_mask(mask, _LEVEL, simplify_tolerance=1.0, edge_margin=1.0, min_island_area=4.0)

        # Assert
        self.assertEqual(polygons, [])

    async def test_mask_polygons_to_uv_flips_v_and_normalizes_to_unit_square(self):
        # Arrange
        polygon = Polygon([(0, 0), (4, 0), (4, 2), (0, 2)])

        # Act
        result = mask_polygons_to_uv([polygon], (8, 16))

        # Assert
        self.assertEqual(result[0].bounds, (0.0, 0.75, 0.25, 1.0))

    async def test_union_geometries_with_overlapping_squares_returns_combined_area(self):
        # Arrange
        squares = [Polygon([(i, 0), (i + 2, 0), (i + 2, 2), (i, 2)]) for i in range(0, 5)]

        # Act
        union = union_geometries(squares)

        # Assert
        self.assertAlmostEqual(union.area, 12.0)
