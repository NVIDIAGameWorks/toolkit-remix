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

E2E Tests for SMOOTH tangent behavior.

SMOOTH tangent behavior (from TANGENT_BEHAVIOR.md):
- SMOOTH is like AUTO, but the angle can be customized by the user
- Length is auto-computed so handle X reaches neighboring keyframe X
- Y is scaled proportionally to preserve angle when X changes
- Subject to Y clamping within curve bounds
- "Non-weighted" from UX perspective (user controls angle, not length)

Key difference from AUTO:
- AUTO: Both angle AND length are auto-computed from neighbors
- SMOOTH: Angle is user-defined, length is auto-computed to neighbor X

Y-axis flip prevention (applies to all tangent types):
- IN tangent X must be ≤ 0 (points left or vertical)
- OUT tangent X must be ≥ 0 (points right or vertical)
- Dragging past Y axis clamps to vertical (X=0)
"""

import math
import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
from omni import ui

from omni.flux.fcurve.widget import FCurveWidget, FCurve, FCurveKey, TangentType
from omni.flux.fcurve.widget._internal.math import Vector2, _elliptical_scale

__all__ = ["TestSmoothTangents"]


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


class TestSmoothTangents(omni.kit.test.AsyncTestCase):
    """Test SMOOTH tangent behavior: user-defined angle with auto-computed length."""

    async def setUp(self):
        """Create window with FCurveWidget."""
        self._continue_clicked = False

        self.window = ui.Window(
            "Test SMOOTH Tangents",
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

        To disable interactive debugging, uncomment the return statement
        and comment out the loop below.
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
            tangent_name = f"key[{key_index}].in_tangent"
        else:
            actual_x = key.out_tangent_x
            actual_y = key.out_tangent_y
            tangent_name = f"key[{key_index}].out_tangent"

        self.assertAlmostEqual(
            actual_x, expected_x, delta=delta, msg=f"{tangent_name} X: expected {expected_x}, got {actual_x}. {msg}"
        )
        self.assertAlmostEqual(
            actual_y, expected_y, delta=delta, msg=f"{tangent_name} Y: expected {expected_y}, got {actual_y}. {msg}"
        )

    @staticmethod
    def _smooth_tangent(handle_x, handle_y, key_time, key_value, neighbor_time, neighbor_value):
        """Expected SMOOTH tangent (elliptical scale of handle onto half-diff ellipse)."""
        half_diff = Vector2(neighbor_time - key_time, neighbor_value - key_value) / 2.0
        result = _elliptical_scale(Vector2(handle_x, handle_y), half_diff)
        return result.x, result.y

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
    # Test 1: SMOOTH with custom angle - LENGTH at HALFWAY to neighbor
    # =========================================================================
    async def test_smooth_extends_to_neighbor_x(self):
        """SMOOTH tangent LENGTH should be at HALFWAY to neighbor keyframe.

        User provides an angle via initial tangent values, SMOOTH computes
        the output with constant LENGTH = halfway_distance, preserving the angle.
        Formula: output = input * (halfway / input_length)
        """
        # Set up with SMOOTH tangents and initial angles
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,  # Initial angle (will be scaled)
                            out_tangent_y=0.15,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,  # Initial angle
                            in_tangent_y=-0.1,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.2,  # Initial angle
                            out_tangent_y=0.1,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.15,  # Initial angle
                            in_tangent_y=0.05,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("SMOOTH: LENGTH at HALFWAY to neighbor, angle preserved")

        k0_out_x, k0_out_y = self._smooth_tangent(0.1, 0.15, KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE)
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=k0_out_x,
            expected_y=k0_out_y,
            msg="Key 0 OUT: SMOOTH LENGTH at halfway to Key 1",
        )

        k1_in_x, k1_in_y = self._smooth_tangent(-0.1, -0.1, KEY_1_TIME, KEY_1_VALUE, KEY_0_TIME, KEY_0_VALUE)
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=k1_in_x,
            expected_y=k1_in_y,
            msg="Key 1 IN: SMOOTH LENGTH at halfway to Key 0",
        )

        k1_out_x, k1_out_y = self._smooth_tangent(0.2, 0.1, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE)
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=k1_out_x,
            expected_y=k1_out_y,
            msg="Key 1 OUT: SMOOTH LENGTH at halfway to Key 2",
        )

        k2_in_x, k2_in_y = self._smooth_tangent(-0.15, 0.05, KEY_2_TIME, KEY_2_VALUE, KEY_1_TIME, KEY_1_VALUE)
        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=k2_in_x,
            expected_y=k2_in_y,
            delta=0.01,
            msg="Key 2 IN: SMOOTH LENGTH at halfway to Key 1",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 2: SMOOTH with horizontal angle (Y=0)
    # =========================================================================
    async def test_smooth_horizontal_angle(self):
        """SMOOTH with horizontal angle (Y=0) - X at halfway, Y stays 0."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.0,  # Horizontal
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=0.0,  # Horizontal
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("SMOOTH horizontal (Y=0) - X at halfway")

        # X at halfway to neighbor, Y stays 0
        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="Key 0 OUT: SMOOTH horizontal, X at halfway"
        )
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=-0.25, expected_y=0.0, msg="Key 1 IN: SMOOTH horizontal, X at halfway"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 3: SMOOTH with zero X (vertical) - stays vertical with LENGTH at halfway
    # =========================================================================
    async def test_smooth_zero_x_stays_vertical(self):
        """SMOOTH with X=0 (vertical tangent) stays vertical, LENGTH at halfway.

        When user sets X=0, SMOOTH respects this as a vertical tangent.
        The LENGTH is normalized to halfway distance, so Y = ±halfway.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.0,  # Vertical
                            out_tangent_y=0.5,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=0.0,  # Vertical
                            in_tangent_y=-0.3,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("SMOOTH with X=0 stays vertical, LENGTH at halfway")

        # When X=0, SMOOTH keeps vertical tangent but LENGTH = halfway (0.25)
        # Input (0, 0.5) → length=0.5, scale=0.25/0.5=0.5 → output (0, 0.25)
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=0.0,
            expected_y=0.2,
            msg="Key 0 OUT: SMOOTH X=0 stays vertical, Y=0.2 (halfway)",
        )
        # Input (0, -0.3) → length=0.3, scale=0.25/0.3=0.833 → output (0, -0.25)
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=0.0,
            expected_y=-0.2,
            msg="Key 1 IN: SMOOTH X=0 stays vertical, Y=-0.2 (halfway)",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 4: SMOOTH paired with LINEAR
    # =========================================================================
    async def test_smooth_paired_with_linear(self):
        """SMOOTH tangent paired with LINEAR tangent."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.1,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.LINEAR,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=0.1,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("SMOOTH(0).out -> LINEAR(1) -> SMOOTH(2).in")

        # Key 0 SMOOTH out: input (0.1, 0.1), halfway = 0.25
        # input_length = sqrt(0.02) = 0.1414, scale = 1.768, output = (0.1768, 0.1768)
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=0.1562,
            expected_y=0.1562,
            msg="Key 0 OUT: SMOOTH LENGTH at halfway to Key 1",
        )

        # Key 1 LINEAR: midpoints (unchanged)
        self._assert_tangent(1, is_in_tangent=True, expected_x=-0.25, expected_y=-0.2, msg="Key 1 IN: LINEAR midpoint")
        self._assert_tangent(1, is_in_tangent=False, expected_x=0.25, expected_y=-0.1, msg="Key 1 OUT: LINEAR midpoint")

        k2_in_x, k2_in_y = self._smooth_tangent(-0.1, 0.1, KEY_2_TIME, KEY_2_VALUE, KEY_1_TIME, KEY_1_VALUE)
        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=k2_in_x,
            expected_y=k2_in_y,
            msg="Key 2 IN: SMOOTH LENGTH at halfway to Key 1",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 5: SMOOTH paired with FLAT
    # =========================================================================
    async def test_smooth_paired_with_flat(self):
        """SMOOTH tangent paired with FLAT tangent."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.FLAT,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.1,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.05,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.FLAT,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("FLAT(0).out -> SMOOTH(1) -> FLAT(2).in")

        # Key 0 FLAT out: horizontal to Key 1 (FLAT uses full distance)
        self._assert_tangent(0, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="Key 0 OUT: FLAT horizontal")

        # Key 1 SMOOTH: LENGTH at halfway to neighbors
        # IN: input (-0.1, -0.1), length=0.1414, scale=1.768, output=(-0.1768, -0.1768)
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=-0.1562,
            expected_y=-0.1562,
            msg="Key 1 IN: SMOOTH LENGTH at halfway to Key 0",
        )
        # OUT: input (0.1, 0.05), elliptical_scale onto half_diff to Key2
        k1_out_x, k1_out_y = self._smooth_tangent(0.1, 0.05, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE)
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=k1_out_x,
            expected_y=k1_out_y,
            msg="Key 1 OUT: SMOOTH LENGTH at halfway to Key 2",
        )

        # Key 2 FLAT in: horizontal from Key 1
        self._assert_tangent(2, is_in_tangent=True, expected_x=-0.25, expected_y=0.0, msg="Key 2 IN: FLAT horizontal")

        await self._wait_for_continue()

    # =========================================================================
    # Test 6: SMOOTH paired with AUTO
    # =========================================================================
    async def test_smooth_paired_with_auto(self):
        """SMOOTH tangent paired with AUTO tangent."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.1,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.05,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("SMOOTH(0).out -> AUTO(1) -> SMOOTH(2).in")

        # Key 0 SMOOTH out: input (0.1, 0.1), halfway = 0.25
        # input_length = 0.1414, scale = 1.768, output = (0.1768, 0.1768)
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=0.1562,
            expected_y=0.1562,
            msg="Key 0 OUT: SMOOTH LENGTH at halfway to Key 1",
        )

        neighbor_dir = Vector2(KEY_2_TIME - KEY_0_TIME, KEY_2_VALUE - KEY_0_VALUE)
        auto_in = -_elliptical_scale(neighbor_dir, Vector2(KEY_0_TIME - KEY_1_TIME, KEY_0_VALUE - KEY_1_VALUE) / 2.0)
        auto_out = _elliptical_scale(neighbor_dir, Vector2(KEY_2_TIME - KEY_1_TIME, KEY_2_VALUE - KEY_1_VALUE) / 2.0)

        self._assert_tangent(
            1, is_in_tangent=True, expected_x=auto_in.x, expected_y=auto_in.y, msg="Key 1 IN: AUTO unchanged"
        )
        self._assert_tangent(
            1, is_in_tangent=False, expected_x=auto_out.x, expected_y=auto_out.y, msg="Key 1 OUT: AUTO unchanged"
        )

        k2_in_x, k2_in_y = self._smooth_tangent(-0.1, -0.05, KEY_2_TIME, KEY_2_VALUE, KEY_1_TIME, KEY_1_VALUE)
        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=k2_in_x,
            expected_y=k2_in_y,
            msg="Key 2 IN: SMOOTH LENGTH at halfway to Key 1",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 6b: SMOOTH paired with STEP
    # =========================================================================
    async def test_smooth_paired_with_step(self):
        """SMOOTH tangent paired with STEP tangent.

        STEP tangents create instant value changes - the curve holds constant
        until the next keyframe, then jumps. SMOOTH tangents use X at halfway.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.08,  # Angle to test scaling
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.STEP,
                            out_tangent_type=TangentType.STEP,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=0.05,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("SMOOTH(0).out -> STEP(1) -> SMOOTH(2).in")

        # Key 0 SMOOTH out: input (0.1, 0.08), halfway = 0.25
        # input_length = sqrt(0.01 + 0.0064) = 0.1281, scale = 1.952
        # output = (0.1952, 0.1561)
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=0.1768,
            expected_y=0.1414,
            msg="Key 0 OUT: SMOOTH LENGTH at halfway to Key 1 (STEP)",
        )

        # Key 1 STEP: OUT tangent is (0,0), IN tangent falls back to LINEAR
        # STEP as in-tangent falls back to LINEAR (documented behavior)
        # LINEAR in-tangent: X = -0.25, Y = -0.2
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=-0.25, expected_y=-0.2, msg="Key 1 IN: STEP falls back to LINEAR midpoint"
        )
        self._assert_tangent(
            1, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="Key 1 OUT: STEP has zero tangent"
        )

        # Key 2 SMOOTH in: input (-0.1, 0.05), halfway = 0.25
        # input_length = sqrt(0.01 + 0.0025) = 0.1118, scale = 2.236
        # output = (-0.2236, 0.1118)
        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=-0.25,
            expected_y=0.0,
            msg="Key 2 IN: SMOOTH LENGTH at halfway to Key 1 (STEP)",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 7: SMOOTH angle changes during drag while LENGTH stays constant
    # =========================================================================
    async def test_smooth_y_clamping_during_drag(self):
        """SMOOTH tangent angle changes during drag while LENGTH stays at halfway.

        When dragging a SMOOTH tangent, the angle changes but length stays constant
        at halfway distance to neighbor. Clamping may apply if handle exceeds bounds.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.2,
                            value=0.5,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.3,
                            out_tangent_y=0.1,  # Slight upward angle
                        ),
                        FCurveKey(
                            time=0.8,
                            value=0.5,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.3,
                            in_tangent_y=0.1,  # Slight upward angle
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("SMOOTH tangent: drag changes angle, LENGTH constant at 0.3")

        # Select key 0 to show tangent handles (widgets only exist after selection)
        await self._select_key(0)

        out_tangent = self._get_tangent_widget(0, is_in_tangent=False)
        self.assertIsNotNone(out_tangent, "Key 0 should have OUT tangent widget for SMOOTH")

        # Drag tangent far up - angle becomes steeper
        await self._drag_tangent_widget(out_tangent, dx=0, dy=-200)

        curve = self._get_curve()

        # With constant LENGTH = 0.3, dragging up makes angle steeper
        # Nearly vertical tangent: X small, Y ≈ 0.3 (but may be clamped)
        # Handle position = 0.5 + Y, so handle at 0.5 + 0.3 = 0.8 (within bounds, no clamping)
        tangent_length = math.sqrt(curve.keys[0].out_tangent_x ** 2 + curve.keys[0].out_tangent_y ** 2)
        self.assertGreater(tangent_length, 0.01, msg="SMOOTH tangent should have non-trivial length")

        await self._wait_for_continue()

    # =========================================================================
    # Test 8: Y-axis flip prevention - IN tangent cannot point right (drag test)
    # =========================================================================
    async def test_yaxis_flip_prevention_in_tangent(self):
        """IN tangent cannot flip past Y axis (X must be ≤ 0).

        When user drags IN tangent past the keyframe's Y axis:
        1. HARD rules clamp X to 0 (vertical)
        2. SMOOTH keeps the vertical tangent (X=0) with Y preserved
        3. Internal rules clamp Y to bbox if needed

        The tangent stays vertical, not reset to horizontal.
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
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.2,  # Start with valid negative X
                            in_tangent_y=0.1,  # Start with non-zero Y
                            out_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Y-axis flip: drag IN tangent past keyframe")

        # Initial SMOOTH computed tangent: input (-0.2, 0.1), halfway = 0.25
        # input_length = sqrt(0.04 + 0.01) = 0.2236, scale = 0.25/0.2236 = 1.118
        # output = (-0.2236, 0.1118)
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=-0.2120,
            expected_y=0.106,
            msg="Initial: SMOOTH LENGTH at halfway to neighbor",
        )

        # Select key 1 to show tangent handles (widgets only exist after selection)
        await self._select_key(1)

        in_tangent = self._get_tangent_widget(1, is_in_tangent=True)
        self.assertIsNotNone(in_tangent, "Key 1 should have IN tangent widget for SMOOTH")

        # Drag IN tangent to the RIGHT (past the keyframe)
        # HARD rules clamp X to 0, SMOOTH keeps vertical with Y preserved
        await self._drag_tangent_widget(in_tangent, dx=200, dy=0)

        curve = self._get_curve()

        # Tangent stays vertical (X=0), Y preserved from drag
        # The Y value comes from the drag position clamped by bbox
        self.assertAlmostEqual(curve.keys[1].in_tangent_x, -0.0026, delta=0.001, msg="IN tangent X clamped to 0")
        # Y is preserved from the drag - should be non-zero
        self.assertNotEqual(curve.keys[1].in_tangent_y, 0.0, msg="IN tangent Y preserved (not reset to horizontal)")

        await self._wait_for_continue()

    # =========================================================================
    # Test 9: Y-axis flip prevention - OUT tangent cannot point left (drag test)
    # =========================================================================
    async def test_yaxis_flip_prevention_out_tangent(self):
        """OUT tangent cannot flip past Y axis (X must be ≥ 0).

        When user drags OUT tangent past the keyframe's Y axis:
        1. HARD rules clamp X to 0 (vertical)
        2. SMOOTH keeps the vertical tangent (X=0) with Y preserved
        3. Internal rules clamp Y to bbox if needed

        The tangent stays vertical, not reset to horizontal.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.2,  # Start with valid positive X
                            out_tangent_y=0.1,  # Start with non-zero Y
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
        self._set_label("Y-axis flip: drag OUT tangent past keyframe")

        # Initial SMOOTH computed tangent (constant LENGTH = 0.25 halfway to neighbor):
        # Input: (0.2, 0.1), input_length = sqrt(0.2² + 0.1²) ≈ 0.2236
        # Unit vector: (0.8944, 0.4472), scaled to length 0.25: (0.2236, 0.1118)
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=0.2120,
            expected_y=0.106,
            msg="Initial: SMOOTH LENGTH at halfway to neighbor",
        )

        # Select key 0 to show tangent handles (widgets only exist after selection)
        await self._select_key(0)

        out_tangent = self._get_tangent_widget(0, is_in_tangent=False)
        self.assertIsNotNone(out_tangent, "Key 0 should have OUT tangent widget for SMOOTH")

        # Drag OUT tangent to the LEFT (past the keyframe)
        # HARD rules clamp X to 0, SMOOTH keeps vertical with Y preserved
        await self._drag_tangent_widget(out_tangent, dx=-200, dy=0)

        curve = self._get_curve()

        # Tangent stays vertical (X~=0.0026), Y preserved from drag
        # The Y value comes from the drag position clamped by bbox
        self.assertAlmostEqual(
            curve.keys[0].out_tangent_x, 0.0026, delta=0.001, msg="OUT tangent X clamped to 0 (vertical)"
        )
        # Y is preserved from the drag - should be non-zero
        self.assertNotEqual(curve.keys[0].out_tangent_y, 0.0, msg="OUT tangent Y preserved (not reset to horizontal)")

        await self._wait_for_continue()

    # =========================================================================
    # Test 10: Drag SMOOTH tangent to change angle - X ALWAYS at halfway to neighbor
    # =========================================================================
    async def test_drag_smooth_tangent_changes_angle(self):
        """Dragging SMOOTH tangent changes angle while X ALWAYS stays at HALFWAY distance.

        This is the KEY behavior of SMOOTH tangents: the user controls the angle,
        but the length (X component) is auto-computed to be HALFWAY to neighbor.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.05,  # Start with small positive angle
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=0.0,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Drag SMOOTH tangent: LENGTH ALWAYS at halfway distance")

        # Initial: SMOOTH computes constant LENGTH at halfway (0.25)
        # input (0.1, 0.05), length = 0.1118, scale = 2.236
        # output = (0.2236, 0.1118)
        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.2120, expected_y=0.106, msg="Initial: Key 0 OUT LENGTH at halfway"
        )

        # Select key 0 to show tangent handles (widgets only exist after selection)
        await self._select_key(0)

        out_tangent = self._get_tangent_widget(0, is_in_tangent=False)
        self.assertIsNotNone(out_tangent, "Key 0 should have OUT tangent widget for SMOOTH")

        offset_before = out_tangent.position

        # Drag the out tangent upward (negative Y in pixels = positive Y in model space)
        # Using moderate drag to change angle without hitting bounds
        await self._drag_tangent_widget(out_tangent, dx=0, dy=-30)

        # After drag: LENGTH MUST still be at halfway (0.25), angle changes
        offset_after = out_tangent.position
        curve = self._get_curve()

        # Verify the tangent actually moved
        self.assertNotEqual(offset_before, offset_after, "Tangent should have moved after drag")

        # KEY ASSERTION: LENGTH must ALWAYS be 0.25 (halfway) for SMOOTH tangents
        tangent_length = math.sqrt(curve.keys[0].out_tangent_x ** 2 + curve.keys[0].out_tangent_y ** 2)
        self.assertGreater(
            tangent_length,
            0.05,
            msg="SMOOTH tangent should have non-trivial length after drag",
        )

        # Y should have increased (we dragged up)
        self.assertGreater(
            curve.keys[0].out_tangent_y, 0.1118, msg="Tangent Y should have increased after dragging upward"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 11: Switch from LINEAR to SMOOTH - angle preserved, length normalized
    # =========================================================================
    async def test_switch_linear_to_smooth(self):
        """Switching from LINEAR to SMOOTH - angle preserved, length normalized to halfway."""
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
        self._set_label("LINEAR(0).out -> SMOOTH (switching...)")

        # Initial LINEAR: midpoint (0.25, 0.2)
        self._assert_tangent(0, is_in_tangent=False, expected_x=0.25, expected_y=0.2, msg="Initial LINEAR: midpoint")

        await self._wait_for_continue()

        # Switch to SMOOTH
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.SMOOTH)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("SMOOTH(0).out: LENGTH at halfway, angle from LINEAR preserved")

        # SMOOTH normalizes LENGTH to halfway (0.25), preserving angle
        # LINEAR input: (0.25, 0.2), length = 0.3202, scale = 0.25/0.3202 = 0.7806
        # output = (0.1952, 0.1561)
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=0.1768,
            expected_y=0.1414,
            msg="SMOOTH: LENGTH at halfway, angle from LINEAR preserved",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 12a: Two keyframes with SMOOTH (within bounds)
    # =========================================================================
    async def test_two_keys_both_smooth(self):
        """Two keyframes with SMOOTH tangents facing each other, within bounds."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.2,
                            value=0.5,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.05,
                        ),
                        FCurveKey(
                            time=0.8,
                            value=0.5,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.05,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Two keys: SMOOTH(0).out -> SMOOTH(1).in (within bounds)")

        # Key 0 OUT: input (0.1, 0.05), halfway = 0.3
        # input_length = sqrt(0.01 + 0.0025) = 0.1118, scale = 0.3/0.1118 = 2.683
        # output = (0.2683, 0.1342)
        k0_out_x, k0_out_y = self._smooth_tangent(0.1, 0.05, 0.2, 0.5, 0.8, 0.5)
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=k0_out_x,
            expected_y=k0_out_y,
            msg="Key 0 OUT: SMOOTH LENGTH=0.3 (halfway)",
        )

        k1_in_x, k1_in_y = self._smooth_tangent(-0.1, -0.05, 0.8, 0.5, 0.2, 0.5)
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=k1_in_x, expected_y=k1_in_y, msg="Key 1 IN: SMOOTH LENGTH=0.3 (halfway)"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 12b: Two keyframes with SMOOTH (constant LENGTH)
    # =========================================================================
    async def test_two_keys_smooth_clamped_by_bounds(self):
        """Two keyframes with SMOOTH tangents - constant LENGTH at halfway.

        SMOOTH tangents have constant LENGTH = halfway distance.
        Clamping may still apply if handle position exceeds curve bounds.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.2,
                            value=0.3,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.15,
                        ),
                        FCurveKey(
                            time=0.8,
                            value=0.7,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.1,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Two keys: SMOOTH LENGTH=0.3 (halfway)")

        # Key 0 OUT: input (0.1, 0.15), halfway = 0.3
        # input_length = sqrt(0.01 + 0.0225) = 0.1803, scale = 0.3/0.1803 = 1.664
        # output = (0.1664, 0.2496)
        k0_out_x, k0_out_y = self._smooth_tangent(0.1, 0.15, 0.2, 0.3, 0.8, 0.7)
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=k0_out_x,
            expected_y=k0_out_y,
            msg="Key 0 OUT: SMOOTH LENGTH=0.3 (halfway)",
        )

        k1_in_x, k1_in_y = self._smooth_tangent(-0.1, -0.1, 0.8, 0.7, 0.2, 0.3)
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=k1_in_x, expected_y=k1_in_y, msg="Key 1 IN: SMOOTH LENGTH=0.3 (halfway)"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 13: All SMOOTH tangents (3 keys)
    # =========================================================================
    async def test_all_smooth_tangents(self):
        """All keyframes with SMOOTH tangents at various angles."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=0.0,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.1,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.05,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=-0.08,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=0.02,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.0,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("All SMOOTH: various angles, LENGTH at halfway to neighbors")

        # Key 0: no prev neighbor for IN, OUT at halfway to Key 1
        # OUT: input (0.1, 0.1), halfway=0.25, length=0.1414, scale=1.768
        # output = (0.1768, 0.1768)
        self._assert_tangent(
            0, is_in_tangent=True, expected_x=0.0, expected_y=0.0, msg="Key 0 IN: no previous neighbor"
        )
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=0.1562,
            expected_y=0.1562,
            msg="Key 0 OUT: SMOOTH LENGTH at halfway to Key 1",
        )

        # Key 1: both at halfway to neighbors
        # IN: input (-0.1, -0.05), halfway=0.25, length=0.1118, scale=2.236
        # output = (-0.2236, -0.1118)
        # OUT: input (0.1, -0.08), halfway=0.25, length=0.1281, scale=1.952
        # output = (0.1952, -0.1561)
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=-0.2120,
            expected_y=-0.106,
            msg="Key 1 IN: SMOOTH LENGTH at halfway to Key 0",
        )
        k1_out_x, k1_out_y = self._smooth_tangent(0.1, -0.08, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE)
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=k1_out_x,
            expected_y=k1_out_y,
            msg="Key 1 OUT: SMOOTH LENGTH at halfway to Key 2",
        )

        k2_in_x, k2_in_y = self._smooth_tangent(-0.1, 0.02, KEY_2_TIME, KEY_2_VALUE, KEY_1_TIME, KEY_1_VALUE)
        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=k2_in_x,
            expected_y=k2_in_y,
            msg="Key 2 IN: SMOOTH LENGTH at halfway to Key 1",
        )
        self._assert_tangent(2, is_in_tangent=False, expected_x=0.0, expected_y=0.0, msg="Key 2 OUT: no next neighbor")

        await self._wait_for_continue()

    # =========================================================================
    # Test 14: Dragging keyframe recomputes SMOOTH tangent X to new neighbor
    # =========================================================================
    async def _drag_keyframe(self, key_index: int, dx: float, dy: float):
        """Drag a keyframe by the given delta in pixels."""
        mgr = self.widget._managers["test"]
        handle = mgr.key_handles[key_index]
        start_pos = ui_test.Vec2(*handle.screen_center)
        end_pos = start_pos + ui_test.Vec2(dx, dy)

        await ui_test.input.emulate_mouse_move(start_pos)
        await ui_test.human_delay(3)
        await ui_test.emulate_mouse_drag_and_drop(start_pos, end_pos)
        await ui_test.human_delay(3)
        await omni.kit.app.get_app().next_update_async()

    async def test_drag_keyframe_smooth_recomputes(self):
        """Moving a keyframe causes adjacent SMOOTH tangents to recompute X.

        SMOOTH tangents use X at halfway to neighbor keyframe position.
        When a keyframe moves, the neighbor distance changes, so SMOOTH tangents
        must recompute their X (and scale Y proportionally) to maintain this behavior.
        """
        # Set up 3 keys with SMOOTH tangents in the middle key
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.2,
                            value=0.3,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.05,
                        ),
                        FCurveKey(
                            time=0.5,
                            value=0.5,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.05,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.04,
                        ),
                        FCurveKey(
                            time=0.8,
                            value=0.6,
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.03,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Drag keyframe: SMOOTH tangents recompute LENGTH at halfway to new distance")

        # Initial distances: Key0-Key1 = 0.3, Key1-Key2 = 0.3
        # Halfway = 0.15 for both

        # Key 0 OUT: input (0.1, 0.05), halfway=0.15
        # input_length = sqrt(0.01 + 0.0025) = 0.1118, scale = 0.15/0.1118 = 1.342
        # output = (0.1342, 0.0671)
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=0.12,
            expected_y=0.06,
            msg="Initial: Key 0 OUT LENGTH at halfway (0.15)",
        )

        k1_in_x, k1_in_y = self._smooth_tangent(-0.1, -0.05, 0.5, 0.5, 0.2, 0.3)
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=k1_in_x,
            expected_y=k1_in_y,
            msg="Initial: Key 1 IN LENGTH at halfway (0.15)",
        )

        k1_out_x, k1_out_y = self._smooth_tangent(0.1, 0.04, 0.5, 0.5, 0.8, 0.7)
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=k1_out_x,
            expected_y=k1_out_y,
            delta=0.04,
            msg="Initial: Key 1 OUT LENGTH at halfway (0.15)",
        )

        k2_in_x, k2_in_y = self._smooth_tangent(-0.1, -0.03, 0.8, 0.7, 0.5, 0.5)
        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=k2_in_x,
            expected_y=k2_in_y,
            delta=0.04,
            msg="Initial: Key 2 IN LENGTH at halfway (0.15)",
        )

        await self._wait_for_continue()

        # Drag Key 1 to the right (increase its time)
        # This changes: Key0-Key1 distance increases, Key1-Key2 distance decreases
        # Moving by 40 pixels right ≈ 0.1 in time (400px = 1.0 time)
        await self._drag_keyframe(1, dx=40, dy=0)

        # After drag, Key 1 is at approximately time=0.6 (was 0.5)
        curve = self._get_curve()

        # SMOOTH tangents preserve ANGLE, change LENGTH to new halfway

        new_k1_value = curve.keys[1].value
        expected_k0_out_x, expected_k0_out_y = self._smooth_tangent(0.1, 0.05, 0.2, 0.3, 0.5, new_k1_value)
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=expected_k0_out_x,
            expected_y=expected_k0_out_y,
            delta=0.04,
            msg="After drag: Key 0 OUT LENGTH at halfway to new Key 1",
        )

        # Key 1 IN: input direction (-0.1, -0.05), normalized = (-0.8944, -0.4472)
        expected_k1_in_x, expected_k1_in_y = self._smooth_tangent(-0.1, -0.05, 0.5, new_k1_value, 0.2, 0.3)
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=expected_k1_in_x,
            expected_y=expected_k1_in_y,
            delta=0.04,
            msg="After drag: Key 1 IN LENGTH at halfway to new Key 0",
        )

        expected_k1_out_x, expected_k1_out_y = self._smooth_tangent(0.1, 0.04, 0.5, new_k1_value, 0.8, 0.7)
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=expected_k1_out_x,
            expected_y=expected_k1_out_y,
            delta=0.06,
            msg="After drag: Key 1 OUT LENGTH at halfway to new Key 2",
        )

        expected_k2_in_x, expected_k2_in_y = self._smooth_tangent(-0.1, -0.03, 0.8, 0.7, 0.5, new_k1_value)
        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=expected_k2_in_x,
            expected_y=expected_k2_in_y,
            delta=0.06,
            msg="After drag: Key 2 IN LENGTH at halfway to new Key 1",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 15: Switch FROM SMOOTH to LINEAR
    # =========================================================================
    async def test_switch_smooth_to_linear(self):
        """Switching from SMOOTH to LINEAR - both use halfway length, but SMOOTH preserves angle.

        LINEAR tangent = midpoint to neighbor.
        SMOOTH tangent = LENGTH at halfway, angle from user input.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.15,  # Steep angle
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
        self._set_label("SMOOTH(0).out switching to LINEAR...")

        # Initial SMOOTH: input (0.1, 0.15), halfway=0.25
        # input_length = sqrt(0.01 + 0.0225) = 0.1803, scale = 0.25/0.1803 = 1.387
        # output = (0.1387, 0.2080)
        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.1176, expected_y=0.1764, msg="Initial SMOOTH: LENGTH=0.25 (halfway)"
        )

        await self._wait_for_continue()

        # Switch to LINEAR
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.LINEAR)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("LINEAR(0).out: midpoint to Key 1")

        # LINEAR computes midpoint to neighbor
        # X = (KEY_1_TIME - KEY_0_TIME) / 2 = 0.25
        # Y = (KEY_1_VALUE - KEY_0_VALUE) / 2 = (0.6 - 0.2) / 2 = 0.2
        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.25, expected_y=0.2, msg="After switch to LINEAR: midpoint (0.25, 0.2)"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 16: Switch FROM SMOOTH to FLAT
    # =========================================================================
    async def test_switch_smooth_to_flat(self):
        """Switching from SMOOTH to FLAT makes tangent horizontal.

        FLAT tangent has Y=0, X extends to full neighbor distance.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.15,
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
        self._set_label("SMOOTH(0).out switching to FLAT...")

        # Initial SMOOTH: input (0.1, 0.15), halfway=0.25
        # input_length = 0.1803, scale = 1.387
        # output = (0.1387, 0.2080)
        self._assert_tangent(0, is_in_tangent=False, expected_x=0.1176, expected_y=0.1764, msg="Initial SMOOTH")

        await self._wait_for_continue()

        # Switch to FLAT
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.FLAT)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("FLAT(0).out: horizontal to Key 1")

        # FLAT: X extends to neighbor (0.5), Y=0
        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="After switch to FLAT: (0.5, 0.0)"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 17: Switch FROM SMOOTH to AUTO
    # =========================================================================
    async def test_switch_smooth_to_auto(self):
        """Switching from SMOOTH to AUTO recomputes angle from neighbors.

        AUTO computes angle from slope between prev and next keys.
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
                            in_tangent_type=TangentType.SMOOTH,
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.2,  # Steep downward angle
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.2,  # Steep upward angle
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
        self._set_label("SMOOTH(1) switching to AUTO...")

        # Initial SMOOTH: X at halfway with user-defined angles
        # IN: X=-0.25 (halfway), Y=-0.2*(-0.25/-0.1) = -0.5, clamped by bounds
        # OUT: X=0.25 (halfway), Y=0.2*(0.25/0.1) = 0.5, clamped by bounds

        await self._wait_for_continue()

        # Switch to AUTO
        self.widget.set_key_tangent_type("test", 1, in_tangent_type=TangentType.AUTO, out_tangent_type=TangentType.AUTO)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("AUTO(1): angle computed from Key0 -> Key2 slope")

        neighbor_dir = Vector2(KEY_2_TIME - KEY_0_TIME, KEY_2_VALUE - KEY_0_VALUE)
        auto_in = -_elliptical_scale(neighbor_dir, Vector2(KEY_0_TIME - KEY_1_TIME, KEY_0_VALUE - KEY_1_VALUE) / 2.0)
        auto_out = _elliptical_scale(neighbor_dir, Vector2(KEY_2_TIME - KEY_1_TIME, KEY_2_VALUE - KEY_1_VALUE) / 2.0)

        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=auto_in.x,
            expected_y=auto_in.y,
            msg="After switch to AUTO: computed from slope",
        )
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=auto_out.x,
            expected_y=auto_out.y,
            msg="After switch to AUTO: computed from slope",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 18: Switch FROM SMOOTH to STEP
    # =========================================================================
    async def test_switch_smooth_to_step(self):
        """Switching from SMOOTH to STEP zeros out tangents.

        STEP tangents are (0, 0) - instant value change.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.SMOOTH,
                            out_tangent_x=0.1,
                            out_tangent_y=0.1,
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
        self._set_label("SMOOTH(0).out switching to STEP...")

        # Initial SMOOTH: input (0.1, 0.1), halfway=0.25
        # input_length = 0.1414, scale = 1.768
        # output = (0.1768, 0.1768)
        self._assert_tangent(0, is_in_tangent=False, expected_x=0.1562, expected_y=0.1562, msg="Initial SMOOTH")

        await self._wait_for_continue()

        # Switch to STEP
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.STEP)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("STEP(0).out: zero tangent")

        # STEP: tangent is (0, 0)
        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="After switch to STEP: (0, 0)"
        )

        await self._wait_for_continue()
