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

Unit tests for FCurveWidget public API additions.

Tests for:
- subscribe_curve_changed() - unified curve change event
- SelectionInfo dataclass - helper properties
- selection property - returns SelectionInfo
- get_selection_tangent_type() - returns common tangent types
- set_selected_keys_tangent_type() - sets tangent type on selected keys
"""

from copy import deepcopy
from dataclasses import replace
from math import nextafter
from random import Random
from unittest import mock

import omni.kit.test
from omni import ui

from omni.flux.fcurve.widget import (
    CurveBounds,
    FCurve,
    FCurveKey,
    FCurveWidget,
    InfinityType,
    KeyReference,
    SelectionInfo,
    TangentType,
)
from omni.flux.fcurve.widget import fcurve_widget

__all__ = [
    "TestFCurveWidget",
    "TestGetSelectionTangentType",
    "TestSelectionInfo",
    "TestSelectionProperty",
    "TestSetSelectedKeysTangentType",
    "TestSubscribeCurveChanged",
]


class TestFCurveWidget(omni.kit.test.AsyncTestCase):
    """Test FCurveWidget logic without constructing render widgets."""

    async def setUp(self):
        """Isolate UI construction while exercising real curve processing."""
        stack_patch = mock.patch.object(fcurve_widget.ui, "ZStack")
        stack_patch.start()
        self.addCleanup(stack_patch.stop)
        manager_patch = mock.patch.object(fcurve_widget, "CurveWidgetsManager", side_effect=lambda *a, **k: mock.Mock())
        self._manager_factory = manager_patch.start()
        self.addCleanup(manager_patch.stop)
        self._commit = mock.Mock()
        self._widget = FCurveWidget(curve_bounds=CurveBounds(value_max=8.0), on_commit=self._commit)
        self.addCleanup(self._widget.destroy)

    async def test_set_selected_keys_tangent_type_with_neither_side_preserves_selected_keys_without_notifications(self):
        """Requesting neither tangent side leaves linked and broken keys untouched."""
        # Arrange
        self._widget.set_curves(
            {
                curve_id: FCurve(
                    id=curve_id,
                    keys=[
                        FCurveKey(time=time, value=value, tangent_broken=broken)
                        for time, value in ((0.0, 0.2), (0.5, 0.8), (1.0, 0.4))
                    ],
                )
                for curve_id, broken in (("linked", False), ("broken", True))
            }
        )
        self._widget.select_keys([KeyReference("linked", 1), KeyReference("broken", 1)])
        curves_before = deepcopy(self._widget.curves)
        selected_before = self._widget.selected_keys
        changed_curves = []
        self._tangent_edit_subscription = self._widget.subscribe_curve_changed(changed_curves.append)
        try:
            # Act
            modified = self._widget.set_selected_keys_tangent_type(
                TangentType.FLAT, in_tangent=False, out_tangent=False
            )

            # Assert
            self.assertEqual(modified, 0)
            self.assertEqual(self._widget.curves, curves_before)
            self.assertEqual(self._widget.selected_keys, selected_before)
            self.assertEqual(changed_curves, [])
            self._commit.assert_not_called()
        finally:
            self._tangent_edit_subscription = None

    async def test_editable_selected_keys_filters_invalid_references_without_changing_selection(self):
        """Return eligible references once in selection order without observable edits."""
        # Arrange
        hidden = self._curve("hidden")
        hidden.visible = False
        locked = self._curve("locked")
        locked.locked = True
        self._set_curves(self._curve(), self._curve("second"), hidden, locked)
        references = [
            KeyReference("second", 1),
            KeyReference("hidden", 0),
            KeyReference("first", 2),
            KeyReference("second", 1),
            KeyReference("locked", 0),
            KeyReference("missing", 0),
            KeyReference("first", -1),
            KeyReference("first", 3),
        ]
        self._widget.select_keys(references)
        selection_changed = mock.Mock()
        _subscription = self._widget.subscribe_selection_changed(selection_changed)

        # Act
        result = self._widget.editable_selected_keys

        # Assert
        self.assertEqual(result, (KeyReference("second", 1), KeyReference("first", 2)))
        self.assertEqual(self._widget.selected_keys, references)
        self._commit.assert_not_called()
        selection_changed.assert_not_called()

    async def test_prepare_key_offset_selected_keys_stop_at_stationary_neighbors(self):
        """Stationary neighbors limit shared movement of adjacent and disjoint selections."""
        for indices, requested, expected, values in (
            ((0, 1), 0.3, (0.399, 0.599), [1.0, 7.0]),
            ((0, 2), 0.4, (0.399, 0.799), [1.0, 3.0]),
            ((0, 2), -0.4, (0.001, 0.401), [1.0, 3.0]),
        ):
            with self.subTest(indices=indices, time_offset=requested):
                # Arrange
                baseline = self._set_curves(self._curve())
                selected = tuple(KeyReference("first", index) for index in indices)

                # Act
                positions = self._widget.prepare_key_offset(baseline, selected, time_offset=requested)

                # Assert
                self.assertAlmostEqual(positions[selected[0]][0], expected[0])
                self.assertAlmostEqual(positions[selected[1]][0], expected[1])
                self.assertEqual([position[1] for position in positions.values()], values)
                self.assertEqual(self._widget.curves["first"].keys, baseline["first"])
                self._commit.assert_not_called()

    async def test_prepare_key_offset_rounded_boundary_stays_inside_neighbor_limit(self):
        """Prepared coordinates must remain valid despite floating-point offset cancellation."""
        # Arrange
        baseline = self._set_curves(
            FCurve(id="first", keys=[FCurveKey(time=0.04, value=1.0), FCurveKey(time=0.11, value=2.0)])
        )
        selected = KeyReference("first", 0)

        # Act
        positions = self._widget.prepare_key_offset(baseline, (selected,), time_offset=1.0)

        # Assert
        self.assertLessEqual(positions[selected][0], 0.11 - self._widget.keyframe_clamp_threshold)
        self.assertAlmostEqual(positions[selected][0], 0.109)
        self.assertEqual(self._widget.curves["first"].keys, baseline["first"])
        self._commit.assert_not_called()

    async def test_set_key_positions_prepared_rounded_boundary_preserves_stationary_neighbors(self):
        """Boundary preparation must produce an applicable batch across adjacent keys and curves."""
        for times, selected_indices in (((0.04, 0.11), (0,)), ((0.01, 0.04, 0.11), (0, 1))):
            with self.subTest(title=f"selected_indices={selected_indices}"):
                # Arrange
                baseline = self._set_curves(
                    FCurve(id="first", keys=[FCurveKey(time=time, value=1.0) for time in times]),
                    FCurve(id="second", keys=[FCurveKey(time=0.2, value=2.0), FCurveKey(time=0.6, value=3.0)]),
                )
                selected = tuple(KeyReference("first", index) for index in selected_indices) + (
                    KeyReference("second", 0),
                )
                positions = self._widget.prepare_key_offset(baseline, selected, time_offset=1.0)

                # Act
                self._widget.set_key_positions(positions, baseline=baseline)

                # Assert
                curves = self._widget.curves
                self.assertEqual(curves["first"].keys[-1].time, 0.11)
                self.assertEqual(curves["second"].keys[-1].time, 0.6)
                for reference in selected:
                    key = curves[reference.curve_id].keys[reference.key_index]
                    self.assertEqual((key.time, key.value), positions[reference])
                    self.assertAlmostEqual(key.time - baseline[reference.curve_id][reference.key_index].time, 0.069)
                self.assertLessEqual(curves["first"].keys[-2].time, 0.11 - self._widget.keyframe_clamp_threshold)

    async def test_set_key_positions_prepared_rounded_boundary_respects_property_limits(self):
        """Prepared offsets must stay inside both upper and lower hard bounds."""
        for title, time, value, bounds, offsets in (
            ("upper value", 0.2, 0.04, CurveBounds(value_max=0.11), {"value_offset": 1.0}),
            ("lower value", 0.2, 0.11, CurveBounds(value_min=0.04), {"value_offset": -1.0}),
            ("lower time", 0.11, 0.5, CurveBounds(time_min=0.04), {"time_offset": -1.0}),
        ):
            with self.subTest(title=title):
                # Arrange
                key = FCurveKey(time=time, value=value)
                baseline = self._set_curves(FCurve(id="first", keys=[key]))
                self._widget.set_curve_bounds("first", bounds)
                selected = KeyReference("first", 0)
                positions = self._widget.prepare_key_offset(baseline, (selected,), **offsets)

                # Act
                self._widget.set_key_positions(positions, baseline=baseline)

                # Assert
                self.assertEqual((key.time, key.value), positions[selected])
                self.assertGreaterEqual(positions[selected][0], bounds.time_min)
                self.assertLessEqual(positions[selected][0], bounds.time_max)
                self.assertGreaterEqual(positions[selected][1], bounds.value_min)
                self.assertLessEqual(positions[selected][1], bounds.value_max)
                if "time_offset" in offsets:
                    self.assertAlmostEqual(key.time, bounds.time_min)
                else:
                    expected = bounds.value_max if offsets["value_offset"] > 0 else bounds.value_min
                    self.assertAlmostEqual(key.value, expected)

    async def test_prepare_key_offset_multiple_curves_share_tightest_time_limit(self):
        """The tightest per-curve hard bound constrains every selected key equally."""
        # Arrange
        baseline = self._set_curves(self._curve(), self._curve("second"))
        self._widget.set_curve_bounds("second", CurveBounds(time_min=0.1, time_max=0.65, value_max=8.0))
        selected = (KeyReference("first", 2), KeyReference("second", 2))

        # Act
        positions = self._widget.prepare_key_offset(baseline, selected, time_offset=0.3)

        # Assert
        self.assertAlmostEqual(positions[selected[0]][0], 0.65)
        self.assertAlmostEqual(positions[selected[1]][0], 0.65)

    async def test_prepare_key_offset_value_limit_preserves_common_offset(self):
        """Shared value clamping preserves the difference between selected values."""
        # Arrange
        baseline = self._set_curves(self._curve())
        selected = (KeyReference("first", 0), KeyReference("first", 1))

        # Act
        positions = self._widget.prepare_key_offset(baseline, selected, value_offset=5.0)

        # Assert
        self.assertEqual(positions, {selected[0]: (0.2, 2.0), selected[1]: (0.4, 8.0)})

    async def test_prepare_key_offset_multiple_curves_share_tightest_lower_value_limit(self):
        """A per-curve lower value limit stops the entire selection together."""
        # Arrange
        baseline = self._set_curves(self._curve(), self._curve("second"))
        self._widget.set_curve_bounds("second", CurveBounds(value_min=0.5, value_max=8.0))
        selected = (KeyReference("first", 1), KeyReference("second", 0))

        # Act
        positions = self._widget.prepare_key_offset(baseline, selected, value_offset=-4.0)

        # Assert
        self.assertEqual(positions, {selected[0]: (0.4, 6.5), selected[1]: (0.2, 0.5)})

    async def test_prepare_key_offset_hidden_locked_and_duplicate_references_do_not_constrain_selection(self):
        """Only unique editable visible keys contribute positions or limits."""
        # Arrange
        baseline = self._set_curves(
            self._curve(), replace(self._curve("hidden"), visible=False), replace(self._curve("locked"), locked=True)
        )
        self._widget.set_curve_bounds("hidden", CurveBounds(value_min=1.0, value_max=7.0))
        self._widget.set_curve_bounds("locked", CurveBounds(value_min=1.0, value_max=7.0))
        selected = (
            KeyReference("first", 0),
            KeyReference("hidden", 1),
            KeyReference("locked", 1),
            KeyReference("first", 0),
        )

        # Act
        positions = self._widget.prepare_key_offset(baseline, selected, value_offset=2.0)

        # Assert
        self.assertEqual(positions, {KeyReference("first", 0): (0.2, 3.0)})
        self._commit.assert_not_called()

    async def test_prepare_key_offset_empty_selection_returns_no_positions(self):
        """An empty selection never starts an edit."""
        # Arrange
        baseline = self._set_curves(self._curve())

        # Act
        positions = self._widget.prepare_key_offset(baseline, (), time_offset=0.1)

        # Assert
        self.assertEqual(positions, {})
        self._commit.assert_not_called()

    async def test_set_key_positions_roundoff_fixtures_preserve_requested_shared_translation(self):
        """Apply one requested offset across negative, many-ULP, and multi-curve cases."""
        for title, pairs, offset in (
            ("negative", ((0.02, 0.021),), -0.008),
            ("stationary neighbor", ((0.35, 0.351, 0.99),), 0.18),
            ("formerly 32 ULPs", ((3.8912670487369034, 3.8922670487369033),), 0.10779718742058719),
            (
                "four boundary pairs",
                (
                    (0.4959945624267403, 0.4969945624267403),
                    (0.9539481321814672, 0.9549481321814672),
                    (0.22823639681083177, 0.22923639681083177),
                    (0.00850938803961099, 0.00950938803961099),
                ),
                0.0032212358465387543,
            ),
        ):
            with self.subTest(title=title):
                # Arrange
                self._widget.curve_bounds = CurveBounds(time_min=-10.0, time_max=10.0, value_max=8.0)
                curves = [
                    FCurve(id=str(index), keys=[FCurveKey(time=time, value=1.0) for time in times])
                    for index, times in enumerate(pairs)
                ]
                baseline = self._set_curves(*curves)
                selected = tuple(KeyReference(curve.id, index) for curve in curves for index in range(2))
                positions = self._widget.prepare_key_offset(baseline, selected, time_offset=offset)
                self._commit.reset_mock()

                # Act
                self._widget.set_key_positions(positions, baseline=baseline)

                # Assert
                for reference in selected:
                    key = baseline[reference.curve_id][reference.key_index]
                    self.assertEqual(positions[reference], (key.time + offset, key.value))
                    live = self._widget.curves[reference.curve_id].keys[reference.key_index]
                    self.assertEqual((live.time, live.value), positions[reference])
                for curve in curves:
                    self.assertEqual(
                        [(key.time, key.value) for key in curve.keys[2:]],
                        [(key.time, key.value) for key in baseline[curve.id][2:]],
                    )
                self.assertCountEqual([call.args[0] for call in self._commit.call_args_list], list(baseline))

    async def test_set_key_positions_large_coordinates_retain_fallback_translation(self):
        """The existing common-offset fallback keeps larger roundoff errors applicable."""
        # Arrange
        self._widget.curve_bounds = CurveBounds(time_min=-1_000_000.0, time_max=1_000_000.0, value_max=8.0)
        curve = FCurve(
            id="first", keys=[FCurveKey(time=time, value=1.0) for time in (86331.1885979297, 86331.1895979297)]
        )
        baseline = self._set_curves(curve)
        selected = (KeyReference("first", 0), KeyReference("first", 1))
        positions = self._widget.prepare_key_offset(baseline, selected, time_offset=-8235.654889179168)

        # Act
        self._widget.set_key_positions(positions, baseline=baseline)

        # Assert
        self.assertEqual(tuple(key.time for key in curve.keys), (78095.53370875053, 78095.53470875054))
        offset = curve.keys[0].time - baseline["first"][0].time
        for reference in selected:
            self.assertEqual(positions[reference][0], baseline["first"][reference.key_index].time + offset)
            self.assertEqual(curve.keys[reference.key_index].time, positions[reference][0])

    async def test_set_key_positions_roundoff_tolerance_accepts_only_inside_boundary(self):
        """A sub-tolerance gap shortfall applies without moving either requested key."""
        # Arrange
        curve = FCurve(id="first", keys=[FCurveKey(time=time, value=1.0) for time in (0.001, 0.002)])
        baseline = self._set_curves(curve)
        positions = {KeyReference("first", 0): (0.009, 1.0), KeyReference("first", 1): (0.01 - 0.5e-12, 1.0)}

        # Act
        self._widget.set_key_positions(positions, baseline=baseline)

        # Assert
        self.assertEqual(tuple(key.time for key in curve.keys), (0.009, 0.01 - 0.5e-12))
        self._commit.assert_called_once_with("first", curve)

    async def test_set_key_positions_gap_outside_tolerance_rejects_without_mutation(self):
        """A larger gap shortfall cannot enter the live curve."""
        # Arrange
        curve = FCurve(id="first", keys=[FCurveKey(time=time, value=1.0) for time in (0.001, 0.002)])
        baseline = self._set_curves(curve)
        positions = {KeyReference("first", 0): (0.009, 1.0), KeyReference("first", 1): (0.01 - 2e-12, 1.0)}

        # Act
        with self.assertRaises(ValueError):
            self._widget.set_key_positions(positions, baseline=baseline)

        # Assert
        self.assertEqual(curve.keys, baseline["first"])
        self._commit.assert_not_called()

    async def test_validate_curve_keys_tiny_positive_gap_rejects_duplicate_and_reversed_times(self):
        """Absolute roundoff tolerance cannot admit equal or crossed key times."""
        for title, times in (("duplicate", (0.5, 0.5)), ("reversed", (0.5, 0.5 - 0.25e-12))):
            with self.subTest(title=title):
                # Arrange
                self._widget._threshold = 0.5e-12
                curve = FCurve(id="first", keys=[FCurveKey(time=time, value=1.0) for time in times])
                baseline = self._set_curves(curve)

                # Act
                with self.assertRaises(ValueError):
                    self._widget._validate_curve_keys("first", baseline["first"])

                # Assert
                self.assertEqual(curve.keys, baseline["first"])
                self._commit.assert_not_called()

    async def test_process_curve_seeded_translations_preserve_key_coordinates(self):
        """A second processing pass keeps prepared coordinates stable across tangent modes."""
        random = Random(6066)
        for magnitude in (10.0, 100.0, 1000.0):
            for tangent_type in TangentType:
                with self.subTest(title=f"magnitude={magnitude}, tangents={tangent_type.name}"):
                    # Arrange
                    left = random.uniform(magnitude / 2, magnitude)
                    right = left + 0.001
                    if left > right - 0.001:
                        right = nextafter(right, float("inf"))
                    self._widget.curve_bounds = CurveBounds(time_min=-2000.0, time_max=2000.0, value_max=8.0)
                    curve = FCurve(
                        id="first",
                        keys=[
                            FCurveKey(
                                time=time, value=value, in_tangent_type=tangent_type, out_tangent_type=tangent_type
                            )
                            for time, value in ((left, 1.0), (right, 2.0))
                        ],
                    )
                    baseline = self._set_curves(curve)
                    selected = (KeyReference("first", 0), KeyReference("first", 1))
                    offset = random.uniform(-magnitude / 2, magnitude / 2)
                    positions = self._widget.prepare_key_offset(baseline, selected, time_offset=offset)
                    self._widget.set_key_positions(positions, baseline=baseline)
                    expected = [(key.time, key.value) for key in curve.keys]
                    keys = tuple(curve.keys)

                    # Act
                    fcurve_widget.process_curve(curve, self._widget.bounds_for("first"), 0.001)

                    # Assert
                    self.assertEqual([(key.time, key.value) for key in curve.keys], expected)
                    self.assertEqual(tuple(key.time for key in curve.keys), (left + offset, right + offset))
                    for index, key in enumerate(keys):
                        self.assertIs(curve.keys[index], key)

    async def test_prepare_key_offset_roundoff_gap_preserves_requested_translation(self):
        """Accept a shared translation whose gap differs only by roundoff."""
        # Arrange
        curve = FCurve(id="first", keys=[FCurveKey(time=time, value=1.0) for time in (0.001, 0.002)])
        baseline = self._set_curves(curve)
        selected = (KeyReference("first", 0), KeyReference("first", 1))

        # Act
        positions = self._widget.prepare_key_offset(baseline, selected, time_offset=0.008)

        # Assert
        self.assertEqual(positions[selected[0]], (0.001 + 0.008, 1.0))
        self.assertEqual(positions[selected[1]], (0.002 + 0.008, 1.0))
        self.assertEqual(curve.keys, baseline["first"])
        self._commit.assert_not_called()

    async def test_set_key_positions_roundoff_gap_preserves_requested_positions_and_identities(self):
        """Apply tolerance-valid coordinates without replacing live keys or managers."""
        # Arrange
        curve = FCurve(id="first", keys=[FCurveKey(time=time, value=1.0) for time in (0.001, 0.002)])
        baseline = self._set_curves(curve)
        key_list = curve.keys
        keys = tuple(curve.keys)
        manager = self._widget._managers["first"]
        factory_calls = self._manager_factory.call_count
        selection = [KeyReference("first", 1), KeyReference("first", 0)]
        self._widget.select_keys(selection)
        positions = {KeyReference("first", index): (key.time + 0.008, key.value) for index, key in enumerate(keys)}

        # Act
        self._widget.set_key_positions(positions, baseline=baseline)

        # Assert
        self.assertIs(curve.keys, key_list)
        self.assertIs(self._widget.curves["first"], curve)
        self.assertEqual(self._widget.selected_keys, selection)
        self.assertIs(self._widget._managers["first"], manager)
        self.assertEqual(self._manager_factory.call_count, factory_calls)
        for index, key in enumerate(keys):
            self.assertIs(curve.keys[index], key)
            self.assertEqual((key.time, key.value), positions[KeyReference("first", index)])
        self._commit.assert_called_once_with("first", curve)
        manager.request_position_sync.assert_called_once_with()
        manager.sync.assert_not_called()

    async def test_prepare_key_offset_zero_width_interval_blocks_only_time_axis(self):
        """A fully constrained time interval remains valid for value editing."""
        # Arrange
        curve = FCurve(id="first", keys=[FCurveKey(time=0.25, value=1.0)])
        baseline = self._set_curves(curve)
        self._widget.set_curve_bounds("first", CurveBounds(time_min=0.25, time_max=0.25, value_max=8.0))
        selected = (KeyReference("first", 0),)

        # Act
        positions = self._widget.prepare_key_offset(baseline, selected, time_offset=0.5, value_offset=2.0)

        # Assert
        self.assertEqual(positions, {selected[0]: (0.25, 3.0)})

    async def test_prepare_key_offset_tolerance_valid_neighbors_preserves_time_during_value_edit(self):
        """A value edit preserves accepted times next to one or two tight neighbors."""
        for title, times in (
            ("both tight", (0.009, 0.01 - 0.5e-12, 0.011 - 1e-12)),
            ("previous tight", (0.009, 0.01 - 0.5e-12, 0.2)),
            ("next tight", (0.001, 0.01 - 0.5e-12, 0.011 - 1e-12)),
        ):
            with self.subTest(title=title):
                # Arrange
                curve = FCurve(id="first", keys=[FCurveKey(time=time, value=1.0) for time in times])
                baseline = self._set_curves(curve)
                selected = KeyReference("first", 1)

                # Act
                positions = self._widget.prepare_key_offset(baseline, (selected,), value_offset=1.0)

                # Assert
                self.assertEqual(positions, {selected: (times[1], 2.0)})
                self.assertEqual(curve.keys, baseline["first"])
                self._commit.assert_not_called()

    async def test_set_key_positions_tolerance_valid_neighbors_applies_value_without_moving_keys(self):
        """Prepared value edits retain exact times, stationary neighbors, and live key identities."""
        for title, times in (
            ("both tight", (0.009, 0.01 - 0.5e-12, 0.011 - 1e-12)),
            ("previous tight", (0.009, 0.01 - 0.5e-12, 0.2)),
            ("next tight", (0.001, 0.01 - 0.5e-12, 0.011 - 1e-12)),
        ):
            with self.subTest(title=title):
                # Arrange
                curve = FCurve(id="first", keys=[FCurveKey(time=time, value=1.0) for time in times])
                baseline = self._set_curves(curve)
                key_list = curve.keys
                keys = tuple(curve.keys)
                positions = self._widget.prepare_key_offset(baseline, (KeyReference("first", 1),), value_offset=1.0)
                self._commit.reset_mock()

                # Act
                self._widget.set_key_positions(positions, baseline=baseline)

                # Assert
                self.assertEqual(tuple(key.time for key in curve.keys), times)
                self.assertEqual(tuple(key.value for key in curve.keys), (1.0, 2.0, 1.0))
                self.assertIs(curve.keys, key_list)
                for index, key in enumerate(keys):
                    self.assertIs(curve.keys[index], key)
                self._commit.assert_called_once_with("first", curve)

    async def test_prepare_key_offset_tolerance_valid_neighbors_blocks_only_constrained_direction(self):
        """Time edits stop at accepted tight neighbors while retaining movement into open space."""
        for title, times, requested, expected in (
            ("both tight, backward", (0.009, 0.01 - 0.5e-12, 0.011 - 1e-12), -0.002, 0.0),
            ("both tight, forward", (0.009, 0.01 - 0.5e-12, 0.011 - 1e-12), 0.002, 0.0),
            ("previous tight, backward", (0.009, 0.01 - 0.5e-12, 0.2), -0.002, 0.0),
            ("previous tight, forward", (0.009, 0.01 - 0.5e-12, 0.2), 0.002, 0.002),
            ("next tight, backward", (0.001, 0.01 - 0.5e-12, 0.011 - 1e-12), -0.002, -0.002),
            ("next tight, forward", (0.001, 0.01 - 0.5e-12, 0.011 - 1e-12), 0.002, 0.0),
        ):
            with self.subTest(title=title):
                # Arrange
                curve = FCurve(id="first", keys=[FCurveKey(time=time, value=1.0) for time in times])
                baseline = self._set_curves(curve)
                selected = KeyReference("first", 1)

                # Act
                positions = self._widget.prepare_key_offset(baseline, (selected,), time_offset=requested)

                # Assert
                self.assertEqual(positions, {selected: (times[1] + expected, 1.0)})
                self.assertEqual(curve.keys, baseline["first"])
                self._commit.assert_not_called()

    async def test_prepare_key_offset_tolerance_squeezed_curve_blocks_shared_time_but_allows_value(self):
        """A squeezed key constrains time across curves without blocking their shared value edit."""
        for requested in (-0.002, 0.002):
            with self.subTest(title=f"time_offset={requested}"):
                # Arrange
                times = (0.009, 0.01 - 0.5e-12, 0.011 - 1e-12)
                first = FCurve(id="first", keys=[FCurveKey(time=time, value=1.0) for time in times])
                second = self._curve("second")
                baseline = self._set_curves(first, second)
                selected = (KeyReference("first", 1), KeyReference("second", 1))

                # Act
                positions = self._widget.prepare_key_offset(baseline, selected, time_offset=requested, value_offset=1.0)

                # Assert
                self.assertEqual(positions, {selected[0]: (times[1], 2.0), selected[1]: (0.4, 8.0)})
                self.assertEqual({curve_id: curve.keys for curve_id, curve in self._widget.curves.items()}, baseline)
                self._commit.assert_not_called()

    async def test_set_key_positions_tolerance_valid_neighbors_zero_offset_does_not_commit(self):
        """Applying an unchanged prepared position leaves tight curves untouched without a commit."""
        for title, times in (
            ("both tight", (0.009, 0.01 - 0.5e-12, 0.011 - 1e-12)),
            ("previous tight", (0.009, 0.01 - 0.5e-12, 0.2)),
            ("next tight", (0.001, 0.01 - 0.5e-12, 0.011 - 1e-12)),
        ):
            with self.subTest(title=title):
                # Arrange
                curve = FCurve(id="first", keys=[FCurveKey(time=time, value=1.0) for time in times])
                baseline = self._set_curves(curve)
                positions = self._widget.prepare_key_offset(baseline, (KeyReference("first", 1),))

                # Act
                self._widget.set_key_positions(positions, baseline=baseline)

                # Assert
                self.assertEqual(curve.keys, baseline["first"])
                self._commit.assert_not_called()

    async def test_prepare_key_offset_nonfinite_input_raises_without_mutation(self):
        """Non-finite time or value offsets cannot enter a gesture."""
        for offsets in ({"time_offset": float("nan")}, {"time_offset": float("inf")}, {"value_offset": -float("inf")}):
            with self.subTest(title=str(offsets)):
                # Arrange
                baseline = self._set_curves(self._curve())

                # Act
                with self.assertRaises(ValueError):
                    self._widget.prepare_key_offset(baseline, (KeyReference("first", 0),), **offsets)

                # Assert
                self.assertEqual(self._widget.curves["first"].keys, baseline["first"])
                self._commit.assert_not_called()

    async def test_prepare_key_offset_stale_reference_raises_without_mutation(self):
        """A missing curve or out-of-range index invalidates the whole prepared edit."""
        for invalid in (
            KeyReference("missing", 0),
            KeyReference("first", -1),
            KeyReference("first", 3),
            KeyReference("first", 0.5),
        ):
            with self.subTest(title=str(invalid)):
                # Arrange
                baseline = self._set_curves(self._curve())
                selected = (KeyReference("first", 0), invalid)

                # Act
                with self.assertRaises(ValueError):
                    self._widget.prepare_key_offset(baseline, selected, value_offset=1.0)

                # Assert
                self.assertEqual(self._widget.curves["first"].keys, baseline["first"])
                self._commit.assert_not_called()

    async def test_prepare_key_offset_malformed_baseline_raises_without_repairing_live_data(self):
        """Malformed snapshots are rejected without repairing unrelated keys."""
        for corruption in (
            "missing",
            "short",
            "nonfinite",
            "unordered",
            "invalid_tangent",
            "invalid_in_tangent_type",
            "invalid_out_tangent_type",
        ):
            with self.subTest(title=corruption):
                # Arrange
                original = self._set_curves(self._curve())
                baseline = {"first": [replace(key) for key in original["first"]]}
                if corruption == "missing":
                    baseline.clear()
                elif corruption == "short":
                    baseline["first"].pop()
                elif corruption == "nonfinite":
                    baseline["first"][2].value = float("nan")
                elif corruption == "unordered":
                    baseline["first"][2].time = 0.1
                elif corruption == "invalid_tangent":
                    baseline["first"][2].out_tangent_x = float("nan")
                elif corruption == "invalid_in_tangent_type":
                    baseline["first"][2].in_tangent_type = 99
                else:
                    baseline["first"][2].out_tangent_type = 99

                # Act
                with self.assertRaises(ValueError):
                    self._widget.prepare_key_offset(baseline, (KeyReference("first", 0),), value_offset=1.0)

                # Assert
                self.assertEqual(self._widget.curves["first"].keys, original["first"])
                self._commit.assert_not_called()

    async def test_set_key_positions_effective_noop_does_not_process_render_or_commit(self):
        """Unchanged coordinates preserve storage and renderer state."""
        # Arrange
        baseline = self._set_curves(self._curve())
        manager = self._widget._managers["first"]
        positions = {KeyReference("first", 0): (0.2, 1.0)}
        with mock.patch.object(fcurve_widget, "process_curve", wraps=fcurve_widget.process_curve) as process:
            # Act
            self._widget.set_key_positions(positions, baseline=baseline)

        # Assert
        process.assert_not_called()
        manager.request_position_sync.assert_not_called()
        manager.sync.assert_not_called()
        self._commit.assert_not_called()

    async def test_set_key_positions_multiple_curves_notify_after_all_are_updated(self):
        """Each curve is processed once and persistence observers see the complete batch."""
        # Arrange
        baseline = self._set_curves(self._curve(), self._curve("second"))
        positions = {
            KeyReference("first", 0): (0.2, 2.0),
            KeyReference("first", 1): (0.4, 8.0),
            KeyReference("second", 0): (0.2, 2.0),
        }
        self._widget.select_keys(list(positions))
        notifications = []

        def on_curve_changed(curve_id):
            """Observe completed persistence before a subscriber changes selection."""
            notifications.append((curve_id, self._commit.call_count))
            if len(notifications) == 1:
                self._widget.select_keys([])

        _subscription = self._widget.subscribe_curve_changed(on_curve_changed)
        observed_values = []
        self._commit.side_effect = lambda *_: observed_values.append(
            (self._widget.curves["first"].keys[0].value, self._widget.curves["second"].keys[0].value)
        )
        with mock.patch.object(fcurve_widget, "process_curve", wraps=fcurve_widget.process_curve) as process:
            # Act
            self._widget.set_key_positions(positions, baseline=baseline)

        # Assert
        self.assertEqual(process.call_count, 2)
        self.assertCountEqual([call.args[0].id for call in process.call_args_list], ["first", "second"])
        self.assertEqual(observed_values, [(2.0, 2.0), (2.0, 2.0)])
        self.assertCountEqual([call.args[0] for call in self._commit.call_args_list], ["first", "second"])
        self.assertEqual(notifications, [("first", 2), ("second", 2)])
        self.assertEqual(self._widget.selected_keys, [])

    async def test_set_key_positions_invalid_candidate_rejects_whole_batch(self):
        """Invalid coordinates or references cannot partially write another valid curve."""
        for reference, position in (
            (KeyReference("second", 0), (float("nan"), 2.0)),
            (KeyReference("second", 0), (0.2, float("inf"))),
            (KeyReference("second", 0), (0.4, 2.0)),
            (KeyReference("second", 0), (0.2, 9.0)),
            (KeyReference("second", -1), (0.2, 2.0)),
            (KeyReference("second", 3), (0.2, 2.0)),
            (KeyReference("second", 0.5), (0.2, 2.0)),
            (KeyReference("missing", 0), (0.2, 2.0)),
        ):
            with self.subTest(title=f"{reference}: {position}"):
                # Arrange
                baseline = self._set_curves(self._curve(), self._curve("second"))
                positions = {KeyReference("first", 0): (0.2, 2.0), reference: position}

                # Act
                with self.assertRaises(ValueError):
                    self._widget.set_key_positions(positions, baseline=baseline)

                # Assert
                self.assertEqual({curve_id: curve.keys for curve_id, curve in self._widget.curves.items()}, baseline)
                self._commit.assert_not_called()

    async def test_set_key_positions_ineligible_curve_rejects_whole_batch(self):
        """A curve hidden or locked after preparation cannot be written."""
        for changed_flag in ({"visible": False}, {"locked": True}):
            with self.subTest(title=str(changed_flag)):
                # Arrange
                baseline = self._set_curves(self._curve(), replace(self._curve("second"), **changed_flag))
                positions = {KeyReference("first", 0): (0.2, 2.0), KeyReference("second", 0): (0.2, 2.0)}

                # Act
                with self.assertRaises(ValueError):
                    self._widget.set_key_positions(positions, baseline=baseline)

                # Assert
                self.assertEqual({curve_id: curve.keys for curve_id, curve in self._widget.curves.items()}, baseline)
                self._commit.assert_not_called()

    async def test_set_key_positions_malformed_baseline_rejects_whole_batch(self):
        """Missing or invalid snapshot data cannot partially apply another curve."""
        for corruption in ("missing", "short", "out_of_bounds", "overlapping_keys"):
            with self.subTest(title=corruption):
                # Arrange
                original = self._set_curves(self._curve(), self._curve("second"))
                baseline = {curve_id: [replace(key) for key in keys] for curve_id, keys in original.items()}
                if corruption == "missing":
                    del baseline["second"]
                elif corruption == "short":
                    baseline["second"].pop()
                elif corruption == "out_of_bounds":
                    baseline["second"][2].value = 9.0
                else:
                    baseline["second"][2].time = 0.4005
                positions = {KeyReference("first", 0): (0.2, 2.0), KeyReference("second", 0): (0.2, 2.0)}

                # Act
                with self.assertRaises(ValueError):
                    self._widget.set_key_positions(positions, baseline=baseline)

                # Assert
                self.assertEqual({curve_id: curve.keys for curve_id, curve in self._widget.curves.items()}, original)
                self._commit.assert_not_called()

    async def test_set_key_positions_processing_failure_does_not_partially_mutate(self):
        """A failure preparing the second curve leaves every live key untouched."""
        # Arrange
        baseline = self._set_curves(self._curve(), self._curve("second"))
        positions = {KeyReference("first", 0): (0.2, 2.0), KeyReference("second", 0): (0.2, 2.0)}
        with mock.patch.object(fcurve_widget, "process_curve", side_effect=[None, ValueError("invalid curve")]):
            # Act
            with self.assertRaisesRegex(ValueError, "invalid curve"):
                self._widget.set_key_positions(positions, baseline=baseline)

        # Assert
        self.assertEqual({curve_id: curve.keys for curve_id, curve in self._widget.curves.items()}, baseline)
        self._commit.assert_not_called()

    async def test_set_key_positions_invalid_processed_tangent_does_not_partially_mutate(self):
        """Non-finite generated tangents cannot reach live curves or storage."""
        # Arrange
        baseline = self._set_curves(self._curve(), self._curve("second"))
        positions = {KeyReference("first", 0): (0.2, 2.0), KeyReference("second", 0): (0.2, 2.0)}

        def corrupt_second_curve(curve, _bounds, _threshold):
            """Simulate invalid tangent output from curve processing."""
            if curve.id == "second":
                curve.keys[1].out_tangent_y = float("nan")

        with mock.patch.object(fcurve_widget, "process_curve", side_effect=corrupt_second_curve):
            # Act
            with self.assertRaises(ValueError):
                self._widget.set_key_positions(positions, baseline=baseline)

        # Assert
        self.assertEqual({curve_id: curve.keys for curve_id, curve in self._widget.curves.items()}, baseline)
        self._commit.assert_not_called()

    async def test_set_key_positions_repeated_updates_preserve_baseline_tangent_result(self):
        """Returning after forward and backward movement matches one equivalent move."""
        for tangent_type in (TangentType.CUSTOM, TangentType.SMOOTH):
            with self.subTest(title=tangent_type.name):
                # Arrange
                curve = self._curve()
                for key in curve.keys:
                    key.in_tangent_type = key.out_tangent_type = tangent_type
                    key.in_tangent_x, key.in_tangent_y = -0.08, -0.3
                    key.out_tangent_x, key.out_tangent_y = 0.08, 0.3
                    key.tangent_broken = False
                baseline = self._set_curves(curve)
                expected = replace(curve, keys=[replace(key) for key in baseline["first"]])
                expected.keys[1].time, expected.keys[1].value = 0.45, 6.0
                fcurve_widget.process_curve(expected, self._widget.bounds_for("first"), 0.001)
                for position in ((0.55, 7.5), (0.25, 4.0)):
                    self._widget.set_key_positions({KeyReference("first", 1): position}, baseline=baseline)

                # Act
                self._widget.set_key_positions({KeyReference("first", 1): (0.45, 6.0)}, baseline=baseline)

                # Assert
                self.assertEqual(curve.keys, expected.keys)
                self.assertEqual(baseline["first"][1].time, 0.4)
                self.assertEqual(baseline["first"][1].value, 7.0)

    @staticmethod
    def _curve(curve_id: str = "first") -> FCurve:
        """Return keys with room to move and a stationary neighbor."""
        return FCurve(
            id=curve_id,
            keys=[FCurveKey(time=0.2, value=1.0), FCurveKey(time=0.4, value=7.0), FCurveKey(time=0.6, value=3.0)],
        )

    def _set_curves(self, *curves: FCurve) -> dict[str, list[FCurveKey]]:
        """Load fixture curves and capture independent copies of every key field."""
        self._widget.set_curves({curve.id: curve for curve in curves})
        return {curve.id: [replace(key) for key in curve.keys] for curve in curves}


class TestSelectionInfo(omni.kit.test.AsyncTestCase):
    """Test SelectionInfo dataclass helper properties."""

    async def test_is_empty_when_empty(self):
        """is_empty should be True when no selection."""
        info = SelectionInfo()
        self.assertTrue(info.is_empty)

    async def test_is_empty_with_keys(self):
        """is_empty should be False when keys selected."""
        info = SelectionInfo(keys=[KeyReference("curve1", 0)])
        self.assertFalse(info.is_empty)

    async def test_curve_ids_single_curve(self):
        """curve_ids should return unique curve IDs."""
        info = SelectionInfo(
            keys=[
                KeyReference("curve1", 0),
                KeyReference("curve1", 1),
            ]
        )
        self.assertEqual(info.curve_ids, {"curve1"})

    async def test_curve_ids_multi_curve(self):
        """curve_ids should return all unique curve IDs."""
        info = SelectionInfo(
            keys=[
                KeyReference("curve1", 0),
                KeyReference("curve2", 0),
            ]
        )
        self.assertEqual(info.curve_ids, {"curve1", "curve2"})

    async def test_has_single_key(self):
        """has_single_key should be True for exactly one key."""
        info = SelectionInfo(keys=[KeyReference("curve1", 0)])
        self.assertTrue(info.has_single_key)

        info = SelectionInfo(
            keys=[
                KeyReference("curve1", 0),
                KeyReference("curve1", 1),
            ]
        )
        self.assertFalse(info.has_single_key)

    async def test_key_count(self):
        """key_count should return number of selected keys."""
        info = SelectionInfo(
            keys=[
                KeyReference("curve1", 0),
                KeyReference("curve2", 0),
            ]
        )
        self.assertEqual(info.key_count, 2)


class TestSubscribeCurveChanged(omni.kit.test.AsyncTestCase):
    """Test subscribe_curve_changed() unified event."""

    async def setUp(self):
        self._window = ui.Window("Test", width=400, height=300)
        with self._window.frame:
            self._widget = FCurveWidget()

        self._changed_curve_ids: list[str] = []
        self._sub = self._widget.subscribe_curve_changed(self._changed_curve_ids.append)

        # Set up test curve
        self._widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=0.0, value=0.0),
                        FCurveKey(time=1.0, value=1.0),
                    ],
                )
            }
        )
        self._changed_curve_ids.clear()  # Clear events from set_curves

    async def tearDown(self):
        self._sub = None
        self._widget.destroy()
        self._window.destroy()

    async def test_add_key_fires_event(self):
        """Adding a key should fire curve_changed."""
        self._widget.add_key("test", 0.5, 0.5)

        self.assertEqual(len(self._changed_curve_ids), 1)
        self.assertEqual(self._changed_curve_ids[0], "test")

    async def test_delete_selected_keys_fires_event(self):
        """Deleting keys should fire curve_changed."""
        self._widget.select_keys([KeyReference("test", 0)])
        self._widget.delete_selected_keys()

        self.assertIn("test", self._changed_curve_ids)

    async def test_set_key_tangent_type_fires_event(self):
        """Setting tangent type should fire curve_changed."""
        self._widget.set_key_tangent_type("test", 0, TangentType.FLAT, TangentType.FLAT)

        self.assertEqual(len(self._changed_curve_ids), 1)
        self.assertEqual(self._changed_curve_ids[0], "test")

    async def test_set_curve_infinity_fires_event(self):
        """Setting infinity type should fire curve_changed."""
        self._widget.set_curve_infinity("test", pre_infinity=InfinityType.LINEAR)

        self.assertEqual(len(self._changed_curve_ids), 1)
        self.assertEqual(self._changed_curve_ids[0], "test")


class TestSelectionProperty(omni.kit.test.AsyncTestCase):
    """Test FCurveWidget.selection property."""

    async def setUp(self):
        self._window = ui.Window("Test", width=400, height=300)
        with self._window.frame:
            self._widget = FCurveWidget()

        self._widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=0.0, value=0.0),
                        FCurveKey(time=1.0, value=1.0),
                    ],
                )
            }
        )

    async def tearDown(self):
        self._widget.destroy()
        self._window.destroy()

    async def test_selection_returns_selection_info(self):
        """selection property should return SelectionInfo instance."""
        info = self._widget.selection
        self.assertIsInstance(info, SelectionInfo)

    async def test_selection_reflects_selected_keys(self):
        """selection should reflect currently selected keys."""
        self._widget.select_keys([KeyReference("test", 0)])

        info = self._widget.selection
        self.assertEqual(len(info.keys), 1)
        self.assertEqual(info.keys[0].curve_id, "test")
        self.assertEqual(info.keys[0].key_index, 0)


class TestGetSelectionTangentType(omni.kit.test.AsyncTestCase):
    """Test get_selection_tangent_type() method."""

    async def setUp(self):
        self._window = ui.Window("Test", width=400, height=300)
        with self._window.frame:
            self._widget = FCurveWidget()

        self._widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.0,
                            value=0.0,
                            in_tangent_type=TangentType.LINEAR,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                        FCurveKey(
                            time=1.0,
                            value=1.0,
                            in_tangent_type=TangentType.LINEAR,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                )
            }
        )

    async def tearDown(self):
        self._widget.destroy()
        self._window.destroy()

    async def test_no_selection_returns_none(self):
        """No selection should return (None, None)."""
        in_type, out_type = self._widget.get_selection_tangent_type()
        self.assertIsNone(in_type)
        self.assertIsNone(out_type)

    async def test_single_key_returns_types(self):
        """Single key selection should return its tangent types."""
        self._widget.select_keys([KeyReference("test", 0)])

        in_type, out_type = self._widget.get_selection_tangent_type()
        self.assertEqual(in_type, TangentType.LINEAR)
        self.assertEqual(out_type, TangentType.LINEAR)

    async def test_mixed_types_returns_none(self):
        """Mixed tangent types should return None."""
        # Change one key's tangent type
        self._widget.set_key_tangent_type("test", 1, TangentType.FLAT, TangentType.FLAT)

        # Select both keys
        self._widget.select_keys(
            [
                KeyReference("test", 0),
                KeyReference("test", 1),
            ]
        )

        in_type, out_type = self._widget.get_selection_tangent_type()
        self.assertIsNone(in_type)  # Mixed: LINEAR vs FLAT
        self.assertIsNone(out_type)


class TestSetSelectedKeysTangentType(omni.kit.test.AsyncTestCase):
    """Test set_selected_keys_tangent_type() method."""

    async def setUp(self):
        self._window = ui.Window("Test", width=400, height=300)
        with self._window.frame:
            self._widget = FCurveWidget()

        self._widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.0,
                            value=0.0,
                            in_tangent_type=TangentType.LINEAR,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                        FCurveKey(
                            time=1.0,
                            value=1.0,
                            in_tangent_type=TangentType.LINEAR,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                )
            }
        )

    async def tearDown(self):
        self._widget.destroy()
        self._window.destroy()

    async def test_no_selection_returns_zero(self):
        """No selection should return 0 modified."""
        count = self._widget.set_selected_keys_tangent_type(TangentType.FLAT)
        self.assertEqual(count, 0)

    async def test_modifies_selected_keys(self):
        """Should modify tangent type on selected keys."""
        self._widget.select_keys([KeyReference("test", 0)])

        count = self._widget.set_selected_keys_tangent_type(TangentType.FLAT)

        self.assertEqual(count, 1)

        # Verify the tangent type changed
        curve = self._widget.curves["test"]
        self.assertEqual(curve.keys[0].in_tangent_type, TangentType.FLAT)
        self.assertEqual(curve.keys[0].out_tangent_type, TangentType.FLAT)

    async def test_modifies_multiple_keys(self):
        """Should modify all selected keys."""
        self._widget.select_keys(
            [
                KeyReference("test", 0),
                KeyReference("test", 1),
            ]
        )

        count = self._widget.set_selected_keys_tangent_type(TangentType.AUTO)

        self.assertEqual(count, 2)

        curve = self._widget.curves["test"]
        self.assertEqual(curve.keys[0].in_tangent_type, TangentType.AUTO)
        self.assertEqual(curve.keys[1].in_tangent_type, TangentType.AUTO)

    async def test_in_only_flag(self):
        """Should only modify in_tangent when out_tangent=False."""
        self._widget.select_keys([KeyReference("test", 0)])

        self._widget.set_selected_keys_tangent_type(
            TangentType.FLAT,
            in_tangent=True,
            out_tangent=False,
        )

        curve = self._widget.curves["test"]
        self.assertEqual(curve.keys[0].in_tangent_type, TangentType.FLAT)
        self.assertEqual(curve.keys[0].out_tangent_type, TangentType.LINEAR)  # Unchanged

    async def test_fires_curve_changed_event(self):
        """Should fire curve_changed event."""
        changed_ids: list[str] = []
        sub = self._widget.subscribe_curve_changed(changed_ids.append)

        self._widget.select_keys([KeyReference("test", 0)])
        self._widget.set_selected_keys_tangent_type(TangentType.FLAT)

        self.assertIn("test", changed_ids)
        del sub  # Release subscription
