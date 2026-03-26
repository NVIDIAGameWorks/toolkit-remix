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

E2E Tests for tangent mirroring behavior during drag.

When tangent_broken=False (linked tangents), dragging one tangent handle
should automatically mirror the angle to the opposite tangent while
preserving its length.

Key behaviors tested:
1. Dragging OUT tangent mirrors angle to IN tangent
2. Dragging IN tangent mirrors angle to OUT tangent
3. Mirroring preserves opposite tangent's length
4. Mirroring only occurs when tangent_broken=False
5. No mirroring when tangent_broken=True
"""

import asyncio  # noqa: F401 - kept for interactive debugging
import math
import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
from omni import ui

from omni.flux.fcurve.widget import FCurveWidget, FCurve, FCurveKey, TangentType

__all__ = ["TestTangentMirroringDrag"]


# Test keyframe positions
KEY_0_TIME = 0.0
KEY_0_VALUE = 0.5
KEY_1_TIME = 0.5
KEY_1_VALUE = 0.5
KEY_2_TIME = 1.0
KEY_2_VALUE = 0.5

# Window dimensions
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 400
CURVE_WIDTH = 400
CURVE_HEIGHT = 280
PADDING = 30


class TestTangentMirroringDrag(omni.kit.test.AsyncTestCase):
    """Test tangent mirroring during drag when tangent_broken=False."""

    async def setUp(self):
        """Create window with FCurveWidget."""
        self._continue_clicked = False

        self.window = ui.Window(
            "Test Tangent Mirroring",
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
        )

        with self.window.frame:
            with ui.VStack():
                # Label and button area at top
                with ui.HStack(height=ui.Pixel(40)):
                    ui.Spacer(width=10)
                    self._label = ui.Label(
                        "",
                        style={"font_size": 14, "color": 0xFFFFFFFF},
                        alignment=ui.Alignment.LEFT_CENTER,
                    )
                    ui.Spacer()
                    self._continue_btn = ui.Button(
                        "Continue",
                        width=ui.Pixel(100),
                        clicked_fn=self._on_continue_clicked,
                        style={"background_color": 0xFF2266AA},
                    )
                    ui.Spacer(width=10)
                # Curve area
                with ui.HStack():
                    ui.Spacer(width=PADDING)
                    with ui.ZStack(
                        width=ui.Pixel(CURVE_WIDTH),
                        height=ui.Pixel(CURVE_HEIGHT),
                    ):
                        ui.Rectangle(style={"background_color": 0xFF1A1A1A})
                        self.widget = FCurveWidget(
                            time_range=(0.0, 1.0),
                            value_range=(0.0, 1.0),
                            viewport_size=(CURVE_WIDTH, CURVE_HEIGHT),
                        )
                    ui.Spacer(width=PADDING)
                ui.Spacer(height=PADDING)

        await omni.kit.app.get_app().next_update_async()

    def _on_continue_clicked(self):
        """Handle continue button click."""
        self._continue_clicked = True

    async def _wait_for_continue(self):
        """Wait for the continue button to be clicked (for interactive debugging)."""
        return
        # self._continue_clicked = False
        # while not self._continue_clicked:
        #     await asyncio.sleep(0.1)
        # self._continue_clicked = False

    def _set_label(self, text: str):
        """Set the label text to describe the current test configuration."""
        self._label.text = text

    async def tearDown(self):
        await self._wait_for_continue()
        if self.widget:
            self.widget.destroy()
            self.widget = None
        if self.window:
            self.window.destroy()
            self.window = None

    def _get_curve(self, curve_id: str = "test"):
        """Get the FCurve model data."""
        return self.widget.curves.get(curve_id)

    def _compute_tangent_angle(self, x: float, y: float) -> float:
        """Compute angle of tangent vector in radians."""
        if abs(x) < 1e-9 and abs(y) < 1e-9:
            return 0.0
        return math.atan2(y, x)

    def _compute_tangent_length(self, x: float, y: float) -> float:
        """Compute length of tangent vector."""
        return math.sqrt(x * x + y * y)

    def _assert_tangent(
        self,
        key_index: int,
        is_in_tangent: bool,
        expected_x: float,
        expected_y: float,
        delta: float = 0.02,
        msg: str = "",
    ):
        """Assert that a tangent has the expected offset values in the model."""
        curve = self._get_curve()
        key = curve.keys[key_index]

        if is_in_tangent:
            actual_x = key.in_tangent_x
            actual_y = key.in_tangent_y
            tangent_name = "IN"
        else:
            actual_x = key.out_tangent_x
            actual_y = key.out_tangent_y
            tangent_name = "OUT"

        self.assertAlmostEqual(
            actual_x, expected_x, delta=delta, msg=f"Key {key_index} {tangent_name} tangent X: {msg}"
        )
        self.assertAlmostEqual(
            actual_y, expected_y, delta=delta, msg=f"Key {key_index} {tangent_name} tangent Y: {msg}"
        )

    def _assert_angles_mirrored(
        self,
        key_index: int,
        delta_radians: float = 0.1,
        msg: str = "",
    ):
        """Assert that in and out tangent angles are mirrored (opposite directions)."""
        curve = self._get_curve()
        key = curve.keys[key_index]

        in_angle = self._compute_tangent_angle(key.in_tangent_x, key.in_tangent_y)
        out_angle = self._compute_tangent_angle(key.out_tangent_x, key.out_tangent_y)

        # Mirrored tangents have opposite directions
        # in_angle should be approximately out_angle + π (or out_angle - π)
        angle_diff = abs(in_angle - out_angle)
        # Normalize to [0, 2π]
        while angle_diff > math.pi:
            angle_diff = abs(angle_diff - 2 * math.pi)

        self.assertAlmostEqual(
            angle_diff,
            math.pi,
            delta=delta_radians,
            msg=f"Key {key_index} angles should be mirrored: in={in_angle:.3f}, out={out_angle:.3f}. {msg}",
        )

    def _get_tangent_widget(self, key_index: int, is_in_tangent: bool):
        """Get a tangent handle widget from the manager."""
        mgr = self.widget._managers.get("test")
        if not mgr or key_index >= len(mgr._groups):
            return None
        g = mgr._groups[key_index]
        return g.in_h if is_in_tangent else g.out_h

    async def _select_key(self, key_index: int):
        """Click a keyframe to select it (makes tangent handles visible)."""
        mgr = self.widget._managers["test"]
        handle = mgr.key_handles[key_index]
        pos = ui_test.Vec2(*handle.screen_center)
        await ui_test.input.emulate_mouse_move(pos)
        await ui_test.human_delay(3)
        await ui_test.emulate_mouse_click()
        await ui_test.human_delay(3)
        await omni.kit.app.get_app().next_update_async()

    async def _drag_tangent_widget(self, tangent_widget, dx: float, dy: float):
        """Drag a tangent handle by the given delta in pixels."""
        self.assertIsNotNone(tangent_widget, "Tangent widget must not be None")
        start_pos = ui_test.Vec2(*tangent_widget.screen_center)
        end_pos = start_pos + ui_test.Vec2(dx, dy)

        await ui_test.input.emulate_mouse_move(start_pos)
        await ui_test.human_delay(3)
        await ui_test.emulate_mouse_drag_and_drop(start_pos, end_pos)
        await ui_test.human_delay(3)
        await omni.kit.app.get_app().next_update_async()

    # =========================================================================
    # Test 1: Linked tangents - drag OUT, IN mirrors
    # =========================================================================
    async def test_linked_drag_out_mirrors_in(self):
        """When tangent_broken=False, dragging OUT tangent should mirror angle to IN.

        Setup:
        - Middle key (index 1) with tangent_broken=False
        - Both tangents start horizontal (in: -0.2, 0; out: 0.2, 0)
        - Drag OUT tangent upward
        - IN tangent should mirror (point downward with same angle magnitude)
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=KEY_0_TIME, value=KEY_0_VALUE),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.2,
                            in_tangent_y=0.0,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.2,
                            out_tangent_y=0.0,
                            tangent_broken=False,  # Linked!
                        ),
                        FCurveKey(time=KEY_2_TIME, value=KEY_2_VALUE),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Linked: Drag OUT up, IN should mirror down")

        # Verify initial state
        curve = self._get_curve()
        self.assertFalse(curve.keys[1].tangent_broken, "Key 1 should have linked tangents")
        self._assert_tangent(1, is_in_tangent=True, expected_x=-0.2, expected_y=0.0, msg="Initial IN")
        self._assert_tangent(1, is_in_tangent=False, expected_x=0.2, expected_y=0.0, msg="Initial OUT")

        # Select key to make tangent handles visible
        await self._select_key(1)

        # Get initial IN tangent length (should be preserved)
        initial_in_length = self._compute_tangent_length(curve.keys[1].in_tangent_x, curve.keys[1].in_tangent_y)

        await self._wait_for_continue()

        # Drag OUT tangent upward (screen Y is inverted, so negative dy = up)
        out_tangent = self._get_tangent_widget(1, is_in_tangent=False)
        self.assertIsNotNone(out_tangent, "OUT tangent widget should exist")
        await self._drag_tangent_widget(out_tangent, dx=0, dy=-40)  # 40px up

        # Check that IN tangent was mirrored
        curve = self._get_curve()
        _out_angle = self._compute_tangent_angle(curve.keys[1].out_tangent_x, curve.keys[1].out_tangent_y)
        _in_angle = self._compute_tangent_angle(curve.keys[1].in_tangent_x, curve.keys[1].in_tangent_y)

        # OUT should point up-right, IN should point down-left (mirrored)
        self.assertGreater(curve.keys[1].out_tangent_y, 0.05, "OUT should point upward after drag")
        self.assertLess(curve.keys[1].in_tangent_y, -0.05, "IN should be mirrored downward")

        # Verify angles are mirrored (differ by π)
        self._assert_angles_mirrored(1, msg="After dragging OUT up")

        # Verify IN tangent length was preserved
        final_in_length = self._compute_tangent_length(curve.keys[1].in_tangent_x, curve.keys[1].in_tangent_y)
        self.assertAlmostEqual(
            initial_in_length, final_in_length, delta=0.02, msg="IN tangent length should be preserved"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 2: Linked tangents - drag IN, OUT mirrors
    # =========================================================================
    async def test_linked_drag_in_mirrors_out(self):
        """When tangent_broken=False, dragging IN tangent should mirror angle to OUT.

        Setup:
        - Middle key with tangent_broken=False
        - Drag IN tangent downward
        - OUT tangent should mirror (point upward)
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=KEY_0_TIME, value=KEY_0_VALUE),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.2,
                            in_tangent_y=0.0,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.2,
                            out_tangent_y=0.0,
                            tangent_broken=False,
                        ),
                        FCurveKey(time=KEY_2_TIME, value=KEY_2_VALUE),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Linked: Drag IN down, OUT should mirror up")

        # Get initial OUT tangent length
        curve = self._get_curve()
        initial_out_length = self._compute_tangent_length(curve.keys[1].out_tangent_x, curve.keys[1].out_tangent_y)

        await self._select_key(1)
        await self._wait_for_continue()

        # Drag IN tangent downward (positive dy in screen = negative Y in model)
        in_tangent = self._get_tangent_widget(1, is_in_tangent=True)
        self.assertIsNotNone(in_tangent, "IN tangent widget should exist")
        await self._drag_tangent_widget(in_tangent, dx=0, dy=40)  # 40px down in screen

        # Check mirroring
        # IN tangent dragged down → negative Y in model (pointing down-left)
        # OUT tangent mirrored → positive Y in model (pointing up-right)
        curve = self._get_curve()
        self.assertLess(curve.keys[1].in_tangent_y, -0.05, "IN should point downward after drag (negative Y)")
        self.assertGreater(curve.keys[1].out_tangent_y, 0.05, "OUT should be mirrored upward (positive Y)")

        # Verify angles are mirrored
        self._assert_angles_mirrored(1, msg="After dragging IN down")

        # Verify OUT tangent length was preserved
        final_out_length = self._compute_tangent_length(curve.keys[1].out_tangent_x, curve.keys[1].out_tangent_y)
        self.assertAlmostEqual(
            initial_out_length, final_out_length, delta=0.02, msg="OUT tangent length should be preserved"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 3: Broken tangents - NO mirroring
    # =========================================================================
    async def test_broken_no_mirroring(self):
        """When tangent_broken=True, dragging one tangent should NOT affect the other.

        Setup:
        - Middle key with tangent_broken=True
        - Drag OUT tangent
        - IN tangent should remain unchanged
        """
        initial_in_x = -0.2
        initial_in_y = 0.05  # Slight upward angle

        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=KEY_0_TIME, value=KEY_0_VALUE),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=initial_in_x,
                            in_tangent_y=initial_in_y,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.2,
                            out_tangent_y=0.0,
                            tangent_broken=True,  # Broken!
                        ),
                        FCurveKey(time=KEY_2_TIME, value=KEY_2_VALUE),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Broken: Drag OUT, IN should NOT change")

        curve = self._get_curve()
        self.assertTrue(curve.keys[1].tangent_broken, "Key 1 should have broken tangents")

        await self._select_key(1)
        await self._wait_for_continue()

        # Drag OUT tangent significantly
        out_tangent = self._get_tangent_widget(1, is_in_tangent=False)
        await self._drag_tangent_widget(out_tangent, dx=20, dy=-50)

        # IN tangent should remain exactly as before
        curve = self._get_curve()
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=initial_in_x,
            expected_y=initial_in_y,
            delta=0.005,  # Tighter tolerance - should be unchanged
            msg="IN tangent should NOT change when broken",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 4: Mirroring preserves length - asymmetric tangents
    # =========================================================================
    async def test_mirroring_preserves_asymmetric_lengths(self):
        """Mirroring should preserve individual tangent lengths.

        Setup:
        - IN tangent: short (-0.1, 0)
        - OUT tangent: long (0.3, 0)
        - Drag OUT to change angle
        - Both should share the new angle but keep their lengths
        """
        short_length = 0.1
        long_length = 0.3

        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=KEY_0_TIME, value=KEY_0_VALUE),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-short_length,
                            in_tangent_y=0.0,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=long_length,
                            out_tangent_y=0.0,
                            tangent_broken=False,
                        ),
                        FCurveKey(time=KEY_2_TIME, value=KEY_2_VALUE),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Asymmetric lengths should be preserved during mirroring")

        await self._select_key(1)
        await self._wait_for_continue()

        # Drag OUT tangent to change angle
        out_tangent = self._get_tangent_widget(1, is_in_tangent=False)
        await self._drag_tangent_widget(out_tangent, dx=30, dy=-30)

        # Both tangents should have mirrored angles but original lengths
        curve = self._get_curve()
        final_in_length = self._compute_tangent_length(curve.keys[1].in_tangent_x, curve.keys[1].in_tangent_y)
        final_out_length = self._compute_tangent_length(curve.keys[1].out_tangent_x, curve.keys[1].out_tangent_y)

        self.assertAlmostEqual(final_in_length, short_length, delta=0.02, msg="IN tangent should keep short length")
        # OUT length changed because we dragged it
        self.assertNotAlmostEqual(final_out_length, long_length, delta=0.02, msg="OUT length should change from drag")

        # But angles should still be mirrored
        self._assert_angles_mirrored(1, msg="Angles still mirrored with different lengths")

        await self._wait_for_continue()

    # =========================================================================
    # Test 5: Diagonal drag - angle changes in both directions
    # =========================================================================
    async def test_diagonal_drag_mirroring(self):
        """Diagonal drag should properly mirror the resulting angle.

        Drag OUT tangent diagonally up-right, IN should mirror diagonally down-left.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=KEY_0_TIME, value=KEY_0_VALUE),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.2,
                            in_tangent_y=0.0,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.2,
                            out_tangent_y=0.0,
                            tangent_broken=False,
                        ),
                        FCurveKey(time=KEY_2_TIME, value=KEY_2_VALUE),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Diagonal drag: OUT up-right, IN down-left")

        await self._select_key(1)
        await self._wait_for_continue()

        # Diagonal drag: right (+X) and up (-Y screen)
        out_tangent = self._get_tangent_widget(1, is_in_tangent=False)
        await self._drag_tangent_widget(out_tangent, dx=30, dy=-30)

        curve = self._get_curve()

        # OUT should point up-right
        self.assertGreater(curve.keys[1].out_tangent_x, 0.2, "OUT X increased (right)")
        self.assertGreater(curve.keys[1].out_tangent_y, 0.0, "OUT Y increased (up)")

        # IN should point down-left (mirrored)
        self.assertLess(curve.keys[1].in_tangent_x, 0.0, "IN X negative (left)")
        self.assertLess(curve.keys[1].in_tangent_y, 0.0, "IN Y negative (down)")

        # Verify mirroring
        self._assert_angles_mirrored(1, msg="Diagonal mirroring")

        await self._wait_for_continue()

    # =========================================================================
    # Test 6: Multiple drags maintain mirroring
    # =========================================================================
    async def test_multiple_drags_maintain_mirroring(self):
        """Multiple sequential drags should maintain mirroring.

        Drag OUT, then drag IN - both operations should maintain mirror relationship.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=KEY_0_TIME, value=KEY_0_VALUE),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.2,
                            in_tangent_y=0.0,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.2,
                            out_tangent_y=0.0,
                            tangent_broken=False,
                        ),
                        FCurveKey(time=KEY_2_TIME, value=KEY_2_VALUE),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Multiple drags: OUT then IN")

        await self._select_key(1)
        await self._wait_for_continue()

        # First drag: OUT upward
        out_tangent = self._get_tangent_widget(1, is_in_tangent=False)
        await self._drag_tangent_widget(out_tangent, dx=0, dy=-30)

        self._assert_angles_mirrored(1, msg="After first drag (OUT)")

        # Second drag: IN to the left
        in_tangent = self._get_tangent_widget(1, is_in_tangent=True)
        await self._drag_tangent_widget(in_tangent, dx=-20, dy=0)

        self._assert_angles_mirrored(1, msg="After second drag (IN)")

        await self._wait_for_continue()

    # =========================================================================
    # Test 7: First key OUT tangent (no IN to mirror)
    # =========================================================================
    async def test_first_key_out_tangent_no_mirror(self):
        """First key has no IN tangent, so OUT drag shouldn't crash.

        First key only has OUT tangent - dragging should work without errors.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.2,
                            out_tangent_y=0.0,
                            tangent_broken=False,
                        ),
                        FCurveKey(time=KEY_1_TIME, value=KEY_1_VALUE),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("First key: OUT drag (no IN to mirror)")

        await self._select_key(0)
        await self._wait_for_continue()

        # Drag OUT tangent - should work without errors
        out_tangent = self._get_tangent_widget(0, is_in_tangent=False)
        self.assertIsNotNone(out_tangent, "First key should have OUT tangent")

        # Should not crash
        await self._drag_tangent_widget(out_tangent, dx=20, dy=-30)

        # Verify OUT tangent changed
        curve = self._get_curve()
        self.assertNotAlmostEqual(curve.keys[0].out_tangent_y, 0.0, delta=0.01, msg="OUT tangent Y should have changed")

        await self._wait_for_continue()

    # =========================================================================
    # Test 8: Last key IN tangent (no OUT to mirror)
    # =========================================================================
    async def test_last_key_in_tangent_no_mirror(self):
        """Last key has no OUT tangent, so IN drag shouldn't crash.

        Last key only has IN tangent - dragging should work without errors.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=KEY_0_TIME, value=KEY_0_VALUE),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.2,
                            in_tangent_y=0.0,
                            tangent_broken=False,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Last key: IN drag (no OUT to mirror)")

        await self._select_key(1)
        await self._wait_for_continue()

        # Drag IN tangent - should work without errors
        in_tangent = self._get_tangent_widget(1, is_in_tangent=True)
        self.assertIsNotNone(in_tangent, "Last key should have IN tangent")

        # Should not crash
        await self._drag_tangent_widget(in_tangent, dx=-20, dy=30)

        # Verify IN tangent changed
        curve = self._get_curve()
        self.assertNotAlmostEqual(curve.keys[1].in_tangent_y, 0.0, delta=0.01, msg="IN tangent Y should have changed")

        await self._wait_for_continue()

    # =========================================================================
    # Test 9: Widget visual update during drag
    # =========================================================================
    async def test_opposite_widget_updates_visually(self):
        """The opposite tangent WIDGET should update position during drag.

        Not just the model, but the visual handle should move.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=KEY_0_TIME, value=KEY_0_VALUE),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.2,
                            in_tangent_y=0.0,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.2,
                            out_tangent_y=0.0,
                            tangent_broken=False,
                        ),
                        FCurveKey(time=KEY_2_TIME, value=KEY_2_VALUE),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Widget visual update test")

        await self._select_key(1)

        # Get IN tangent widget and record initial position
        in_tangent = self._get_tangent_widget(1, is_in_tangent=True)
        self.assertIsNotNone(in_tangent)
        initial_in_offset = in_tangent.position

        await self._wait_for_continue()

        # Drag OUT tangent
        out_tangent = self._get_tangent_widget(1, is_in_tangent=False)
        await self._drag_tangent_widget(out_tangent, dx=0, dy=-40)

        # IN tangent widget offset should have changed (visual update)
        final_in_offset = in_tangent.position
        self.assertNotEqual(
            initial_in_offset, final_in_offset, "IN tangent widget should update visually when OUT is dragged"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 10: Small drag still mirrors
    # =========================================================================
    async def test_small_drag_still_mirrors(self):
        """Even small drags should trigger mirroring."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=KEY_0_TIME, value=KEY_0_VALUE),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.2,
                            in_tangent_y=0.0,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.2,
                            out_tangent_y=0.0,
                            tangent_broken=False,
                        ),
                        FCurveKey(time=KEY_2_TIME, value=KEY_2_VALUE),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()

        await self._select_key(1)

        # Very small drag
        out_tangent = self._get_tangent_widget(1, is_in_tangent=False)
        await self._drag_tangent_widget(out_tangent, dx=5, dy=-5)

        # Should still be mirrored
        self._assert_angles_mirrored(1, msg="Small drag still mirrors")
