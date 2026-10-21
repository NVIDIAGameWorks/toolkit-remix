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

from dataclasses import replace
from unittest import mock

import omni.kit.test

from omni.flux.fcurve.widget import CurveBounds, FCurve, FCurveKey, TangentType
from omni.flux.fcurve.widget._internal import curve_widgets_manager
from omni.flux.fcurve.widget._internal.curve_widgets_manager import CurveWidgetsManager
from omni.flux.fcurve.widget._internal.viewport import ViewportState

__all__ = ["TestCurveWidgetsManager"]


class TestCurveWidgetsManager(omni.kit.test.AsyncTestCase):
    """Verify renderer synchronization scheduling without constructing native widgets."""

    async def setUp(self):
        """Construct a manager with no external UI or event subscription."""
        self._manager = CurveWidgetsManager(FCurve(id="test"), ViewportState(), CurveBounds(), curve_color=0xFFFFFFFF)

    async def tearDown(self):
        """Release manager state after each test."""
        self._manager.destroy()

    async def test_build_roundoff_gap_preserves_requested_positions(self):
        """Rebuilding a manager retains tolerance-valid minimum-gap coordinates."""
        # Arrange
        times = (0.001 + 0.008, 0.002 + 0.008)
        self._manager._curve.keys = [FCurveKey(time=time, value=1.0) for time in times]
        keys = tuple(self._manager._curve.keys)
        with (
            mock.patch.object(curve_widgets_manager.omni.kit.app, "get_app"),
            mock.patch.object(self._manager, "_sync"),
        ):
            # Act
            self._manager.build(mock.Mock())

        # Assert
        self.assertEqual(tuple(key.time for key in self._manager._curve.keys), times)
        for index, key in enumerate(keys):
            self.assertIs(self._manager._curve.keys[index], key)

    async def test_update_repeated_position_requests_synchronize_once_without_rebuild(self):
        """Several numeric callbacks in one frame require just one position synchronization."""
        # Arrange
        with (
            mock.patch.object(self._manager, "_sync_positions") as sync_positions,
            mock.patch.object(self._manager, "_sync_topology") as sync_topology,
            mock.patch.object(self._manager, "_rebuild_tangents") as rebuild_tangents,
        ):
            for _ in range(5):
                self._manager.request_position_sync()
            pending = self._manager._positions_dirty
            immediate_syncs = sync_positions.call_count

            # Act
            self._manager._on_update(None)

        # Assert
        self.assertTrue(pending)
        self.assertEqual(immediate_syncs, 0)
        self.assertFalse(self._manager._positions_dirty)
        sync_positions.assert_called_once_with()
        sync_topology.assert_not_called()
        rebuild_tangents.assert_not_called()

    async def test_update_after_positions_flushed_does_not_resynchronize(self):
        """An idle frame does no repeated work for an already rendered numeric change."""
        # Arrange
        self._manager.request_position_sync()
        self._manager._on_update(None)
        with mock.patch.object(self._manager, "_sync_positions") as sync_positions:
            # Act
            self._manager._on_update(None)

        # Assert
        sync_positions.assert_not_called()

    async def test_insert_key_coarse_or_endpoint_native_candidate_recovers_pointer_time(self):
        """Recover an on-curve press without depending on native projection precision."""
        for parameter in (0.4, 0.0, 1.0):
            for width, height, zoom, origin in ((100, 100, 1.0, (0, 0)), (500, 300, 0.5, (17, 43))):
                with self.subTest(title=f"parameter={parameter}, size={(width, height)}, zoom={zoom}"):
                    # Arrange
                    x, y = self._prepare_insertion(width, height, zoom, origin)

                    # Act
                    self._manager._insert_key(0, parameter, x, y)

                    # Assert
                    self.assertEqual(len(self._manager._curve.keys), 3)
                    inserted = self._manager._curve.keys[1]
                    self.assertEqual((inserted.time, inserted.value), (0.5, 5.0))
                    self._manager._on_insert_started.assert_called_once_with()
                    self._manager._on_key_added.assert_called_once_with(1)
                    self.assertIs(self._manager._inserted_key, inserted)

    async def test_insert_key_steep_native_hit_preserves_projection_without_inversion(self):
        """A valid nearest-point projection must survive a distant inverse-time projection."""
        for parameter, pointer_offset in ((0.5, 3.0), (0.01, -3.0)):
            with self.subTest(title=f"parameter={parameter}, pointer_offset={pointer_offset}"):
                # Arrange
                self._prepare_insertion()
                x, y = self._manager._vp.model_to_pixel(parameter, parameter * 10.0)
                with mock.patch.object(
                    curve_widgets_manager, "bezier_parameter_at_time", side_effect=AssertionError("native hit must win")
                ):
                    # Act
                    self._manager._insert_key(0, parameter, x + pointer_offset, y)

                # Assert
                inserted = self._manager._curve.keys[1]
                self.assertAlmostEqual(inserted.time, parameter)
                self.assertAlmostEqual(inserted.value, parameter * 10.0)
                self.assertAlmostEqual(self._manager._insert_pointer_offset[0], -pointer_offset)
                self._manager._on_insert_started.assert_called_once_with()

    async def test_insert_key_fallback_uses_logical_pixel_hit_radius(self):
        """Viewport dimensions and canvas zoom do not widen the six-pixel background boundary."""
        for distance, accepted in ((5.9, True), (6.1, False)):
            for width, height, zoom, origin in ((100, 100, 1.0, (0, 0)), (300, 500, 2.0, (43, 17))):
                with self.subTest(title=f"distance={distance}, size={(width, height)}, zoom={zoom}"):
                    # Arrange
                    x, y = self._prepare_insertion(width, height, zoom, origin)
                    before = [replace(key) for key in self._manager._curve.keys]

                    # Act
                    self._manager._insert_key(0, 0.4, x, y + distance)

                    # Assert
                    self.assertEqual(len(self._manager._curve.keys), 3 if accepted else 2)
                    self.assertEqual(self._manager._on_insert_started.call_count, int(accepted))
                    self.assertEqual(self._manager._on_key_added.call_count, int(accepted))
                    if not accepted:
                        self.assertEqual(self._manager._curve.keys, before)
                        self.assertFalse(self._manager.is_inserting_key)

    async def test_insert_key_invalid_native_parameter_rejects_without_fallback(self):
        """Only native parameters within the closed segment interval may be retried."""
        for parameter in (-0.1, 1.1, float("nan"), float("inf")):
            with self.subTest(title=f"parameter={parameter}"):
                # Arrange
                x, y = self._prepare_insertion()
                before = [replace(key) for key in self._manager._curve.keys]
                with mock.patch.object(curve_widgets_manager, "bezier_parameter_at_time") as invert:
                    # Act
                    self._manager._insert_key(0, parameter, x, y)

                # Assert
                self.assertEqual(self._manager._curve.keys, before)
                self._manager._on_insert_started.assert_not_called()
                invert.assert_not_called()

    async def test_insert_key_fallback_time_outside_segment_rejects_without_inversion(self):
        """A missed native candidate cannot project a background press beyond the segment."""
        for time in (-0.1, 0.0, 1.0, 1.1):
            with self.subTest(title=f"pointer_time={time}"):
                # Arrange
                self._prepare_insertion()
                x, y = self._manager._vp.model_to_pixel(time, 5.0)
                before = [replace(key) for key in self._manager._curve.keys]
                with mock.patch.object(curve_widgets_manager, "bezier_parameter_at_time") as invert:
                    # Act
                    self._manager._insert_key(0, 0.5, x, y)

                # Assert
                self.assertEqual(self._manager._curve.keys, before)
                self._manager._on_insert_started.assert_not_called()
                invert.assert_not_called()

    async def test_insert_key_native_hit_rejected_by_spacing_or_shape_does_not_retry(self):
        """Fallback must not bypass the constraints of an already accepted native hit."""
        for title, parameter in (("minimum spacing", 0.0005), ("split tangent width", 0.0025)):
            with self.subTest(title=title):
                # Arrange
                self._prepare_insertion()
                x, y = self._manager._vp.model_to_pixel(parameter + 0.005, (parameter + 0.005) * 10.0)
                before = [replace(key) for key in self._manager._curve.keys]
                with mock.patch.object(curve_widgets_manager, "bezier_parameter_at_time") as invert:
                    # Act
                    self._manager._insert_key(0, parameter, x, y)

                # Assert
                self.assertEqual(self._manager._curve.keys, before)
                self._manager._on_insert_started.assert_not_called()
                invert.assert_not_called()

    async def test_insert_key_step_uses_only_native_horizontal_candidate(self):
        """STEP accepts its native horizontal hit without attempting Bezier inversion."""
        for parameter, accepted in ((0.5, True), (0.4, False), (0.0, False), (1.0, False)):
            with self.subTest(title=f"parameter={parameter}"):
                # Arrange
                self._prepare_insertion()
                self._manager._curve.keys[0].out_tangent_type = TangentType.STEP
                x, y = self._manager._vp.model_to_pixel(0.5, 0.0)
                with mock.patch.object(curve_widgets_manager, "bezier_parameter_at_time") as invert:
                    # Act
                    self._manager._insert_key(0, parameter, x, y)

                # Assert
                self.assertEqual(len(self._manager._curve.keys), 3 if accepted else 2)
                self.assertEqual(self._manager._on_insert_started.call_count, int(accepted))
                invert.assert_not_called()
                if accepted:
                    inserted = self._manager._curve.keys[1]
                    self.assertEqual((inserted.time, inserted.value), (0.5, 0.0))
                    self.assertEqual(inserted.out_tangent_type, TangentType.STEP)

    def _prepare_insertion(self, width=100, height=100, zoom=1.0, origin=(0, 0)) -> tuple[float, float]:
        """Prepare a steep linear Bezier and return its midpoint in screen coordinates."""
        self._manager._curve.keys = [
            FCurveKey(time=0.0, value=0.0, out_tangent_x=1 / 3, out_tangent_y=10 / 3),
            FCurveKey(time=1.0, value=10.0, in_tangent_x=-1 / 3, in_tangent_y=-10 / 3),
        ]
        self._manager._vp = ViewportState(width=width, height=height)
        self._manager._stack = mock.Mock(screen_position_x=origin[0], screen_position_y=origin[1])
        self._manager._zoom = zoom
        self._manager._on_insert_started = mock.Mock(return_value=True)
        self._manager._on_key_added = mock.Mock()
        self._manager._inserted_key = None
        x, y = self._manager._vp.model_to_pixel(0.5, 5.0)
        return origin[0] + x * zoom, origin[1] + y * zoom
