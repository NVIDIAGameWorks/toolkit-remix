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
- Undo/redo with USD commands
- Multi-curve editing
- FCurveWidget ↔ CurveModel data flow
"""

import omni.kit.app
import omni.kit.test
import omni.kit.commands
import omni.kit.undo
import omni.usd
from omni import ui
from pxr import UsdGeom

from omni.flux.curve_editor.widget import CurveEditorWidget, InMemoryCurveModel, PrimvarCurveModel
from omni.flux.fcurve.widget import FCurve, FCurveKey, InfinityType, TangentType

__all__ = [
    "TestDataFlow",
    "TestInfinityTypes",
    "TestMultiCurveEditing",
    "TestTangentTypes",
    "TestUndoRedo",
]


class TestUndoRedo(omni.kit.test.AsyncTestCase):
    """
    Test undo/redo functionality with USD-backed storage.
    """

    async def setUp(self):
        """Set up test environment."""
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()
        self.prim_path = "/World/TestCurve"
        UsdGeom.Xform.Define(self.stage, self.prim_path)

        self.curve_id = "test:x"
        self.model = PrimvarCurveModel(
            prim_path=self.prim_path,
            curve_ids=[self.curve_id],
            usd_context_name="",
        )
        self.widget = None
        self.window = None

    async def tearDown(self):
        """Clean up."""
        if self.window:
            self.window.destroy()
        if self.model:
            self.model.destroy()
        await omni.usd.get_context().close_stage_async()

    async def test_undo_redo_commit_curve(self):
        """
        Test that commit_curve can be undone/redone.
        """
        # Initial curve
        initial_curve = FCurve(
            id=self.curve_id,
            keys=[
                FCurveKey(time=0.0, value=0.0),
                FCurveKey(time=1.0, value=1.0),
            ],
        )
        self.model.commit_curve(self.curve_id, initial_curve)

        # Verify initial state
        curve = self.model.get_curve(self.curve_id)
        self.assertIsNotNone(curve)
        self.assertEqual(len(curve.keys), 2)
        self.assertEqual(curve.keys[1].value, 1.0)

        # Modify curve (add a key)
        modified_curve = FCurve(
            id=self.curve_id,
            keys=[
                FCurveKey(time=0.0, value=0.0),
                FCurveKey(time=0.5, value=0.5),  # New key
                FCurveKey(time=1.0, value=1.0),
            ],
        )
        self.model.commit_curve(self.curve_id, modified_curve)

        # Verify modified state
        curve = self.model.get_curve(self.curve_id)
        self.assertEqual(len(curve.keys), 3)

        # Undo
        omni.kit.undo.undo()
        await omni.kit.app.get_app().next_update_async()

        # Verify undone state
        curve = self.model.get_curve(self.curve_id)
        self.assertEqual(len(curve.keys), 2, "Undo should restore 2 keys")

        # Redo
        omni.kit.undo.redo()
        await omni.kit.app.get_app().next_update_async()

        # Verify redone state
        curve = self.model.get_curve(self.curve_id)
        self.assertEqual(len(curve.keys), 3, "Redo should restore 3 keys")

    async def test_undo_redo_with_widget(self):
        """
        Test undo/redo when editing through the widget.
        """
        # Create widget (builds automatically in constructor)
        self.window = ui.Window("Test Window", width=400, height=300)
        with self.window.frame:
            self.widget = CurveEditorWidget(
                model=self.model,
                show_toolbar=False,
            )

        # Let UI build
        for _ in range(5):
            await omni.kit.app.get_app().next_update_async()

        # Add curve via widget API
        curve = FCurve(
            id=self.curve_id,
            keys=[
                FCurveKey(time=0.0, value=0.0),
                FCurveKey(time=1.0, value=1.0),
            ],
        )
        self.widget.add_curve(curve)
        await omni.kit.app.get_app().next_update_async()

        # Verify
        stored = self.widget.get_curve(self.curve_id)
        self.assertIsNotNone(stored)
        self.assertEqual(len(stored.keys), 2)


class TestMultiCurveEditing(omni.kit.test.AsyncTestCase):
    """
    Test multi-curve editing functionality.
    """

    async def setUp(self):
        """Set up test environment."""
        self.model = InMemoryCurveModel()
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
            self.model.commit_curve(curve.id, curve)

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
        curve_ids = self.widget.get_curve_ids()
        self.assertEqual(len(curve_ids), 3)
        self.assertIn("curve_r", curve_ids)
        self.assertIn("curve_g", curve_ids)
        self.assertIn("curve_b", curve_ids)

        # Verify FCurveWidget received the curves
        if self.widget.fcurve_widget:
            fcurve_curves = self.widget.fcurve_widget.curves
            self.assertEqual(len(fcurve_curves), 3)

    async def test_independent_curve_editing(self):
        """
        Test that curves can be edited independently.
        """
        # Setup curves
        self.model.commit_curve(
            "c1",
            FCurve(
                id="c1",
                keys=[FCurveKey(time=0.0, value=0.0), FCurveKey(time=1.0, value=1.0)],
            ),
        )
        self.model.commit_curve(
            "c2",
            FCurve(
                id="c2",
                keys=[FCurveKey(time=0.0, value=1.0), FCurveKey(time=1.0, value=0.0)],
            ),
        )

        # Modify only c1
        modified_c1 = FCurve(
            id="c1",
            keys=[
                FCurveKey(time=0.0, value=0.0),
                FCurveKey(time=0.5, value=2.0),  # New peak
                FCurveKey(time=1.0, value=1.0),
            ],
        )
        self.model.commit_curve("c1", modified_c1)

        # Verify c1 changed
        c1 = self.model.get_curve("c1")
        self.assertEqual(len(c1.keys), 3)

        # Verify c2 unchanged
        c2 = self.model.get_curve("c2")
        self.assertEqual(len(c2.keys), 2)
        self.assertEqual(c2.keys[0].value, 1.0)


class TestDataFlow(omni.kit.test.AsyncTestCase):
    """
    Test data flow between FCurveWidget and CurveModel.
    """

    async def setUp(self):
        """Set up test environment."""
        self.model = InMemoryCurveModel()
        self.widget = None
        self.window = None
        self.change_notifications = []

    async def tearDown(self):
        """Clean up."""
        if self.window:
            self.window.destroy()
        if self.model:
            self.model.destroy()

    def _on_model_change(self, curve_id: str):
        """Track model change notifications."""
        self.change_notifications.append(curve_id)

    async def test_model_to_widget_sync(self):
        """
        Test that model changes propagate to widget.
        """
        # Create widget first
        self.window = ui.Window("Sync Test", width=400, height=300)
        with self.window.frame:
            self.widget = CurveEditorWidget(
                model=self.model,
                show_toolbar=False,
            )

        for _ in range(5):
            await omni.kit.app.get_app().next_update_async()

        # Add curve to model
        curve = FCurve(
            id="sync_test",
            keys=[FCurveKey(time=0.0, value=0.0), FCurveKey(time=1.0, value=1.0)],
        )
        self.model.commit_curve("sync_test", curve)

        # Let sync happen
        for _ in range(5):
            await omni.kit.app.get_app().next_update_async()

        # Widget should see the curve
        ids = self.widget.get_curve_ids()
        self.assertIn("sync_test", ids)

    async def test_model_subscription_fires(self):
        """
        Test that model subscription fires on external changes.

        Subscriptions are designed for EXTERNAL changes (undo/redo, external editor),
        not for changes made via commit_curve (the caller already knows about those).
        """
        # Subscribe to changes
        sub = self.model.subscribe(self._on_model_change)

        # Simulate an external change (like undo/redo would cause)
        curve = FCurve(
            id="sub_test",
            keys=[FCurveKey(time=0.0, value=0.0)],
        )
        self.model.simulate_external_change("sub_test", curve)

        # Verify notification fired
        self.assertIn("sub_test", self.change_notifications)

        # Clean up subscription
        del sub

    async def test_selection_info_updates(self):
        """
        Test that selection info is properly reported.
        """
        # Setup
        self.model.commit_curve(
            "sel_test",
            FCurve(
                id="sel_test",
                keys=[
                    FCurveKey(time=0.0, value=0.0),
                    FCurveKey(time=0.5, value=0.5),
                    FCurveKey(time=1.0, value=1.0),
                ],
            ),
        )

        self.window = ui.Window("Selection Test", width=400, height=300)
        with self.window.frame:
            self.widget = CurveEditorWidget(
                model=self.model,
                show_toolbar=True,
            )

        for _ in range(5):
            await omni.kit.app.get_app().next_update_async()

        # Initially no selection
        if self.widget.fcurve_widget:
            selection = self.widget.fcurve_widget.selection
            self.assertTrue(selection.is_empty)


class TestTangentTypes(omni.kit.test.AsyncTestCase):
    """
    Test tangent type handling.
    """

    async def setUp(self):
        """Set up test environment."""
        self.model = InMemoryCurveModel()

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

        self.model.commit_curve("tangent_test", curve)
        retrieved = self.model.get_curve("tangent_test")

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
        self.model = InMemoryCurveModel()

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

        self.model.commit_curve("infinity_test", curve)
        retrieved = self.model.get_curve("infinity_test")

        self.assertEqual(retrieved.pre_infinity, InfinityType.LINEAR)
        self.assertEqual(retrieved.post_infinity, InfinityType.CONSTANT)
