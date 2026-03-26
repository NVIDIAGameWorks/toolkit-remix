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

Unit tests for tangent linking/mirroring in compute_keyframe_tangents.

These tests exercise the production code in process_curve / compute_keyframe_tangents
and verify:
  1. Linked mirroring math — angle, length, exact values (TestLinkedMirroring)
  2. Type propagation — dominant side copies its type to the opposite (TestMirroringTypePropagation)
  3. Broken independence — no mirroring, no type copying (TestBrokenTangentIndependence)
  4. Boundary zeroing — first/last keys zero their missing-neighbor tangent (TestBoundaryKeyBehavior)

Key constraints of compute_keyframe_tangents:
  - Mirroring requires both prev_key and next_key (3+ key curve, middle key).
  - CUSTOM is the only type where handle values pass through to the tangent.
  - Other types (LINEAR, FLAT, AUTO, SMOOTH) derive tangent from neighbor distances.
  - Boundary tangents (no prev → in, no next → out) are always zeroed.
"""

import math
import omni.kit.test

from omni.flux.fcurve.widget.model import FCurve, FCurveKey, TangentType, CurveBounds
from omni.flux.fcurve.widget._internal.math import process_curve

__all__ = [
    "TestBoundaryKeyBehavior",
    "TestBrokenTangentIndependence",
    "TestLinkedMirroring",
    "TestMirroringTypePropagation",
]

_BOUNDS = CurveBounds(time_min=-100.0, time_max=100.0, value_min=-100.0, value_max=100.0)
_THRESHOLD = 0.001

_MID_TIME = 0.5
_MID_VALUE = 0.5
_PREV_TIME = -99.0
_NEXT_TIME = 99.0


def _process_middle_key(middle: FCurveKey, tangent_positions: dict | None = None) -> FCurveKey:
    """Build a 3-key curve, run process_curve, return the middle key.

    Outer keys at -99/99 keep tangent clamping from interfering with test values.
    """
    curve = FCurve(
        id="test",
        keys=[
            FCurveKey(time=_PREV_TIME, value=_MID_VALUE),
            middle,
            FCurveKey(time=_NEXT_TIME, value=_MID_VALUE),
        ],
    )
    process_curve(curve, _BOUNDS, _THRESHOLD, tangent_positions=tangent_positions or {})
    return curve.keys[1]


def _length(x: float, y: float) -> float:
    return math.sqrt(x * x + y * y)


def _normalized(x: float, y: float) -> tuple[float, float]:
    ln = _length(x, y)
    if ln < 1e-12:
        return (0.0, 0.0)
    return (x / ln, y / ln)


def _angle_diff(ax: float, ay: float, bx: float, by: float) -> float:
    """Absolute angular difference normalized to [0, pi]."""
    a1 = math.atan2(ay, ax)
    a2 = math.atan2(by, bx)
    d = abs(a1 - a2)
    while d > math.pi:
        d = abs(d - 2 * math.pi)
    return d


# ─────────────────────────────────────────────────────────────────────────────
# 1. Linked mirroring math
#
# For CUSTOM type, compute_keyframe_tangents does:
#   Step 1 (handle mirror):  opposite_handle = -dominant_handle.normalized() * opposite_handle.length()
#   Step 2 (type compute):   tangent = handle  (CUSTOM passthrough)
#   Step 3 (tangent mirror): opposite_tangent = -dominant_tangent.normalized() * opposite_tangent.length()
#
# Net result for CUSTOM (step 3 overwrites step 2 on the opposite side):
#   dominant_tangent  = dominant_handle                              (unchanged)
#   opposite_tangent  = -normalized(dominant_handle) * length(opposite_handle)
# ─────────────────────────────────────────────────────────────────────────────


class TestLinkedMirroring(omni.kit.test.AsyncTestCase):
    """Verify mirroring math through process_curve with linked CUSTOM tangents."""

    def _linked(self, in_x, in_y, out_x, out_y, in_dominates=False):
        middle = FCurveKey(
            time=_MID_TIME,
            value=_MID_VALUE,
            in_tangent_type=TangentType.CUSTOM,
            out_tangent_type=TangentType.CUSTOM,
            in_tangent_x=in_x,
            in_tangent_y=in_y,
            out_tangent_x=out_x,
            out_tangent_y=out_y,
            tangent_broken=False,
        )
        if in_dominates:
            tp = {(1, True): (in_x, in_y), (1, False): (out_x, out_y)}
        else:
            tp = {(1, False): (out_x, out_y)}
        return _process_middle_key(middle, tp)

    def _assert_exact_mirror(self, k, dom_x, dom_y, opp_orig_x, opp_orig_y, in_dominates):
        """Assert exact mirrored values against the formula."""
        opp_len = _length(opp_orig_x, opp_orig_y)
        nx, ny = _normalized(dom_x, dom_y)
        expected_opp = (-nx * opp_len, -ny * opp_len)

        if in_dominates:
            self.assertAlmostEqual(k.in_tangent_x, dom_x, places=4, msg="dominant IN X")
            self.assertAlmostEqual(k.in_tangent_y, dom_y, places=4, msg="dominant IN Y")
            self.assertAlmostEqual(k.out_tangent_x, expected_opp[0], places=4, msg="mirrored OUT X")
            self.assertAlmostEqual(k.out_tangent_y, expected_opp[1], places=4, msg="mirrored OUT Y")
        else:
            self.assertAlmostEqual(k.out_tangent_x, dom_x, places=4, msg="dominant OUT X")
            self.assertAlmostEqual(k.out_tangent_y, dom_y, places=4, msg="dominant OUT Y")
            self.assertAlmostEqual(k.in_tangent_x, expected_opp[0], places=4, msg="mirrored IN X")
            self.assertAlmostEqual(k.in_tangent_y, expected_opp[1], places=4, msg="mirrored IN Y")

    async def test_horizontal_out_dominates(self):
        """OUT(1,0) dom → IN = -normalized(1,0) * 1.0 = (-1,0)."""
        k = self._linked(-1.0, 0.0, 1.0, 0.0)
        self._assert_exact_mirror(k, 1.0, 0.0, -1.0, 0.0, in_dominates=False)

    async def test_horizontal_in_dominates(self):
        """IN(-1,0) dom → OUT = -normalized(-1,0) * 1.0 = (1,0)."""
        k = self._linked(-1.0, 0.0, 1.0, 0.0, in_dominates=True)
        self._assert_exact_mirror(k, -1.0, 0.0, 1.0, 0.0, in_dominates=True)

    async def test_diagonal_out_dominates(self):
        """OUT(0.3,0.2) dom, IN(-0.2,0) → exact mirrored IN."""
        k = self._linked(-0.2, 0.0, 0.3, 0.2)
        self._assert_exact_mirror(k, 0.3, 0.2, -0.2, 0.0, in_dominates=False)

    async def test_diagonal_in_dominates(self):
        """IN(-0.5,0.3) dom, OUT(0.8,-0.2) → exact mirrored OUT."""
        k = self._linked(-0.5, 0.3, 0.8, -0.2, in_dominates=True)
        self._assert_exact_mirror(k, -0.5, 0.3, 0.8, -0.2, in_dominates=True)

    async def test_asymmetric_lengths_preserved(self):
        """IN length 2.236, OUT length 1.581 — both preserved after mirroring."""
        in_x, in_y, out_x, out_y = -2.0, 1.0, 1.5, 0.5
        k = self._linked(in_x, in_y, out_x, out_y)
        self.assertAlmostEqual(_length(k.out_tangent_x, k.out_tangent_y), _length(out_x, out_y), places=4)
        self.assertAlmostEqual(_length(k.in_tangent_x, k.in_tangent_y), _length(in_x, in_y), places=4)

    async def test_angles_differ_by_pi(self):
        """After mirroring, IN and OUT angles always differ by exactly pi."""
        cases = [
            (-1.0, 0.0, 1.0, 0.0, False),
            (-0.5, 0.3, 0.5, -0.3, False),
            (-0.2, -0.1, 0.3, 0.0, True),
            (-1.0, 1.0, 0.5, 0.5, False),
            (-0.15, 0.05, 0.25, -0.03, True),
        ]
        for in_x, in_y, out_x, out_y, in_dom in cases:
            k = self._linked(in_x, in_y, out_x, out_y, in_dominates=in_dom)
            diff = _angle_diff(k.in_tangent_x, k.in_tangent_y, k.out_tangent_x, k.out_tangent_y)
            self.assertAlmostEqual(
                diff,
                math.pi,
                places=3,
                msg=f"in=({in_x},{in_y}) out=({out_x},{out_y}) in_dom={in_dom}",
            )

    async def test_zero_opposite_clamped_to_threshold(self):
        """IN(0,0) mirrored → (0,0), then bounds clamp IN X to -threshold."""
        k = self._linked(0.0, 0.0, 1.0, 0.5)
        self.assertAlmostEqual(k.in_tangent_x, -_THRESHOLD, places=5)
        self.assertAlmostEqual(k.in_tangent_y, 0.0, places=5)

    async def test_zero_dominant_clamps_opposite(self):
        """OUT(0,0) dom → mirrored IN=(0,0), then bounds clamp IN X to -threshold."""
        k = self._linked(-0.5, 0.3, 0.0, 0.0)
        self.assertAlmostEqual(k.in_tangent_x, -_THRESHOLD, places=5)
        self.assertAlmostEqual(k.in_tangent_y, 0.0, places=5)

    async def test_both_zero_clamped_to_threshold(self):
        """Both (0,0) → mirrored to (0,0), then bounds clamp X to ±threshold."""
        k = self._linked(0.0, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(k.in_tangent_x, -_THRESHOLD, places=5)
        self.assertAlmostEqual(k.in_tangent_y, 0.0, places=5)
        self.assertAlmostEqual(k.out_tangent_x, _THRESHOLD, places=5)
        self.assertAlmostEqual(k.out_tangent_y, 0.0, places=5)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Type propagation during mirroring
#
# compute_keyframe_tangents line 174: out_type = in_type  (in dominates)
# compute_keyframe_tangents line 177: in_type = out_type  (out dominates)
# ─────────────────────────────────────────────────────────────────────────────


class TestMirroringTypePropagation(omni.kit.test.AsyncTestCase):
    """Verify that mirroring copies the dominant side's tangent type to the opposite side."""

    async def test_out_dominates_copies_type_to_in(self):
        """When OUT dominates, in_tangent_type should become out_tangent_type."""
        cases = [
            (TangentType.LINEAR, TangentType.CUSTOM),
            (TangentType.SMOOTH, TangentType.CUSTOM),
            (TangentType.FLAT, TangentType.CUSTOM),
            (TangentType.AUTO, TangentType.CUSTOM),
            (TangentType.CUSTOM, TangentType.SMOOTH),
        ]
        for initial_in, initial_out in cases:
            middle = FCurveKey(
                time=_MID_TIME,
                value=_MID_VALUE,
                in_tangent_type=initial_in,
                out_tangent_type=initial_out,
                in_tangent_x=-0.2,
                in_tangent_y=0.0,
                out_tangent_x=0.2,
                out_tangent_y=0.0,
                tangent_broken=False,
            )
            k = _process_middle_key(middle, {(1, False): (0.2, 0.0)})
            self.assertEqual(
                k.in_tangent_type,
                initial_out,
                f"in_type should be {initial_out.name}, got {k.in_tangent_type.name} "
                f"(started as {initial_in.name}→{initial_out.name})",
            )

    async def test_in_dominates_copies_type_to_out(self):
        """When IN dominates, out_tangent_type should become in_tangent_type."""
        cases = [
            (TangentType.CUSTOM, TangentType.LINEAR),
            (TangentType.CUSTOM, TangentType.SMOOTH),
            (TangentType.CUSTOM, TangentType.FLAT),
            (TangentType.SMOOTH, TangentType.CUSTOM),
        ]
        for initial_in, initial_out in cases:
            middle = FCurveKey(
                time=_MID_TIME,
                value=_MID_VALUE,
                in_tangent_type=initial_in,
                out_tangent_type=initial_out,
                in_tangent_x=-0.2,
                in_tangent_y=0.0,
                out_tangent_x=0.2,
                out_tangent_y=0.0,
                tangent_broken=False,
            )
            k = _process_middle_key(middle, {(1, True): (-0.2, 0.0), (1, False): (0.2, 0.0)})
            self.assertEqual(
                k.out_tangent_type,
                initial_in,
                f"out_type should be {initial_in.name}, got {k.out_tangent_type.name} "
                f"(started as {initial_in.name}→{initial_out.name})",
            )

    async def test_same_types_stay_same(self):
        """When both sides already share the same type, it stays unchanged."""
        for tt in [TangentType.CUSTOM, TangentType.LINEAR, TangentType.SMOOTH, TangentType.FLAT]:
            middle = FCurveKey(
                time=_MID_TIME,
                value=_MID_VALUE,
                in_tangent_type=tt,
                out_tangent_type=tt,
                in_tangent_x=-0.2,
                in_tangent_y=0.0,
                out_tangent_x=0.2,
                out_tangent_y=0.0,
                tangent_broken=False,
            )
            k = _process_middle_key(middle, {(1, False): (0.2, 0.0)})
            self.assertEqual(k.in_tangent_type, tt, f"in_type changed for {tt.name}")
            self.assertEqual(k.out_tangent_type, tt, f"out_type changed for {tt.name}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Broken tangent independence
#
# When tangent_broken=True, mirrored=False: each side computes its own tangent
# from its own type, without copying types or angles.
# ─────────────────────────────────────────────────────────────────────────────


class TestBrokenTangentIndependence(omni.kit.test.AsyncTestCase):
    """Verify that broken tangents compute independently — no mirroring, no type copying."""

    async def test_drag_out_does_not_affect_in(self):
        """Dragging OUT with broken tangents should leave IN unchanged."""
        middle = FCurveKey(
            time=_MID_TIME,
            value=_MID_VALUE,
            in_tangent_type=TangentType.CUSTOM,
            out_tangent_type=TangentType.CUSTOM,
            in_tangent_x=-0.2,
            in_tangent_y=0.1,
            out_tangent_x=0.3,
            out_tangent_y=0.0,
            tangent_broken=True,
        )
        k = _process_middle_key(middle, {(1, False): (0.5, 0.3)})
        self.assertAlmostEqual(k.in_tangent_x, -0.2, places=4)
        self.assertAlmostEqual(k.in_tangent_y, 0.1, places=4)
        self.assertAlmostEqual(k.out_tangent_x, 0.5, places=4)
        self.assertAlmostEqual(k.out_tangent_y, 0.3, places=4)

    async def test_types_stay_independent(self):
        """Broken tangents should not copy types between sides."""
        middle = FCurveKey(
            time=_MID_TIME,
            value=_MID_VALUE,
            in_tangent_type=TangentType.LINEAR,
            out_tangent_type=TangentType.FLAT,
            in_tangent_x=-0.2,
            in_tangent_y=0.0,
            out_tangent_x=0.2,
            out_tangent_y=0.0,
            tangent_broken=True,
        )
        k = _process_middle_key(middle, {(1, False): (0.2, 0.0)})
        self.assertEqual(k.in_tangent_type, TangentType.LINEAR)
        self.assertEqual(k.out_tangent_type, TangentType.FLAT)

    async def test_angles_can_diverge(self):
        """Broken CUSTOM tangents at non-opposite angles stay unchanged."""
        middle = FCurveKey(
            time=_MID_TIME,
            value=_MID_VALUE,
            in_tangent_type=TangentType.CUSTOM,
            out_tangent_type=TangentType.CUSTOM,
            in_tangent_x=-0.3,
            in_tangent_y=0.3,
            out_tangent_x=0.3,
            out_tangent_y=0.3,
            tangent_broken=True,
        )
        k = _process_middle_key(middle, {(1, False): (0.3, 0.3)})
        self.assertAlmostEqual(k.in_tangent_x, -0.3, places=4)
        self.assertAlmostEqual(k.in_tangent_y, 0.3, places=4)
        self.assertAlmostEqual(k.out_tangent_x, 0.3, places=4)
        self.assertAlmostEqual(k.out_tangent_y, 0.3, places=4)
        diff = _angle_diff(k.in_tangent_x, k.in_tangent_y, k.out_tangent_x, k.out_tangent_y)
        self.assertAlmostEqual(diff, math.pi / 2, places=3, msg="angles at 135° and 45° differ by 90°")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Boundary key behavior
#
# compute_keyframe_tangents lines 258-270:
#   - No prev_key → in_tangent zeroed
#   - No next_key → out_tangent zeroed
#   - mirrored requires both neighbors → boundary keys never mirror
# ─────────────────────────────────────────────────────────────────────────────


class TestBoundaryKeyBehavior(omni.kit.test.AsyncTestCase):
    """Verify that boundary keys zero their missing-neighbor tangent and don't mirror."""

    async def test_first_key_in_tangent_zeroed(self):
        """First key (no prev) should have in_tangent = (0,0) regardless of stored value."""
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(
                    time=0.0,
                    value=0.5,
                    in_tangent_type=TangentType.CUSTOM,
                    in_tangent_x=-0.5,
                    in_tangent_y=0.3,
                ),
                FCurveKey(time=1.0, value=0.5),
            ],
        )
        process_curve(curve, _BOUNDS, _THRESHOLD)
        self.assertAlmostEqual(curve.keys[0].in_tangent_x, 0.0, places=5)
        self.assertAlmostEqual(curve.keys[0].in_tangent_y, 0.0, places=5)

    async def test_last_key_out_tangent_zeroed(self):
        """Last key (no next) should have out_tangent = (0,0) regardless of stored value."""
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(time=0.0, value=0.5),
                FCurveKey(
                    time=1.0,
                    value=0.5,
                    out_tangent_type=TangentType.CUSTOM,
                    out_tangent_x=0.5,
                    out_tangent_y=0.3,
                ),
            ],
        )
        process_curve(curve, _BOUNDS, _THRESHOLD)
        self.assertAlmostEqual(curve.keys[1].out_tangent_x, 0.0, places=5)
        self.assertAlmostEqual(curve.keys[1].out_tangent_y, 0.0, places=5)

    async def test_two_key_curve_no_mirroring(self):
        """In a 2-key curve, neither key has both neighbors, so neither mirrors."""
        curve = FCurve(
            id="test",
            keys=[
                FCurveKey(
                    time=0.0,
                    value=0.0,
                    tangent_broken=False,
                    in_tangent_type=TangentType.CUSTOM,
                    out_tangent_type=TangentType.CUSTOM,
                    in_tangent_x=-0.5,
                    in_tangent_y=0.3,
                    out_tangent_x=0.3,
                    out_tangent_y=0.2,
                ),
                FCurveKey(
                    time=1.0,
                    value=1.0,
                    tangent_broken=False,
                    in_tangent_type=TangentType.CUSTOM,
                    out_tangent_type=TangentType.CUSTOM,
                    in_tangent_x=-0.3,
                    in_tangent_y=-0.2,
                    out_tangent_x=0.5,
                    out_tangent_y=-0.3,
                ),
            ],
        )
        process_curve(curve, _BOUNDS, _THRESHOLD)

        # Key 0: in zeroed (no prev), out passes through (has next)
        self.assertAlmostEqual(curve.keys[0].in_tangent_x, 0.0, places=5)
        self.assertAlmostEqual(curve.keys[0].in_tangent_y, 0.0, places=5)
        self.assertAlmostEqual(curve.keys[0].out_tangent_x, 0.3, places=4)
        self.assertAlmostEqual(curve.keys[0].out_tangent_y, 0.2, places=4)

        # Key 1: in passes through (has prev), out zeroed (no next)
        self.assertAlmostEqual(curve.keys[1].in_tangent_x, -0.3, places=4)
        self.assertAlmostEqual(curve.keys[1].in_tangent_y, -0.2, places=4)
        self.assertAlmostEqual(curve.keys[1].out_tangent_x, 0.0, places=5)
        self.assertAlmostEqual(curve.keys[1].out_tangent_y, 0.0, places=5)
