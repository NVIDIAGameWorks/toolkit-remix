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

E2E Tests for CUSTOM tangent behavior.

CUSTOM tangent behavior (from TANGENT_BEHAVIOR.md):
- CUSTOM tangents are free-form: user can freely position handles in both X and Y
- What you set is what gets stored and rendered (after clamping)
- CUSTOM handles are still subject to hard rules:
  1. Y-axis flip prevention (IN X ≤ 0, OUT X ≥ 0)
  2. Bounding box clamping (handles must stay within curve bounds)
- CUSTOM is NOT limited by monotonic curve constraints (free draw support)
- This is the only tangent type where user's handle position maps directly to stored value

Key difference from other types:
- OTHER: Some form of auto-computation (LINEAR midpoint, AUTO neighbor-derived, SMOOTH halfway, etc.)
- CUSTOM: No computation - raw values preserved (only clamping applied)

Hard rules tested:
- Y-axis flip prevention
- Bounding box clamping (ray-box intersection preserves angle)
"""

import asyncio  # noqa: F401 - kept for interactive debugging in _wait_for_continue
import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
from omni import ui

from omni.flux.fcurve.widget import FCurveWidget, FCurve, FCurveKey, TangentType

__all__ = ["TestCustomTangents"]


# Test keyframe positions (3 keyframes)
KEY_0_TIME = 0.0
KEY_0_VALUE = 0.2
KEY_1_TIME = 0.5
KEY_1_VALUE = 0.6
KEY_2_TIME = 1.0
KEY_2_VALUE = 0.4

# Window dimensions
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 400
CURVE_WIDTH = 400
CURVE_HEIGHT = 280
PADDING = 30


class TestCustomTangents(omni.kit.test.AsyncTestCase):
    """Test CUSTOM tangent behavior: fully user-controlled with hard rule clamping."""

    async def setUp(self):
        """Create window with FCurveWidget."""
        self._continue_clicked = False

        self.window = ui.Window(
            "Test CUSTOM Tangents",
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
        """
        Wait for the continue button to be clicked.

        To enable interactive debugging, uncomment the loop below.
        """
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

    def _assert_tangent(
        self,
        key_index: int,
        is_in_tangent: bool,
        expected_x: float,
        expected_y: float,
        delta: float = 0.001,
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
    # Test 1: CUSTOM preserves exact user values (no auto-computation)
    # =========================================================================
    async def test_custom_preserves_exact_values(self):
        """CUSTOM tangent preserves exact user-provided X and Y values.

        Unlike SMOOTH/AUTO/LINEAR which compute values, CUSTOM stores
        exactly what the user sets (subject only to clamping).
        """
        # Set up with CUSTOM tangents with specific values
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.15,  # Arbitrary value
                            out_tangent_y=0.08,  # Arbitrary value
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.12,  # Arbitrary value
                            in_tangent_y=-0.05,  # Arbitrary value
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.2,  # Arbitrary value
                            out_tangent_y=0.1,  # Arbitrary value
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.25,  # Arbitrary value
                            in_tangent_y=0.15,  # Arbitrary value
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM: exact values preserved (no auto-computation)")

        # Key 0 OUT: exact value preserved
        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.15, expected_y=0.08, msg="CUSTOM preserves exact X and Y"
        )

        # Key 1 IN: exact value preserved
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=-0.12, expected_y=-0.05, msg="CUSTOM preserves exact X and Y"
        )

        # Key 1 OUT: exact value preserved
        self._assert_tangent(
            1, is_in_tangent=False, expected_x=0.2, expected_y=0.1, msg="CUSTOM preserves exact X and Y"
        )

        # Key 2 IN: exact value preserved
        self._assert_tangent(
            2, is_in_tangent=True, expected_x=-0.25, expected_y=0.15, msg="CUSTOM preserves exact X and Y"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 2: CUSTOM with various angles (free-form positioning)
    # =========================================================================
    async def test_custom_various_angles(self):
        """CUSTOM allows any angle - steep, shallow, horizontal, vertical.

        CUSTOM is free-form: any angle is allowed as long as it doesn't
        violate hard rules (Y-flip, bbox).
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
                            out_tangent_x=0.1,
                            out_tangent_y=0.3,  # Steep upward (3:1 ratio)
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.3,
                            in_tangent_y=-0.05,  # Shallow downward
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.2,
                            out_tangent_y=0.0,  # Horizontal
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.1,
                            in_tangent_y=0.25,  # Steep upward (pointing back-up)
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM: various angles (steep, shallow, horizontal)")

        # Steep angle
        self._assert_tangent(0, is_in_tangent=False, expected_x=0.1, expected_y=0.3, msg="Steep angle preserved")

        # Shallow angle
        self._assert_tangent(1, is_in_tangent=True, expected_x=-0.3, expected_y=-0.05, msg="Shallow angle preserved")

        # Horizontal (Y=0)
        self._assert_tangent(1, is_in_tangent=False, expected_x=0.2, expected_y=0.0, msg="Horizontal angle preserved")

        # Steep upward (in-tangent pointing up-left)
        self._assert_tangent(
            2, is_in_tangent=True, expected_x=-0.1, expected_y=0.25, msg="Steep upward in-tangent preserved"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 3: CUSTOM with vertical tangent (X=0)
    # =========================================================================
    async def test_custom_vertical_tangent(self):
        """CUSTOM allows vertical tangents (X=0, non-zero Y).

        Vertical tangents are valid for CUSTOM - no auto-reset to horizontal.
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
                            out_tangent_x=0.0,  # Vertical
                            out_tangent_y=0.2,  # Pointing up
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=0.0,  # Vertical
                            in_tangent_y=-0.15,  # Pointing down
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM: vertical tangents (X=0) allowed")

        # Vertical out-tangent
        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.0, expected_y=0.2, msg="Vertical out-tangent preserved"
        )

        # Vertical in-tangent
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=0.0, expected_y=-0.15, msg="Vertical in-tangent preserved"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 4: Y-axis flip prevention (HARD RULE)
    # =========================================================================
    async def test_custom_y_axis_flip_prevention(self):
        """CUSTOM tangents cannot flip past Y-axis.

        Hard rule: IN tangent X ≤ 0, OUT tangent X ≥ 0.
        If user provides invalid X, it's clamped to 0 (vertical).
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
                            out_tangent_x=-0.2,  # INVALID: OUT tangent pointing left
                            out_tangent_y=0.1,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=0.15,  # INVALID: IN tangent pointing right
                            in_tangent_y=-0.08,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM: Y-axis flip prevention (X clamped to 0)")

        # OUT tangent with negative X clamped to 0
        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.0, expected_y=0.1, msg="OUT tangent X clamped to 0 (was negative)"
        )

        # IN tangent with positive X clamped to 0
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=0.0, expected_y=-0.08, msg="IN tangent X clamped to 0 (was positive)"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 5: Bounding box clamping - Y exceeds bounds
    # =========================================================================
    async def test_custom_bbox_y_clamping(self):
        """CUSTOM tangent Y is clamped to curve bounds.

        When handle Y goes outside curve's value range, it's clamped.
        Ray-box intersection preserves angle during clamping.
        """
        # Curve bounds are (0.0, 1.0) for both time and value
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,  # value=0.2
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.1,
                            out_tangent_y=0.9,  # Handle at 0.2 + 0.9 = 1.1 (exceeds max 1.0)
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.7,  # Handle at 0.6 - 0.7 = -0.1 (below min 0.0)
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM: Y clamped to bbox (ray-box intersection)")

        # Key 0 OUT: Y would be at 1.1, clamped to 1.0
        # Ray-box intersection: t = (1.0 - 0.2) / 0.9 = 0.889
        # Clamped X = 0.1 * 0.889 = 0.0889, Y = 0.9 * 0.889 = 0.8 (which gives handle at Y=1.0)
        curve = self._get_curve()
        key0_out_x = curve.keys[0].out_tangent_x
        key0_out_y = curve.keys[0].out_tangent_y
        # Check Y + key_value <= bounds_max (1.0)
        handle_y = KEY_0_VALUE + key0_out_y
        self.assertLessEqual(handle_y, 1.0 + 0.001, msg="Handle Y clamped to max bound")
        # Ensure X is non-zero so angle check is meaningful
        self.assertGreater(abs(key0_out_x), 0.001, msg="X must be non-zero for angle check")
        # Angle should be preserved (original ratio: 0.9/0.1 = 9)
        ratio = key0_out_y / key0_out_x
        self.assertAlmostEqual(ratio, 9.0, delta=0.1, msg="Angle preserved during Y clamp")

        # Key 1 IN: Y would be at -0.1, clamped to 0.0
        # Ray-box intersection: t = (0.0 - 0.6) / -0.7 = 0.857
        key1_in_x = curve.keys[1].in_tangent_x
        key1_in_y = curve.keys[1].in_tangent_y
        handle_y = KEY_1_VALUE + key1_in_y
        self.assertGreaterEqual(handle_y, -0.001, msg="Handle Y clamped to min bound")
        # Ensure X is non-zero so angle check is meaningful
        self.assertGreater(abs(key1_in_x), 0.001, msg="X must be non-zero for angle check")
        # Angle should be preserved (original ratio: -0.7/-0.1 = 7)
        ratio = key1_in_y / key1_in_x
        self.assertAlmostEqual(ratio, 7.0, delta=0.1, msg="Angle preserved during Y clamp")

        await self._wait_for_continue()

    # =========================================================================
    # Test 6: Bounding box clamping - X exceeds bounds
    # =========================================================================
    async def test_custom_bbox_x_clamping(self):
        """CUSTOM tangent X is clamped to curve bounds.

        When handle X goes outside curve's time range, it's clamped.
        Ray-box intersection preserves angle during clamping.
        """
        # Curve bounds are (0.0, 1.0) for time
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.1,
                            value=0.5,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=1.5,  # Handle at 0.1 + 1.5 = 1.6 (exceeds max 1.0)
                            out_tangent_y=0.3,
                        ),
                        FCurveKey(
                            time=0.9,
                            value=0.5,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-1.2,  # Handle at 0.9 - 1.2 = -0.3 (below min 0.0)
                            in_tangent_y=0.2,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM: X clamped to bbox (ray-box intersection)")

        curve = self._get_curve()

        # Key 0 OUT: X would be at 1.6, clamped to 1.0
        key0_out_x = curve.keys[0].out_tangent_x
        key0_out_y = curve.keys[0].out_tangent_y
        handle_x = 0.1 + key0_out_x
        self.assertLessEqual(handle_x, 1.0 + 0.001, msg="Handle X clamped to max bound")
        # Ensure X is non-zero so angle check is meaningful
        self.assertGreater(abs(key0_out_x), 0.001, msg="X must be non-zero for angle check")
        # Angle preserved (original ratio: 0.3/1.5 = 0.2)
        ratio = key0_out_y / key0_out_x
        self.assertAlmostEqual(ratio, 0.2, delta=0.01, msg="Angle preserved during X clamp")

        # Key 1 IN: X would be at -0.3, clamped to 0.0
        key1_in_x = curve.keys[1].in_tangent_x
        key1_in_y = curve.keys[1].in_tangent_y
        handle_x = 0.9 + key1_in_x
        self.assertGreaterEqual(handle_x, -0.001, msg="Handle X clamped to min bound")
        # Ensure X is non-zero so angle check is meaningful
        self.assertGreater(abs(key1_in_x), 0.001, msg="X must be non-zero for angle check")
        # Angle preserved (original ratio: 0.2/-1.2 = -0.167)
        ratio = key1_in_y / key1_in_x
        self.assertAlmostEqual(ratio, -0.167, delta=0.01, msg="Angle preserved during X clamp")

        await self._wait_for_continue()

    # =========================================================================
    # Test 7: Zero tangent (X=0, Y=0) allowed
    # =========================================================================
    async def test_custom_zero_tangent(self):
        """CUSTOM allows zero tangent (X=0, Y=0).

        This creates a cusp/sharp corner at the keyframe.
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
                            out_tangent_x=0.0,
                            out_tangent_y=0.0,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=0.0,
                            in_tangent_y=0.0,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM: zero tangent (cusp/sharp corner)")

        self._assert_tangent(0, is_in_tangent=False, expected_x=0.0, expected_y=0.0, msg="Zero out-tangent preserved")
        self._assert_tangent(1, is_in_tangent=True, expected_x=0.0, expected_y=0.0, msg="Zero in-tangent preserved")

        await self._wait_for_continue()

    # =========================================================================
    # Test 8: CUSTOM drag updates tangent freely
    # =========================================================================
    async def test_drag_custom_tangent(self):
        """Dragging CUSTOM tangent updates position freely.

        The dragged position becomes the new tangent value (subject to clamping).

        Setup: Key at (0.0, 0.5) with CUSTOM tangent (0.2, 0.1).
        - Initial handle position: (0.2, 0.6) in model space
        - Drag 40px right, 28px up in screen space
        - Expected change: ~0.1 in X (40px / 400px), ~0.1 in Y (28px / 280px)
        - Final tangent: approximately (0.3, 0.2)

        Using value=0.5 to keep the handle well within bounds during drag.
        """
        initial_tangent_x = 0.2
        initial_tangent_y = 0.1
        key_value = 0.5  # Middle of range to avoid bbox clamping during drag

        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=key_value,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=initial_tangent_x,
                            out_tangent_y=initial_tangent_y,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM: drag freely updates tangent")

        # Initial value
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=initial_tangent_x,
            expected_y=initial_tangent_y,
            msg="Initial CUSTOM value",
        )

        # Select the keyframe to make tangent handles visible
        await self._select_key(0)

        await self._wait_for_continue()

        # Drag tangent - move right and up (in screen space: right = +X, up = -Y)
        # Calculate expected delta based on viewport conversion:
        # 400px width = 1.0 time range, so 40px ≈ 0.1 time
        # 280px height = 1.0 value range, so 28px ≈ 0.1 value
        drag_dx_px = 40
        drag_dy_px = -28  # Negative because screen Y is inverted
        expected_delta_x = drag_dx_px / CURVE_WIDTH  # ≈ 0.1
        expected_delta_y = -drag_dy_px / CURVE_HEIGHT  # ≈ 0.1 (negate because screen Y inverted)

        tangent_widget = self._get_tangent_widget(0, is_in_tangent=False)
        self.assertIsNotNone(tangent_widget, "Out tangent widget should exist after selection")
        await self._drag_tangent_widget(tangent_widget, dx=drag_dx_px, dy=drag_dy_px)

        # After drag, tangent should have moved by approximately the expected delta
        curve = self._get_curve()
        new_x = curve.keys[0].out_tangent_x
        new_y = curve.keys[0].out_tangent_y

        expected_x = initial_tangent_x + expected_delta_x
        expected_y = initial_tangent_y + expected_delta_y

        # Use wider delta (0.05) to account for UI interaction precision
        self.assertAlmostEqual(
            new_x, expected_x, delta=0.05, msg=f"Drag moved X from {initial_tangent_x} toward {expected_x}"
        )
        self.assertAlmostEqual(
            new_y, expected_y, delta=0.05, msg=f"Drag moved Y from {initial_tangent_y} toward {expected_y}"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 9: CUSTOM with negative Y (pointing downward)
    # =========================================================================
    async def test_custom_negative_y(self):
        """CUSTOM allows negative Y values (downward pointing tangents).

        OUT tangent can point down-right, IN tangent can point down-left.

        Using value=0.5 (middle of range) so negative Y tangents don't hit
        the lower bound (0.0) and get clamped.
        """
        key_value = 0.5  # Middle of range to avoid bbox clamping
        tangent_y = -0.15  # Small enough to stay within bounds (0.5 - 0.15 = 0.35 > 0)

        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=key_value,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.2,
                            out_tangent_y=tangent_y,  # Pointing down-right
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=key_value,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.2,
                            in_tangent_y=tangent_y,  # Pointing down-left
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM: negative Y (downward pointing) allowed")

        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.2, expected_y=tangent_y, msg="OUT tangent pointing down-right"
        )
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=-0.2, expected_y=tangent_y, msg="IN tangent pointing down-left"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 10: CUSTOM mixed with other types
    # =========================================================================
    async def test_custom_mixed_with_other_types(self):
        """CUSTOM can be mixed with other tangent types on same curve.

        Each tangent type follows its own rules independently.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.LINEAR,  # Auto-computed
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,  # User-defined
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.05,
                            out_tangent_type=TangentType.SMOOTH,  # Halfway to neighbor
                            out_tangent_x=0.1,
                            out_tangent_y=0.08,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM mixed with LINEAR and SMOOTH")

        # Key 0 OUT: LINEAR = midpoint to Key 1
        # X = (0.5 - 0.0) / 2 = 0.25, Y = (0.6 - 0.2) / 2 = 0.2
        self._assert_tangent(0, is_in_tangent=False, expected_x=0.25, expected_y=0.2, msg="LINEAR computes midpoint")

        # Key 1 IN: CUSTOM = exact value preserved
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=-0.1, expected_y=-0.05, msg="CUSTOM preserves exact value"
        )

        # Key 1 OUT: SMOOTH = constant LENGTH at halfway, angle preserved
        # Input: (0.1, 0.08), halfway = 0.25
        # input_length = sqrt(0.01 + 0.0064) = 0.1281, scale = 1.952
        # output = (0.1952, 0.1561)
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=0.1118,
            expected_y=0.0894,
            delta=0.01,
            msg="SMOOTH computes constant LENGTH at halfway",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 11: Switching TO CUSTOM from auto-computed type
    # =========================================================================
    async def test_switch_to_custom(self):
        """Switching to CUSTOM preserves the current computed value.

        When switching from an auto-computed type to CUSTOM, the current
        tangent position becomes the new CUSTOM value.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("LINEAR to CUSTOM switch")

        # Initial LINEAR: midpoint
        self._assert_tangent(0, is_in_tangent=False, expected_x=0.25, expected_y=0.2, msg="Initial LINEAR midpoint")

        await self._wait_for_continue()

        # Switch to CUSTOM
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.CUSTOM)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("After switch: CUSTOM with LINEAR's computed value")

        # After switch: same position, now CUSTOM
        # The computed value should be preserved
        curve = self._get_curve()
        self.assertEqual(curve.keys[0].out_tangent_type, TangentType.CUSTOM)
        # Value should still be at LINEAR's computed position
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=0.25,
            expected_y=0.2,
            delta=0.02,
            msg="CUSTOM preserves LINEAR's computed value",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 12: Switching FROM CUSTOM to auto-computed type
    # =========================================================================
    async def test_switch_from_custom(self):
        """Switching from CUSTOM to auto-computed type recomputes tangent.

        The CUSTOM value is replaced by the type's computed value.
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
                            out_tangent_x=0.1,  # Not at midpoint
                            out_tangent_y=0.05,  # Not at midpoint
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM to LINEAR switch")

        # Initial CUSTOM value
        self._assert_tangent(0, is_in_tangent=False, expected_x=0.1, expected_y=0.05, msg="Initial CUSTOM value")

        await self._wait_for_continue()

        # Switch to LINEAR
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.LINEAR)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("After switch: LINEAR recomputes to midpoint")

        # After switch: LINEAR computes midpoint
        curve = self._get_curve()
        self.assertEqual(curve.keys[0].out_tangent_type, TangentType.LINEAR)
        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.25, expected_y=0.2, msg="LINEAR recomputes to midpoint"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 13: CUSTOM at boundary keys (first/last)
    # =========================================================================
    async def test_custom_at_boundary_keys(self):
        """CUSTOM works at boundary keyframes (first and last).

        Boundary tangents that point "outward" (first key's IN, last key's OUT)
        are zeroed because there's no neighbor to point toward. This is consistent
        with how bezier curves work - these tangents serve no purpose.

        Boundary tangents that point "inward" (first key's OUT, last key's IN)
        preserve their CUSTOM values normally.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.CUSTOM,  # First key, no prev - zeroed
                            in_tangent_x=-0.1,
                            in_tangent_y=0.05,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.2,
                            out_tangent_y=0.15,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.2,
                            in_tangent_y=-0.1,
                            out_tangent_type=TangentType.CUSTOM,  # Last key, no next - zeroed
                            out_tangent_x=0.15,
                            out_tangent_y=0.08,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM at boundary keys")

        # Key 0 IN: first key has no previous - tangent zeroed
        self._assert_tangent(
            0, is_in_tangent=True, expected_x=0.0, expected_y=0.0, msg="First key IN zeroed (no prev neighbor)"
        )

        # Key 0 OUT: valid CUSTOM at first key (points to Key 1)
        self._assert_tangent(0, is_in_tangent=False, expected_x=0.2, expected_y=0.15, msg="First key OUT CUSTOM works")

        # Key 1 IN: valid CUSTOM at last key (points from Key 0)
        self._assert_tangent(1, is_in_tangent=True, expected_x=-0.2, expected_y=-0.1, msg="Last key IN CUSTOM works")

        # Key 1 OUT: last key has no next - tangent zeroed
        self._assert_tangent(
            1, is_in_tangent=False, expected_x=0.0, expected_y=0.0, msg="Last key OUT zeroed (no next neighbor)"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 14: CUSTOM with very small values (near zero)
    # =========================================================================
    async def test_custom_small_values(self):
        """CUSTOM handles very small tangent values correctly.

        Near-zero values should be preserved without being zeroed out.
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
                            out_tangent_x=0.001,  # Very small X
                            out_tangent_y=0.0005,  # Very small Y
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.002,
                            in_tangent_y=-0.001,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM: very small values preserved")

        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.001, expected_y=0.0005, delta=0.0001, msg="Small values preserved"
        )
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=-0.002, expected_y=-0.001, delta=0.0001, msg="Small values preserved"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 15: CUSTOM with large values (clamped to neighbor, not just bbox)
    # =========================================================================
    async def test_custom_large_values(self):
        """CUSTOM handles large tangent values by clamping to neighbor key.

        Very large X values are clamped to the neighbor keyframe's time,
        which is a tighter constraint than the curve bounds.

        Setup:
        - Key 0 at time=0.5, Key 1 at time=0.8
        - OUT tangent with X=10.0 would reach time=10.5
        - Should be clamped to neighbor at time=0.8, so X ≤ 0.3
        """
        key0_time = 0.5
        key0_value = 0.5
        key1_time = 0.8
        max_tangent_x = key1_time - key0_time  # 0.3 - the neighbor constraint

        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=key0_time,
                            value=key0_value,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=10.0,  # Way beyond neighbor
                            out_tangent_y=5.0,  # Way beyond bounds
                        ),
                        FCurveKey(
                            time=key1_time,
                            value=0.5,
                            in_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM: large values clamped to neighbor")

        curve = self._get_curve()
        key0_out_x = curve.keys[0].out_tangent_x
        key0_out_y = curve.keys[0].out_tangent_y

        # X should be clamped to neighbor (0.3), not curve bounds (1.0)
        handle_x = key0_time + key0_out_x
        self.assertLessEqual(handle_x, key1_time + 0.001, msg=f"X clamped to neighbor time ({key1_time}), not bounds")
        self.assertLessEqual(key0_out_x, max_tangent_x + 0.001, msg=f"Tangent X ≤ {max_tangent_x} (neighbor distance)")

        # Y should be clamped to curve bounds (1.0)
        handle_y = key0_value + key0_out_y
        self.assertLessEqual(handle_y, 1.0 + 0.001, msg="Y clamped to max bound")

        # Ensure X is non-zero so angle check is meaningful
        self.assertGreater(abs(key0_out_x), 0.001, msg="X must be non-zero for angle check")
        # Angle should be preserved (original ratio: 5/10 = 0.5)
        ratio = key0_out_y / key0_out_x
        self.assertAlmostEqual(ratio, 0.5, delta=0.01, msg="Angle preserved when clamping large values")

        await self._wait_for_continue()

    # =========================================================================
    # Test 16: Interactive Y-axis flip prevention (drag past Y-axis)
    # =========================================================================
    async def test_drag_past_y_axis(self):
        """Dragging CUSTOM tangent past Y-axis clamps X to 0.

        When user drags an OUT tangent to the left (past Y-axis), X is clamped
        to 0 (vertical), preserving Y. Similarly for IN tangent dragged right.

        This tests the interactive case, not just initial value clamping.
        """
        # Start with a valid tangent pointing right
        initial_x = 0.15
        initial_y = 0.1
        key_value = 0.5  # Middle of range

        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=key_value,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=initial_x,
                            out_tangent_y=initial_y,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=key_value,
                            in_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM: drag past Y-axis clamps to vertical")

        # Initial value should be valid
        self._assert_tangent(
            0, is_in_tangent=False, expected_x=initial_x, expected_y=initial_y, msg="Initial CUSTOM value"
        )

        # Select the keyframe
        await self._select_key(0)
        await self._wait_for_continue()

        # Drag far to the left (past Y-axis)
        # 200px left should move X by ~0.5, which would make it negative
        tangent_widget = self._get_tangent_widget(0, is_in_tangent=False)
        self.assertIsNotNone(tangent_widget, "Out tangent widget should exist")
        await self._drag_tangent_widget(tangent_widget, dx=-200, dy=0)

        # After drag past Y-axis, X should be clamped to 0
        curve = self._get_curve()
        self.assertGreaterEqual(curve.keys[0].out_tangent_x, 0.0, msg="OUT tangent X clamped to 0 (cannot go negative)")
        # Y should be preserved (approximately, as it may change slightly due to angle)
        self.assertAlmostEqual(
            curve.keys[0].out_tangent_y, initial_y, delta=0.15, msg="Y approximately preserved when X clamped"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 17: CUSTOM with 3 keyframes (middle key boundary behavior)
    # =========================================================================
    async def test_custom_three_keys_middle(self):
        """CUSTOM on middle keyframe has both neighbors - no zeroing.

        Unlike boundary keys where one tangent may be zeroed (no neighbor),
        middle keys should preserve both IN and OUT CUSTOM values.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.15,
                            in_tangent_y=-0.08,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.18,
                            out_tangent_y=0.12,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM on middle key: both tangents preserved")

        # Middle key IN tangent: should preserve exact value (has previous neighbor)
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=-0.15, expected_y=-0.08, msg="Middle key IN CUSTOM preserved"
        )

        # Middle key OUT tangent: should preserve exact value (has next neighbor)
        self._assert_tangent(
            1, is_in_tangent=False, expected_x=0.18, expected_y=0.12, msg="Middle key OUT CUSTOM preserved"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 18: CUSTOM tangent after keyframe time changes
    # =========================================================================
    async def test_custom_after_keyframe_time_change(self):
        """CUSTOM tangent values are preserved when keyframe time changes.

        When a keyframe is dragged horizontally (time changes), CUSTOM tangent
        values should remain unchanged - they are absolute offsets, not relative
        to neighbors.

        Note: If the new position causes the tangent to exceed the new neighbor
        distance, clamping will apply. This test uses small tangent values to
        avoid that scenario.
        """
        # Use small tangent values that won't exceed neighbor distance after drag
        initial_in_x = -0.1
        initial_in_y = -0.05
        initial_out_x = 0.1
        initial_out_y = 0.08

        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,  # time=0.5
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=initial_in_x,
                            in_tangent_y=initial_in_y,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=initial_out_x,
                            out_tangent_y=initial_out_y,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM preserved after keyframe time change")

        # Verify initial values
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=initial_in_x, expected_y=initial_in_y, msg="Initial IN tangent"
        )
        self._assert_tangent(
            1, is_in_tangent=False, expected_x=initial_out_x, expected_y=initial_out_y, msg="Initial OUT tangent"
        )

        # Select and drag keyframe horizontally (change time)
        # Drag 40px right ≈ 0.1 time units, new time ≈ 0.6
        mgr = self.widget._managers["test"]
        handle = mgr.key_handles[1]
        start_pos = ui_test.Vec2(*handle.screen_center)
        end_pos = start_pos + ui_test.Vec2(40, 0)  # Drag right only

        await ui_test.input.emulate_mouse_move(start_pos)
        await ui_test.human_delay(3)
        await ui_test.emulate_mouse_drag_and_drop(start_pos, end_pos)
        await ui_test.human_delay(3)
        await omni.kit.app.get_app().next_update_async()

        # Verify keyframe time changed
        curve = self._get_curve()
        self.assertGreater(curve.keys[1].time, KEY_1_TIME, msg="Keyframe time should have increased")

        # CUSTOM tangent values should be preserved (or only slightly changed due to clamping)
        # Using wider delta since clamping may adjust values slightly
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=initial_in_x,
            expected_y=initial_in_y,
            delta=0.02,
            msg="IN tangent preserved after time change",
        )
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=initial_out_x,
            expected_y=initial_out_y,
            delta=0.02,
            msg="OUT tangent preserved after time change",
        )

        await self._wait_for_continue()
