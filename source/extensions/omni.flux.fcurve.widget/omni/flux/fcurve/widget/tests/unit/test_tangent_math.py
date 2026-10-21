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

import math

import omni.kit.test

from ... import evaluate_curve
from ..._internal.math import process_curve
from ...model import CurveBounds, FCurve, FCurveKey, InfinityType, TangentType

__all__ = [
    "TestAutoTangentBoundary",
    "TestCurveEvaluation",
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


class TestCurveEvaluation(omni.kit.test.AsyncTestCase):
    """Test evaluated values match the rendered curve."""

    async def test_evaluate_curve_at_key_time_returns_exact_value(self):
        """An exact key time should return that key's value."""
        # Arrange
        curve = FCurve(id="test", keys=[FCurveKey(time=0.0, value=1.0), FCurveKey(time=1.0, value=3.0)])

        # Act
        value = evaluate_curve(curve, 1.0)

        # Assert
        self.assertEqual(value, 3.0)

    async def test_evaluate_curve_on_step_segment_holds_left_value(self):
        """A STEP segment should hold its left value until the right endpoint."""
        # Arrange
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(time=0.0, value=2.0, out_tangent_type=TangentType.STEP),
                FCurveKey(time=1.0, value=5.0),
            ],
        )

        # Act
        value = evaluate_curve(curve, 0.75)

        # Assert
        self.assertEqual(value, 2.0)

    async def test_evaluate_curve_on_bezier_segment_uses_tangent_offsets(self):
        """A cubic segment should use both stored tangent offsets."""
        # Arrange
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(time=0.0, value=0.0, out_tangent_x=1.0, out_tangent_y=1.0),
                FCurveKey(time=1.0, value=0.0, in_tangent_x=-1.0, in_tangent_y=1.0),
            ],
        )

        # Act
        value = evaluate_curve(curve, 0.5)

        # Assert
        self.assertAlmostEqual(value, 0.75)

    async def test_evaluate_curve_with_asymmetric_time_controls_returns_expected_values(self):
        """Invert asymmetric segment time coordinates before evaluating values."""
        for time, expected in (
            (5 / 32, 7 / 16),  # Parameter 1/4.
            (45 / 64, 9 / 16),  # Parameter 3/4.
            (25 / 108, 13 / 27),  # Parameter 1/3.
        ):
            with self.subTest(title=f"time={time}"):
                # Arrange
                curve = FCurve(
                    id="asymmetric",
                    keys=[
                        FCurveKey(time=0.0, value=0.0, out_tangent_x=1 / 8, out_tangent_y=1.0),
                        FCurveKey(time=1.0, value=1.0, in_tangent_x=-3 / 8, in_tangent_y=-1.0),
                    ],
                )

                # Act
                value = evaluate_curve(curve, time)

                # Assert
                self.assertAlmostEqual(value, expected, places=10)

    async def test_evaluate_curve_outside_range_matches_infinity_modes(self):
        """CONSTANT and LINEAR infinity should match the renderer's endpoint tangents."""
        cases = [
            (FCurve(id="constant", keys=[FCurveKey(time=1.0, value=2.0)]), 0.0, 2.0),
            (
                FCurve(
                    id="pre-linear",
                    pre_infinity=InfinityType.LINEAR,
                    keys=[
                        FCurveKey(time=1.0, value=2.0, out_tangent_x=2.0, out_tangent_y=4.0),
                        FCurveKey(time=3.0, value=6.0),
                    ],
                ),
                0.0,
                0.0,
            ),
            (
                FCurve(
                    id="post-linear",
                    post_infinity=InfinityType.LINEAR,
                    keys=[
                        FCurveKey(time=1.0, value=2.0),
                        FCurveKey(time=3.0, value=6.0, in_tangent_x=-2.0, in_tangent_y=-4.0),
                    ],
                ),
                4.0,
                8.0,
            ),
        ]
        for curve, time, expected in cases:
            with self.subTest(title=curve.id):
                # Arrange

                # Act
                value = evaluate_curve(curve, time)

                # Assert
                self.assertEqual(value, expected)

    async def test_evaluate_curve_with_singleton_or_zero_dx_holds_value(self):
        """A singleton or zero-X infinity tangent should hold its endpoint value."""
        cases = [
            (
                FCurve(id="singleton", post_infinity=InfinityType.LINEAR, keys=[FCurveKey(time=1.0, value=2.0)]),
                4.0,
                2.0,
            ),
            (
                FCurve(
                    id="zero-dx",
                    pre_infinity=InfinityType.LINEAR,
                    keys=[
                        FCurveKey(time=1.0, value=2.0, out_tangent_x=0.0, out_tangent_y=4.0),
                        FCurveKey(time=3.0, value=6.0),
                    ],
                ),
                0.0,
                2.0,
            ),
        ]
        for curve, time, expected in cases:
            with self.subTest(title=curve.id):
                # Arrange

                # Act
                value = evaluate_curve(curve, time)

                # Assert
                self.assertEqual(value, expected)

    async def test_evaluate_curve_with_empty_curve_raises_value_error(self):
        """An empty curve should be rejected."""
        # Arrange
        curve = FCurve(id="empty")

        # Act / Assert
        with self.assertRaises(ValueError):
            evaluate_curve(curve, 0.0)

    async def test_evaluate_curve_with_nonfinite_time_raises_value_error(self):
        """A nonfinite query time should be rejected."""
        for time in (math.inf, -math.inf, math.nan):
            with self.subTest(title=str(time)):
                # Arrange
                curve = FCurve(id="test", keys=[FCurveKey(time=0.0, value=1.0)])

                # Act / Assert
                with self.assertRaises(ValueError):
                    evaluate_curve(curve, time)

    async def test_evaluate_curve_does_not_mutate_curve(self):
        """Evaluation should leave stored keys and tangent offsets unchanged."""
        # Arrange
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(time=0.0, value=0.0, out_tangent_x=0.25, out_tangent_y=1.0),
                FCurveKey(time=1.0, value=0.0, in_tangent_x=-0.25, in_tangent_y=1.0),
            ],
        )
        before = [vars(key).copy() for key in curve.keys]

        # Act
        evaluate_curve(curve, 0.5)

        # Assert
        self.assertEqual([vars(key) for key in curve.keys], before)


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
