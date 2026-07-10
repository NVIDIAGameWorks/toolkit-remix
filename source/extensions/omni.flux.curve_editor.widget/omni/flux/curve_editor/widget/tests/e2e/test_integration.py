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

E2E Integration Tests - Full stack tests for curve editor.

Tests:
- Multi-curve editing
- FCurveWidget ↔ GroupedKeysModel data flow
"""

import omni.kit.app
import omni.kit.test
from omni import ui

from omni.flux.curve_editor.widget import CurveEditorWidget
from omni.flux.curve_editor.widget.payload import curve_to_payload, payload_to_curve
from omni.flux.utils.widget import InMemoryGroupedKeysModel
from omni.flux.fcurve.widget import FCurve, FCurveKey, InfinityType, TangentType

__all__ = [
    "TestInfinityTypes",
    "TestMultiCurveEditing",
    "TestTangentTypes",
]


def _commit_payload(model, curve_id: str, curve: FCurve) -> None:
    model.commit_payload(curve_id, curve_to_payload(curve))


def _get_curve(model, curve_id: str) -> FCurve | None:
    return payload_to_curve(curve_id, model.get_payload(curve_id))


class TestMultiCurveEditing(omni.kit.test.AsyncTestCase):
    """
    Test multi-curve editing functionality.
    """

    async def setUp(self):
        """Set up test environment."""
        self.model = InMemoryGroupedKeysModel()
        self.widget = None
        self.window = None

    async def tearDown(self):
        """Clean up."""
        if self.window:
            self.window.destroy()
        if self.model:
            self.model.destroy()

    async def test_multiple_curves_display(self):
        """
        Test that multiple curves can be displayed simultaneously.
        """
        # Create multiple curves
        curves = [
            FCurve(
                id="curve_r",
                keys=[FCurveKey(time=0.0, value=0.0), FCurveKey(time=1.0, value=1.0)],
                color=0xFFFF0000,  # Red
            ),
            FCurve(
                id="curve_g",
                keys=[FCurveKey(time=0.0, value=0.5), FCurveKey(time=1.0, value=0.5)],
                color=0xFF00FF00,  # Green
            ),
            FCurve(
                id="curve_b",
                keys=[FCurveKey(time=0.0, value=1.0), FCurveKey(time=1.0, value=0.0)],
                color=0xFF0000FF,  # Blue
            ),
        ]

        for curve in curves:
            _commit_payload(self.model, curve.id, curve)

        # Create widget
        self.window = ui.Window("Multi-Curve Test", width=600, height=400)
        with self.window.frame:
            self.widget = CurveEditorWidget(
                model=self.model,
                show_toolbar=True,
            )

        # Let UI build
        for _ in range(10):
            await omni.kit.app.get_app().next_update_async()

        # Verify all curves are accessible
        curve_ids = self.widget.model.group_ids
        self.assertEqual(len(curve_ids), 3)
        self.assertIn("curve_r", curve_ids)
        self.assertIn("curve_g", curve_ids)
        self.assertIn("curve_b", curve_ids)

        # Verify FCurveWidget received the curves
        if self.widget.fcurve_widget:
            fcurve_curves = self.widget.fcurve_widget.curves
            self.assertEqual(len(fcurve_curves), 3)


class TestTangentTypes(omni.kit.test.AsyncTestCase):
    """
    Test tangent type handling.
    """

    async def setUp(self):
        """Set up test environment."""
        self.model = InMemoryGroupedKeysModel()

    async def tearDown(self):
        """Clean up."""
        if self.model:
            self.model.destroy()

    async def test_tangent_type_preservation(self):
        """
        Test that tangent types are preserved through commit/get cycle.
        """
        # Create curve with various tangent types
        curve = FCurve(
            id="tangent_test",
            keys=[
                FCurveKey(
                    time=0.0,
                    value=0.0,
                    in_tangent_type=TangentType.FLAT,
                    out_tangent_type=TangentType.LINEAR,
                ),
                FCurveKey(
                    time=0.5,
                    value=1.0,
                    in_tangent_type=TangentType.AUTO,
                    out_tangent_type=TangentType.AUTO,
                ),
                FCurveKey(
                    time=1.0,
                    value=0.0,
                    in_tangent_type=TangentType.SMOOTH,
                    out_tangent_type=TangentType.STEP,
                ),
            ],
        )

        _commit_payload(self.model, "tangent_test", curve)
        retrieved = _get_curve(self.model, "tangent_test")

        # Verify tangent types preserved
        self.assertEqual(retrieved.keys[0].in_tangent_type, TangentType.FLAT)
        self.assertEqual(retrieved.keys[0].out_tangent_type, TangentType.LINEAR)
        self.assertEqual(retrieved.keys[1].in_tangent_type, TangentType.AUTO)
        self.assertEqual(retrieved.keys[1].out_tangent_type, TangentType.AUTO)
        self.assertEqual(retrieved.keys[2].in_tangent_type, TangentType.SMOOTH)
        self.assertEqual(retrieved.keys[2].out_tangent_type, TangentType.STEP)


class TestInfinityTypes(omni.kit.test.AsyncTestCase):
    """
    Test infinity type handling.
    """

    async def setUp(self):
        """Set up test environment."""
        self.model = InMemoryGroupedKeysModel()

    async def tearDown(self):
        """Clean up."""
        if self.model:
            self.model.destroy()

    async def test_infinity_type_preservation(self):
        """
        Test that infinity types are preserved through commit/get cycle.
        """
        curve = FCurve(
            id="infinity_test",
            keys=[
                FCurveKey(time=0.0, value=0.0),
                FCurveKey(time=1.0, value=1.0),
            ],
            pre_infinity=InfinityType.LINEAR,
            post_infinity=InfinityType.CONSTANT,
        )

        _commit_payload(self.model, "infinity_test", curve)
        retrieved = _get_curve(self.model, "infinity_test")

        self.assertEqual(retrieved.pre_infinity, InfinityType.LINEAR)
        self.assertEqual(retrieved.post_infinity, InfinityType.CONSTANT)
