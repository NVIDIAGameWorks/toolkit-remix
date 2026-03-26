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

Unit tests for tangent computation math functions.

Tests the TANGENT_BEHAVIOR.md specification implementation:
- LINEAR tangent at midpoint
- FLAT tangent at neighbor X
- AUTO boundary handling (treat as LINEAR)
- SMOOTH tangent (user angle, computed length)
"""

import omni.kit.test

from omni.flux.fcurve.widget.model import FCurve, FCurveKey, TangentType, CurveBounds
from omni.flux.fcurve.widget._internal.math import process_curve

__all__ = [
    "TestAutoTangentBoundary",
    "TestFlatTangent",
    "TestLinearTangent",
]

# Wide bounds for tests so tangents are not clamped
_DEFAULT_BOUNDS = CurveBounds(time_min=-100.0, time_max=100.0, value_min=-100.0, value_max=100.0)
_X_FLIP_THRESHOLD = 0.001


def _process_and_get_tangents(keys: list, key_index: int) -> tuple[tuple[float, float], tuple[float, float]]:
    """Create curve, process it, return (in_tan, out_tan) for the key at key_index."""
    curve = FCurve(id="test", keys=keys)
    process_curve(curve, _DEFAULT_BOUNDS, _X_FLIP_THRESHOLD)
    key = curve.keys[key_index]
    return (key.in_tangent_x, key.in_tangent_y), (key.out_tangent_x, key.out_tangent_y)


class TestLinearTangent(omni.kit.test.AsyncTestCase):
    """Test LINEAR tangent places handle at midpoint to neighbor."""

    async def test_linear_tangent_midpoint_to_neighbor(self):
        """LINEAR tangent should place handle at midpoint between keys."""
        keys = [
            FCurveKey(time=0.0, value=0.0, in_tangent_type=TangentType.LINEAR, out_tangent_type=TangentType.LINEAR),
            FCurveKey(time=1.0, value=1.0, in_tangent_type=TangentType.LINEAR, out_tangent_type=TangentType.LINEAR),
        ]

        # First key's out tangent
        in_tan, out_tan = _process_and_get_tangents(keys, 0)

        # Out tangent should be at midpoint: (1.0 - 0.0) / 2.0 = 0.5
        self.assertAlmostEqual(out_tan[0], 0.5, places=5)
        self.assertAlmostEqual(out_tan[1], 0.5, places=5)

        # Second key's in tangent
        in_tan, out_tan = _process_and_get_tangents(keys, 1)

        # In tangent should be at midpoint: -(1.0 - 0.0) / 2.0 = -0.5
        self.assertAlmostEqual(in_tan[0], -0.5, places=5)
        self.assertAlmostEqual(in_tan[1], -0.5, places=5)

    async def test_linear_tangent_produces_straight_line(self):
        """Two LINEAR tangents should produce a straight line segment."""
        keys = [
            FCurveKey(time=0.0, value=0.0, out_tangent_type=TangentType.LINEAR),
            FCurveKey(time=2.0, value=4.0, in_tangent_type=TangentType.LINEAR),
        ]

        _, out_tan = _process_and_get_tangents(keys, 0)
        in_tan, _ = _process_and_get_tangents(keys, 1)

        # Both tangents should be on the line connecting the keyframes
        # out_tan from key0: midpoint to key1 = (1.0, 2.0)
        self.assertAlmostEqual(out_tan[0], 1.0, places=5)
        self.assertAlmostEqual(out_tan[1], 2.0, places=5)

        # in_tan from key1: midpoint from key0 = (-1.0, -2.0)
        self.assertAlmostEqual(in_tan[0], -1.0, places=5)
        self.assertAlmostEqual(in_tan[1], -2.0, places=5)


class TestFlatTangent(omni.kit.test.AsyncTestCase):
    """Test FLAT tangent extends to neighbor X with Y=0."""

    async def test_flat_tangent_horizontal(self):
        """FLAT tangent should be horizontal (Y offset = 0)."""
        keys = [
            FCurveKey(time=0.0, value=0.0, out_tangent_type=TangentType.FLAT),
            FCurveKey(time=1.0, value=1.0, in_tangent_type=TangentType.FLAT),
        ]

        _, out_tan = _process_and_get_tangents(keys, 0)
        in_tan, _ = _process_and_get_tangents(keys, 1)

        # Out tangent: X should extend halfway to next key (0.5), Y should be 0
        self.assertAlmostEqual(out_tan[0], 0.5, places=5)
        self.assertAlmostEqual(out_tan[1], 0.0, places=5)

        # In tangent: X should extend halfway to prev key (-0.5), Y should be 0
        self.assertAlmostEqual(in_tan[0], -0.5, places=5)
        self.assertAlmostEqual(in_tan[1], 0.0, places=5)


class TestAutoTangentBoundary(omni.kit.test.AsyncTestCase):
    """Test AUTO tangent at boundaries is treated as LINEAR."""

    async def test_auto_at_first_key_uses_linear(self):
        """AUTO tangent at first key should behave like LINEAR (midpoint)."""
        keys = [
            FCurveKey(time=0.0, value=0.0, out_tangent_type=TangentType.AUTO),
            FCurveKey(time=1.0, value=1.0),
        ]

        _, out_tan = _process_and_get_tangents(keys, 0)

        # Should be midpoint like LINEAR
        self.assertAlmostEqual(out_tan[0], 0.5, places=5)
        self.assertAlmostEqual(out_tan[1], 0.5, places=5)

    async def test_auto_at_last_key_uses_linear(self):
        """AUTO tangent at last key should behave like LINEAR (midpoint)."""
        keys = [
            FCurveKey(time=0.0, value=0.0),
            FCurveKey(time=1.0, value=1.0, in_tangent_type=TangentType.AUTO),
        ]

        in_tan, _ = _process_and_get_tangents(keys, 1)

        # Should be midpoint like LINEAR
        self.assertAlmostEqual(in_tan[0], -0.5, places=5)
        self.assertAlmostEqual(in_tan[1], -0.5, places=5)

    async def test_auto_middle_key_smooth_tangent(self):
        """AUTO tangent at middle key should compute smooth (Catmull-Rom) tangent."""
        keys = [
            FCurveKey(time=0.0, value=0.0),
            FCurveKey(time=1.0, value=1.0, in_tangent_type=TangentType.AUTO, out_tangent_type=TangentType.AUTO),
            FCurveKey(time=2.0, value=0.0),
        ]

        in_tan, out_tan = _process_and_get_tangents(keys, 1)

        # Tangent should be parallel to line from key0 to key2
        # That line goes from (0,0) to (2,0), so slope = 0
        # in_tan X = -(1.0 - 0.0) / 2.0 = -0.5
        # out_tan X = (2.0 - 1.0) / 2.0 = 0.5
        # Y should be 0 (horizontal tangent since slope=0)
        self.assertAlmostEqual(in_tan[0], -0.5, places=5)
        self.assertAlmostEqual(in_tan[1], 0.0, places=5)
        self.assertAlmostEqual(out_tan[0], 0.5, places=5)
        self.assertAlmostEqual(out_tan[1], 0.0, places=5)
