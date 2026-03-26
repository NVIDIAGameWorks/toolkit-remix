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

__all__ = ("TestGradientUtils",)

import numpy as np
import omni.kit.test

from omni.flux.utils.widget.gradient import create_checkerboard, create_multi_stop_gradient


class TestGradientUtils(omni.kit.test.AsyncTestCase):
    """Unit tests for gradient utility functions."""

    # ------------------------------------------------------------------
    # create_multi_stop_gradient
    # ------------------------------------------------------------------

    async def test_gradient_empty_stops_returns_transparent_black(self):
        """An empty stops list should produce an all-zero (transparent black) image."""
        result = create_multi_stop_gradient(16, 1, [])
        self.assertEqual(result.shape, (1, 16, 4))
        self.assertEqual(result.dtype, np.uint8)
        np.testing.assert_array_equal(result, 0)

    async def test_gradient_single_stop_fills_solid(self):
        """A single stop should fill the entire image with that color."""
        result = create_multi_stop_gradient(10, 2, [(0.5, (100, 150, 200, 255))])
        self.assertEqual(result.shape, (2, 10, 4))
        for row in range(2):
            for col in range(10):
                np.testing.assert_array_equal(result[row, col], [100, 150, 200, 255])

    async def test_gradient_two_stops_endpoints(self):
        """With two stops at t=0 and t=1, the first and last pixels should match."""
        result = create_multi_stop_gradient(
            100,
            1,
            [
                (0.0, (0, 0, 0, 255)),
                (1.0, (255, 255, 255, 255)),
            ],
        )
        # First pixel should be close to black
        np.testing.assert_array_less(result[0, 0, :3], 5)
        self.assertEqual(result[0, 0, 3], 255)
        # Last pixel should be close to white
        np.testing.assert_array_less(250, result[0, -1, :3])
        self.assertEqual(result[0, -1, 3], 255)

    async def test_gradient_two_stops_midpoint(self):
        """Midpoint of a black-to-white gradient should be approximately 128."""
        result = create_multi_stop_gradient(
            101,
            1,
            [
                (0.0, (0, 0, 0, 255)),
                (1.0, (254, 254, 254, 255)),
            ],
        )
        mid = result[0, 50, :3]
        for ch in range(3):
            self.assertAlmostEqual(int(mid[ch]), 127, delta=2)

    async def test_gradient_three_stops(self):
        """Three stops should produce correct colors at their positions."""
        result = create_multi_stop_gradient(
            101,
            1,
            [
                (0.0, (255, 0, 0, 255)),
                (0.5, (0, 255, 0, 255)),
                (1.0, (0, 0, 255, 255)),
            ],
        )
        # At pixel 0 -> red
        self.assertGreater(result[0, 0, 0], 250)
        self.assertLess(result[0, 0, 1], 5)
        # At pixel 50 (t=0.5) -> green
        self.assertLess(result[0, 50, 0], 5)
        self.assertGreater(result[0, 50, 1], 250)
        # At pixel 100 (t=1.0) -> blue
        self.assertLess(result[0, 100, 0], 5)
        self.assertGreater(result[0, 100, 2], 250)

    async def test_gradient_zero_width_returns_empty(self):
        """Zero width should return an empty array with correct shape."""
        result = create_multi_stop_gradient(0, 1, [(0.0, (128, 128, 128, 255))])
        self.assertEqual(result.shape, (1, 0, 4))

    async def test_gradient_zero_height_returns_empty(self):
        """Zero height should return an empty array with correct shape."""
        result = create_multi_stop_gradient(10, 0, [(0.0, (128, 128, 128, 255))])
        self.assertEqual(result.shape, (0, 10, 4))

    async def test_gradient_width_one(self):
        """Width of 1 should produce a single pixel matching the first stop."""
        result = create_multi_stop_gradient(
            1,
            1,
            [
                (0.0, (100, 100, 100, 255)),
                (1.0, (200, 200, 200, 255)),
            ],
        )
        self.assertEqual(result.shape, (1, 1, 4))
        # With width=1, t = 0/(max(0,1)) = 0, so we get the first stop color.
        np.testing.assert_array_equal(result[0, 0], [100, 100, 100, 255])

    async def test_gradient_height_broadcast(self):
        """All rows should be identical (the gradient is only horizontal)."""
        result = create_multi_stop_gradient(
            10,
            5,
            [
                (0.0, (0, 0, 0, 255)),
                (1.0, (255, 255, 255, 255)),
            ],
        )
        for row in range(1, 5):
            np.testing.assert_array_equal(result[0], result[row])

    async def test_gradient_alpha_interpolation(self):
        """Alpha channel should interpolate independently from RGB."""
        result = create_multi_stop_gradient(
            101,
            1,
            [
                (0.0, (128, 128, 128, 0)),
                (1.0, (128, 128, 128, 254)),
            ],
        )
        # Midpoint alpha should be approximately 127
        self.assertAlmostEqual(int(result[0, 50, 3]), 127, delta=2)
        # RGB should stay constant
        for col in range(0, 101, 10):
            for ch in range(3):
                self.assertAlmostEqual(int(result[0, col, ch]), 128, delta=2)

    # ------------------------------------------------------------------
    # create_checkerboard
    # ------------------------------------------------------------------

    async def test_checkerboard_shape_and_dtype(self):
        """Checkerboard should return the correct shape and dtype."""
        result = create_checkerboard(32, 16, cell_size=4)
        self.assertEqual(result.shape, (16, 32, 4))
        self.assertEqual(result.dtype, np.uint8)

    async def test_checkerboard_two_colors_only(self):
        """Checkerboard should contain exactly two distinct colors."""
        result = create_checkerboard(16, 16, cell_size=4)
        unique = np.unique(result.reshape(-1, 4), axis=0)
        self.assertEqual(len(unique), 2)
        # Should be light gray and dark gray
        light = [180, 180, 180, 255]
        dark = [120, 120, 120, 255]
        colors = unique.tolist()
        self.assertIn(light, colors)
        self.assertIn(dark, colors)

    async def test_checkerboard_alternates(self):
        """Adjacent cells should alternate colors."""
        result = create_checkerboard(16, 16, cell_size=4)
        # Top-left cell (0,0) and adjacent cell (0,4) should differ
        self.assertFalse(np.array_equal(result[0, 0], result[0, 4]))
        # Top-left cell (0,0) and diagonal cell (4,4) should be the same
        np.testing.assert_array_equal(result[0, 0], result[4, 4])

    async def test_checkerboard_zero_dimensions(self):
        """Zero-sized dimensions should produce empty arrays."""
        result0w = create_checkerboard(0, 16)
        self.assertEqual(result0w.shape, (16, 0, 4))
        result0h = create_checkerboard(16, 0)
        self.assertEqual(result0h.shape, (0, 16, 4))

    async def test_checkerboard_cell_size_one(self):
        """Cell size of 1 should create a pixel-level checkerboard."""
        result = create_checkerboard(4, 4, cell_size=1)
        # (0,0) and (0,1) should differ
        self.assertFalse(np.array_equal(result[0, 0], result[0, 1]))
        # (0,0) and (1,1) should be the same
        np.testing.assert_array_equal(result[0, 0], result[1, 1])

    async def test_checkerboard_fully_opaque(self):
        """All pixels should have alpha = 255."""
        result = create_checkerboard(20, 20, cell_size=5)
        np.testing.assert_array_equal(result[:, :, 3], 255)
