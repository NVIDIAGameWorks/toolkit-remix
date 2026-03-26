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

E2E Tests for AUTO tangent behavior.

AUTO tangent behavior (from TANGENT_BEHAVIOR.md):
- AUTO only applies to non-boundary keyframes (keyframes with neighbors on both sides)
- At boundaries (first/last key), AUTO falls back to LINEAR (midpoint to neighbor)
- For middle keys, tangent is parallel to the line connecting prev and next keys
- Handle X is clamped to midpoint between this key and neighbor (half the distance)
- This ensures handles don't exceed adjacent keyframe's position

Key formulas for middle keys (see math.py compute_tangents):
- Direction follows the line connecting prev and next neighbors (Catmull-Rom)
- Magnitude is elliptically scaled per-axis by the half-distance to the neighbor key
- _elliptical_scale(direction, semi_axes) projects direction onto an ellipse whose
  semi-axes are (|prev_diff.x|/2, |prev_diff.y|/2) for in, (|next_diff.x|/2, |next_diff.y|/2) for out
"""

import asyncio  # noqa: F401 - kept for interactive debugging in _wait_for_continue
import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
from omni import ui

from omni.flux.fcurve.widget import FCurveWidget, FCurve, FCurveKey, TangentType
from omni.flux.fcurve.widget._internal.math import Vector2, _elliptical_scale

__all__ = ["TestAutoTangents"]


# Test keyframe positions (3 keyframes for AUTO testing)
# These positions create a clear slope for AUTO tangent computation
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


class TestAutoTangents(omni.kit.test.AsyncTestCase):
    """Test AUTO tangent behavior, boundary fallback to LINEAR, and recomputation on drag."""

    async def setUp(self):
        """Create window with FCurveWidget."""
        self._continue_clicked = False

        self.window = ui.Window(
            "Test AUTO Tangents",
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
        await self._wait_for_continue()  # Wait for button click before cleanup
        if self.widget:
            self.widget.destroy()
            self.widget = None
        if self.window:
            self.window.destroy()
            self.window = None

    def _get_curve(self, curve_id: str = "test"):
        """Get the FCurve model data."""
        return self.widget.curves.get(curve_id)

    @staticmethod
    def _auto_tangent(prev_time, prev_value, key_time, key_value, next_time, next_value, is_in):
        """Expected AUTO tangent for a middle key (elliptical scale of neighbor direction)."""
        neighbor_dir = Vector2(next_time - prev_time, next_value - prev_value)
        if is_in:
            half_diff = Vector2(prev_time - key_time, prev_value - key_value) / 2.0
            tangent = -_elliptical_scale(neighbor_dir, half_diff)
        else:
            half_diff = Vector2(next_time - key_time, next_value - key_value) / 2.0
            tangent = _elliptical_scale(neighbor_dir, half_diff)
        return tangent.x, tangent.y

    @staticmethod
    def _linear_tangent(key_time, key_value, neighbor_time, neighbor_value):
        """Expected LINEAR tangent = midpoint to neighbor. Also used for AUTO at boundaries."""
        return (neighbor_time - key_time) / 2, (neighbor_value - key_value) / 2

    def _assert_tangent(
        self,
        key_index: int,
        is_in_tangent: bool,
        expected_x: float,
        expected_y: float,
        delta: float = 0.005,
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

    async def _drag_key(self, key_index: int, dx: float, dy: float):
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

    # =========================================================================
    # Test 1: All AUTO tangents (boundary keys fall back to LINEAR)
    # =========================================================================
    async def test_all_auto_tangents(self):
        """All keyframes with AUTO tangents.

        - Key 0 (first): AUTO falls back to LINEAR - out tangent at midpoint to Key 1
        - Key 1 (middle): AUTO computes tangent parallel to Key0->Key2 slope
        - Key 2 (last): AUTO falls back to LINEAR - in tangent at midpoint from Key 1
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
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
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("All AUTO: AUTO(0) -> AUTO(1) -> AUTO(2)")

        k0_out_x, k0_out_y = self._linear_tangent(KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE)
        k1_auto_in_x, k1_auto_in_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=True
        )
        k1_auto_out_x, k1_auto_out_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=False
        )
        k2_in_x, k2_in_y = self._linear_tangent(KEY_2_TIME, KEY_2_VALUE, KEY_1_TIME, KEY_1_VALUE)

        self._assert_tangent(
            0, is_in_tangent=True, expected_x=0.0, expected_y=0.0, msg="Key 0 IN: No previous neighbor"
        )
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=k0_out_x,
            expected_y=k0_out_y,
            msg="Key 0 OUT: boundary -> LINEAR midpoint",
        )
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=k1_auto_in_x,
            expected_y=k1_auto_in_y,
            msg="Key 1 IN: AUTO from Key0->Key2",
        )
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=k1_auto_out_x,
            expected_y=k1_auto_out_y,
            msg="Key 1 OUT: AUTO from Key0->Key2",
        )
        self._assert_tangent(
            2, is_in_tangent=True, expected_x=k2_in_x, expected_y=k2_in_y, msg="Key 2 IN: boundary -> LINEAR midpoint"
        )
        self._assert_tangent(2, is_in_tangent=False, expected_x=0.0, expected_y=0.0, msg="Key 2 OUT: No next neighbor")

        await self._wait_for_continue()

    # =========================================================================
    # Test 2: AUTO at boundaries only (middle key is LINEAR)
    # =========================================================================
    async def test_auto_boundaries_linear_middle(self):
        """AUTO at boundaries with LINEAR middle key.

        Tests that AUTO at boundaries correctly falls back to LINEAR (midpoint).
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
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
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("AUTO boundaries, LINEAR middle")

        k0_out_x, k0_out_y = self._linear_tangent(KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE)
        k1_in_x, k1_in_y = self._linear_tangent(KEY_1_TIME, KEY_1_VALUE, KEY_0_TIME, KEY_0_VALUE)
        k1_out_x, k1_out_y = self._linear_tangent(KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE)
        k2_in_x, k2_in_y = self._linear_tangent(KEY_2_TIME, KEY_2_VALUE, KEY_1_TIME, KEY_1_VALUE)

        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=k0_out_x,
            expected_y=k0_out_y,
            msg="Key 0 OUT: AUTO boundary -> LINEAR midpoint",
        )
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=k1_in_x, expected_y=k1_in_y, msg="Key 1 IN: LINEAR midpoint from Key 0"
        )
        self._assert_tangent(
            1, is_in_tangent=False, expected_x=k1_out_x, expected_y=k1_out_y, msg="Key 1 OUT: LINEAR midpoint to Key 2"
        )
        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=k2_in_x,
            expected_y=k2_in_y,
            msg="Key 2 IN: AUTO boundary -> LINEAR midpoint",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 3: AUTO + FLAT combinations
    # =========================================================================
    async def test_auto_out_flat_in(self):
        """AUTO out-tangent paired with FLAT in-tangent.

        AUTO at boundary falls back to LINEAR. FLAT is always horizontal.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,  # Falls back to LINEAR at boundary
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.FLAT,
                            out_tangent_type=TangentType.AUTO,  # Middle key, true AUTO
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.FLAT,
                            out_tangent_type=TangentType.AUTO,  # Falls back to LINEAR at boundary
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("AUTO(0).out -> FLAT(1).in | AUTO(1).out -> FLAT(2).in")

        k0_out_x, k0_out_y = self._linear_tangent(KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE)
        k1_auto_out_x, k1_auto_out_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=False
        )
        flat_in_half_dt = (KEY_0_TIME - KEY_1_TIME) / 2
        flat_in_half_dt_k2 = (KEY_1_TIME - KEY_2_TIME) / 2

        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=k0_out_x,
            expected_y=k0_out_y,
            msg="Key 0 OUT: AUTO boundary -> LINEAR midpoint",
        )
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=flat_in_half_dt, expected_y=0.0, msg="Key 1 IN: FLAT horizontal"
        )
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=k1_auto_out_x,
            expected_y=k1_auto_out_y,
            msg="Key 1 OUT: AUTO middle Key0->Key2",
        )
        self._assert_tangent(
            2, is_in_tangent=True, expected_x=flat_in_half_dt_k2, expected_y=0.0, msg="Key 2 IN: FLAT horizontal"
        )
        self._assert_tangent(2, is_in_tangent=False, expected_x=0.0, expected_y=0.0, msg="Key 2 OUT: No next neighbor")

        await self._wait_for_continue()

    async def test_flat_out_auto_in(self):
        """FLAT out-tangent paired with AUTO in-tangent.

        FLAT is always horizontal. AUTO at middle key computes from neighbors.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.FLAT,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.AUTO,  # Middle key, true AUTO
                            out_tangent_type=TangentType.FLAT,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.AUTO,  # Boundary, falls back to LINEAR
                            out_tangent_type=TangentType.AUTO,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("FLAT(0).out -> AUTO(1).in | FLAT(1).out -> AUTO(2).in")

        flat_out_half_dt_k0 = (KEY_1_TIME - KEY_0_TIME) / 2
        flat_out_half_dt_k1 = (KEY_2_TIME - KEY_1_TIME) / 2
        k1_auto_in_x, k1_auto_in_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=True
        )
        k2_in_x, k2_in_y = self._linear_tangent(KEY_2_TIME, KEY_2_VALUE, KEY_1_TIME, KEY_1_VALUE)

        self._assert_tangent(
            0, is_in_tangent=True, expected_x=0.0, expected_y=0.0, msg="Key 0 IN: No previous neighbor"
        )
        self._assert_tangent(
            0, is_in_tangent=False, expected_x=flat_out_half_dt_k0, expected_y=0.0, msg="Key 0 OUT: FLAT horizontal"
        )
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=k1_auto_in_x,
            expected_y=k1_auto_in_y,
            msg="Key 1 IN: AUTO middle Key0->Key2",
        )
        self._assert_tangent(
            1, is_in_tangent=False, expected_x=flat_out_half_dt_k1, expected_y=0.0, msg="Key 1 OUT: FLAT horizontal"
        )
        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=k2_in_x,
            expected_y=k2_in_y,
            msg="Key 2 IN: AUTO boundary -> LINEAR midpoint",
        )
        self._assert_tangent(2, is_in_tangent=False, expected_x=0.0, expected_y=0.0, msg="Key 2 OUT: No next neighbor")

        await self._wait_for_continue()

    # =========================================================================
    # Test 4: AUTO + CUSTOM combinations
    # =========================================================================
    async def test_auto_paired_with_custom(self):
        """AUTO tangents paired with CUSTOM tangents.

        AUTO should compute independently of CUSTOM values on adjacent keys.
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
                            out_tangent_x=0.3,
                            out_tangent_y=0.25,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.AUTO,  # Middle key, true AUTO
                            out_tangent_type=TangentType.AUTO,  # Middle key, true AUTO
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.3,
                            in_tangent_y=0.15,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM(0).out -> AUTO(1).in | AUTO(1).out -> CUSTOM(2).in")

        k1_auto_in_x, k1_auto_in_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=True
        )
        k1_auto_out_x, k1_auto_out_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=False
        )

        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.3, expected_y=0.25, msg="Key 0 OUT: CUSTOM user-defined"
        )
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=k1_auto_in_x,
            expected_y=k1_auto_in_y,
            msg="Key 1 IN: AUTO independent of CUSTOM",
        )
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=k1_auto_out_x,
            expected_y=k1_auto_out_y,
            msg="Key 1 OUT: AUTO independent of CUSTOM",
        )
        self._assert_tangent(
            2, is_in_tangent=True, expected_x=-0.3, expected_y=0.15, msg="Key 2 IN: CUSTOM user-defined"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 5: AUTO + STEP combinations
    # =========================================================================
    async def test_step_out_auto_in(self):
        """STEP out-tangent paired with AUTO in-tangent.

        STEP out governs the segment. AUTO in is computed but ignored for segment rendering.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.STEP,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.AUTO,  # Computed but ignored by STEP
                            out_tangent_type=TangentType.STEP,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.AUTO,  # Computed but ignored by STEP
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("STEP(0).out -> AUTO(1).in | STEP(1).out -> AUTO(2).in")

        # STEP on prev key's out overrules in tangent type (math.py line 182-184):
        # in_tangent = (prev_diff.x / 2, 0.0) — always flat.
        k1_step_in_x = (KEY_0_TIME - KEY_1_TIME) / 2  # -0.25
        k2_step_in_x = (KEY_1_TIME - KEY_2_TIME) / 2  # -0.25

        self._assert_tangent(
            0, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="Key 0 OUT: STEP has no handle"
        )
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=k1_step_in_x, expected_y=0.0, msg="Key 1 IN: overridden by prev STEP out"
        )
        self._assert_tangent(
            1, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="Key 1 OUT: STEP has no handle"
        )
        self._assert_tangent(
            2, is_in_tangent=True, expected_x=k2_step_in_x, expected_y=0.0, msg="Key 2 IN: overridden by prev STEP out"
        )

        await self._wait_for_continue()

    async def test_auto_out_step_in(self):
        """AUTO out-tangent paired with STEP in-tangent.

        STEP in falls back to LINEAR. AUTO at boundary falls back to LINEAR.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.AUTO,  # Boundary, falls back to LINEAR
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.STEP,  # Falls back to LINEAR
                            out_tangent_type=TangentType.AUTO,  # Middle key, true AUTO
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.STEP,  # Falls back to LINEAR
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("AUTO(0).out -> STEP(1).in(->LINEAR) | AUTO(1).out -> STEP(2).in(->LINEAR)")

        k0_out_x, k0_out_y = self._linear_tangent(KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE)
        k1_step_in_x, k1_step_in_y = self._linear_tangent(KEY_1_TIME, KEY_1_VALUE, KEY_0_TIME, KEY_0_VALUE)
        k1_auto_out_x, k1_auto_out_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=False
        )
        k2_step_in_x, k2_step_in_y = self._linear_tangent(KEY_2_TIME, KEY_2_VALUE, KEY_1_TIME, KEY_1_VALUE)

        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=k0_out_x,
            expected_y=k0_out_y,
            msg="Key 0 OUT: AUTO boundary -> LINEAR midpoint",
        )
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=k1_step_in_x,
            expected_y=k1_step_in_y,
            msg="Key 1 IN: STEP falls back to LINEAR midpoint",
        )
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=k1_auto_out_x,
            expected_y=k1_auto_out_y,
            msg="Key 1 OUT: AUTO middle Key0->Key2",
        )
        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=k2_step_in_x,
            expected_y=k2_step_in_y,
            msg="Key 2 IN: STEP falls back to LINEAR midpoint",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 6: Two keyframes with AUTO (both boundaries)
    # =========================================================================
    async def test_two_keys_both_auto(self):
        """Two keyframes both with AUTO tangents.

        Both are boundary keys, so both fall back to LINEAR behavior (midpoint).
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.2,
                            value=0.3,
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
                        ),
                        FCurveKey(
                            time=0.8,
                            value=0.7,
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Two keys: AUTO(0) -> AUTO(1) (both boundaries, fall back to LINEAR)")

        await self._wait_for_continue()

        k0_time, k0_value = 0.2, 0.3
        k1_time, k1_value = 0.8, 0.7
        k0_out_x, k0_out_y = self._linear_tangent(k0_time, k0_value, k1_time, k1_value)
        k1_in_x, k1_in_y = self._linear_tangent(k1_time, k1_value, k0_time, k0_value)

        self._assert_tangent(
            0, is_in_tangent=True, expected_x=0.0, expected_y=0.0, msg="Key 0 IN: No previous neighbor"
        )
        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=k0_out_x,
            expected_y=k0_out_y,
            msg="Key 0 OUT: boundary -> LINEAR midpoint",
        )
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=k1_in_x, expected_y=k1_in_y, msg="Key 1 IN: boundary -> LINEAR midpoint"
        )
        self._assert_tangent(1, is_in_tangent=False, expected_x=0.0, expected_y=0.0, msg="Key 1 OUT: No next neighbor")

        await self._wait_for_continue()

    # =========================================================================
    # Test 7: Drag middle keyframe - AUTO tangents should recompute
    # =========================================================================
    async def test_drag_middle_key_auto_recomputes(self):
        """Drag middle keyframe and verify AUTO tangents recompute.

        Moving the middle keyframe changes the slope for AUTO computation.
        All AUTO tangents should update accordingly.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
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
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Drag test: All AUTO (initial)")

        k0_out_x, k0_out_y = self._linear_tangent(KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE)
        k1_auto_in_x, k1_auto_in_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=True
        )
        k1_auto_out_x, k1_auto_out_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=False
        )
        k2_in_x, k2_in_y = self._linear_tangent(KEY_2_TIME, KEY_2_VALUE, KEY_1_TIME, KEY_1_VALUE)

        self._assert_tangent(0, is_in_tangent=False, expected_x=k0_out_x, expected_y=k0_out_y, msg="Initial: Key 0 OUT")
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=k1_auto_in_x, expected_y=k1_auto_in_y, msg="Initial: Key 1 IN"
        )
        self._assert_tangent(
            1, is_in_tangent=False, expected_x=k1_auto_out_x, expected_y=k1_auto_out_y, msg="Initial: Key 1 OUT"
        )
        self._assert_tangent(2, is_in_tangent=True, expected_x=k2_in_x, expected_y=k2_in_y, msg="Initial: Key 2 IN")

        await self._wait_for_continue()

        dy_up = -50
        self._set_label("Drag test: Dragging key 1 UP by 50px")
        await self._drag_key(1, 0, dy_up)

        curve = self._get_curve()
        self.assertAlmostEqual(curve.keys[1].value, 0.78, delta=0.02, msg="Key 1 should have moved up")

        k0_out_after_x, k0_out_after_y = self._linear_tangent(KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, curve.keys[1].value)
        k2_in_after_x, k2_in_after_y = self._linear_tangent(KEY_2_TIME, KEY_2_VALUE, KEY_1_TIME, curve.keys[1].value)

        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=k0_out_after_x,
            expected_y=k0_out_after_y,
            delta=0.02,
            msg="After drag up: Key 0 OUT recomputed",
        )
        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=k2_in_after_x,
            expected_y=k2_in_after_y,
            delta=0.02,
            msg="After drag up: Key 2 IN recomputed",
        )

        await self._wait_for_continue()

        self._set_label("Drag test: Dragging key 1 DOWN by 100px")
        dy_down = 100
        await self._drag_key(1, 0, dy_down)

        self.assertAlmostEqual(curve.keys[1].value, 0.42, delta=0.02, msg="Key 1 should have moved down")

        k0_out_after_x, k0_out_after_y = self._linear_tangent(KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, curve.keys[1].value)
        k2_in_after_x, k2_in_after_y = self._linear_tangent(KEY_2_TIME, KEY_2_VALUE, KEY_1_TIME, curve.keys[1].value)

        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=k0_out_after_x,
            expected_y=k0_out_after_y,
            delta=0.02,
            msg="After drag down: Key 0 OUT recomputed",
        )
        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=k2_in_after_x,
            expected_y=k2_in_after_y,
            delta=0.02,
            msg="After drag down: Key 2 IN recomputed",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 8: Drag first keyframe - boundary AUTO recomputes
    # =========================================================================
    async def test_drag_first_key_auto_recomputes(self):
        """Drag first keyframe and verify AUTO tangents recompute.

        Moving the first keyframe changes both:
        - Its own out tangent (midpoint to Key 1)
        - Middle key's AUTO slope (based on Key 0 -> Key 2)
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
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
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Drag test: All AUTO (initial)")

        k0_out_x, k0_out_y = self._linear_tangent(KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE)
        k1_auto_in_x, k1_auto_in_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=True
        )

        self._assert_tangent(0, is_in_tangent=False, expected_x=k0_out_x, expected_y=k0_out_y, msg="Initial: Key 0 OUT")
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=k1_auto_in_x, expected_y=k1_auto_in_y, msg="Initial: Key 1 IN"
        )

        await self._wait_for_continue()

        dy_up = -40
        self._set_label("Drag test: Dragging key 0 UP by 40px")
        await self._drag_key(0, 0, dy_up)

        curve = self._get_curve()
        self.assertAlmostEqual(curve.keys[0].value, 0.34, delta=0.02, msg="Key 0 should have moved up")

        k0_out_after_x, k0_out_after_y = self._linear_tangent(KEY_0_TIME, curve.keys[0].value, KEY_1_TIME, KEY_1_VALUE)
        k1_auto_in_after_x, k1_auto_in_after_y = self._auto_tangent(
            KEY_0_TIME, curve.keys[0].value, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=True
        )

        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=k0_out_after_x,
            expected_y=k0_out_after_y,
            delta=0.02,
            msg="After drag: Key 0 OUT recomputed",
        )
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=k1_auto_in_after_x,
            expected_y=k1_auto_in_after_y,
            delta=0.02,
            msg="After drag: Key 1 IN recomputed",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 9: Drag last keyframe - boundary AUTO recomputes
    # =========================================================================
    async def test_drag_last_key_auto_recomputes(self):
        """Drag last keyframe and verify AUTO tangents recompute.

        Moving the last keyframe changes both:
        - Its own in tangent (midpoint from Key 1)
        - Middle key's AUTO slope (based on Key 0 -> Key 2)
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
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
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Drag test: All AUTO (initial)")

        k1_auto_out_x, k1_auto_out_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=False
        )
        k2_in_x, k2_in_y = self._linear_tangent(KEY_2_TIME, KEY_2_VALUE, KEY_1_TIME, KEY_1_VALUE)

        self._assert_tangent(
            1, is_in_tangent=False, expected_x=k1_auto_out_x, expected_y=k1_auto_out_y, msg="Initial: Key 1 OUT"
        )
        self._assert_tangent(2, is_in_tangent=True, expected_x=k2_in_x, expected_y=k2_in_y, msg="Initial: Key 2 IN")

        await self._wait_for_continue()

        dy_down = 60
        self._set_label("Drag test: Dragging key 2 DOWN by 60px")
        await self._drag_key(2, 0, dy_down)

        curve = self._get_curve()
        self.assertAlmostEqual(curve.keys[2].value, 0.19, delta=0.02, msg="Key 2 should have moved down")

        k2_in_after_x, k2_in_after_y = self._linear_tangent(KEY_2_TIME, curve.keys[2].value, KEY_1_TIME, KEY_1_VALUE)
        k1_auto_out_after_x, k1_auto_out_after_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, curve.keys[2].value, is_in=False
        )

        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=k2_in_after_x,
            expected_y=k2_in_after_y,
            delta=0.02,
            msg="After drag: Key 2 IN recomputed",
        )
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=k1_auto_out_after_x,
            expected_y=k1_auto_out_after_y,
            delta=0.02,
            msg="After drag: Key 1 OUT recomputed",
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 10: API switching - change tangent type to AUTO and verify recompute
    # =========================================================================
    async def test_switch_to_auto_recomputes(self):
        """Switch tangent types to AUTO via API and verify recomputation.

        Start with LINEAR tangents, then switch to AUTO and verify correct computation.
        """
        # Start with all LINEAR
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.LINEAR,
                            out_tangent_type=TangentType.LINEAR,
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
                            in_tangent_type=TangentType.LINEAR,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("All LINEAR (initial)")
        await self._wait_for_continue()

        k0_out_x, k0_out_y = self._linear_tangent(KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE)
        k1_linear_in_x, k1_linear_in_y = self._linear_tangent(KEY_1_TIME, KEY_1_VALUE, KEY_0_TIME, KEY_0_VALUE)
        k1_linear_out_x, k1_linear_out_y = self._linear_tangent(KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE)
        k1_auto_in_x, k1_auto_in_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=True
        )
        k1_auto_out_x, k1_auto_out_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=False
        )
        k2_in_x, k2_in_y = self._linear_tangent(KEY_2_TIME, KEY_2_VALUE, KEY_1_TIME, KEY_1_VALUE)

        self._assert_tangent(
            0, is_in_tangent=False, expected_x=k0_out_x, expected_y=k0_out_y, msg="Initial LINEAR: Key 0 OUT midpoint"
        )
        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=k1_linear_in_x,
            expected_y=k1_linear_in_y,
            msg="Initial LINEAR: Key 1 IN midpoint",
        )
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=k1_linear_out_x,
            expected_y=k1_linear_out_y,
            msg="Initial LINEAR: Key 1 OUT midpoint",
        )

        await self._wait_for_continue()

        self.widget.set_key_tangent_type("test", 1, in_tangent_type=TangentType.AUTO)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("LINEAR(0) -> AUTO(1).in | LINEAR(1).out")

        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=k1_auto_in_x,
            expected_y=k1_auto_in_y,
            msg="After switch: Key 1 IN now AUTO",
        )
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=k1_linear_out_x,
            expected_y=k1_linear_out_y,
            msg="After switch: Key 1 OUT still LINEAR",
        )

        await self._wait_for_continue()

        self.widget.set_key_tangent_type("test", 1, out_tangent_type=TangentType.AUTO)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("LINEAR(0) -> AUTO(1).in | AUTO(1).out -> LINEAR(2)")

        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=k1_auto_out_x,
            expected_y=k1_auto_out_y,
            msg="After switch: Key 1 OUT now AUTO",
        )

        await self._wait_for_continue()

        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.AUTO)
        self.widget.set_key_tangent_type("test", 2, in_tangent_type=TangentType.AUTO)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("All AUTO (boundary keys fall back to LINEAR)")

        self._assert_tangent(
            0, is_in_tangent=False, expected_x=k0_out_x, expected_y=k0_out_y, msg="Final: Key 0 OUT boundary -> LINEAR"
        )
        self._assert_tangent(
            2, is_in_tangent=True, expected_x=k2_in_x, expected_y=k2_in_y, msg="Final: Key 2 IN boundary -> LINEAR"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 11: Four keyframes with middle two being AUTO
    # =========================================================================
    async def test_four_keys_middle_auto(self):
        """Four keyframes with middle two having AUTO tangents.

        Tests that each middle key computes its own slope from its specific neighbors.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.0,
                            value=0.3,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                        FCurveKey(
                            time=0.3,
                            value=0.8,
                            in_tangent_type=TangentType.AUTO,  # Middle key
                            out_tangent_type=TangentType.AUTO,
                        ),
                        FCurveKey(
                            time=0.7,
                            value=0.5,
                            in_tangent_type=TangentType.AUTO,  # Middle key
                            out_tangent_type=TangentType.AUTO,
                        ),
                        FCurveKey(
                            time=1.0,
                            value=0.7,
                            in_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("4 keys: LINEAR -> AUTO -> AUTO -> LINEAR")

        t0, v0 = 0.0, 0.3
        t1, v1 = 0.3, 0.8
        t2, v2 = 0.7, 0.5
        t3, v3 = 1.0, 0.7

        k0_out_x, k0_out_y = self._linear_tangent(t0, v0, t1, v1)
        k1_auto_in_x, k1_auto_in_y = self._auto_tangent(t0, v0, t1, v1, t2, v2, is_in=True)
        k1_auto_out_x, k1_auto_out_y = self._auto_tangent(t0, v0, t1, v1, t2, v2, is_in=False)
        k2_auto_in_x, k2_auto_in_y = self._auto_tangent(t1, v1, t2, v2, t3, v3, is_in=True)
        k2_auto_out_x, k2_auto_out_y = self._auto_tangent(t1, v1, t2, v2, t3, v3, is_in=False)
        k3_in_x, k3_in_y = self._linear_tangent(t3, v3, t2, v2)

        self._assert_tangent(
            0, is_in_tangent=False, expected_x=k0_out_x, expected_y=k0_out_y, msg="Key 0 OUT: LINEAR midpoint to Key 1"
        )
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=k1_auto_in_x, expected_y=k1_auto_in_y, msg="Key 1 IN: AUTO Key0->Key2"
        )
        self._assert_tangent(
            1, is_in_tangent=False, expected_x=k1_auto_out_x, expected_y=k1_auto_out_y, msg="Key 1 OUT: AUTO Key0->Key2"
        )
        self._assert_tangent(
            2, is_in_tangent=True, expected_x=k2_auto_in_x, expected_y=k2_auto_in_y, msg="Key 2 IN: AUTO Key1->Key3"
        )
        self._assert_tangent(
            2, is_in_tangent=False, expected_x=k2_auto_out_x, expected_y=k2_auto_out_y, msg="Key 2 OUT: AUTO Key1->Key3"
        )
        self._assert_tangent(
            3, is_in_tangent=True, expected_x=k3_in_x, expected_y=k3_in_y, msg="Key 3 IN: LINEAR midpoint from Key 2"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test 12: Drag with mixed tangent types
    # =========================================================================
    async def test_drag_with_mixed_tangents(self):
        """Drag keyframe when curve has mixed tangent types.

        Verifies that AUTO tangents recompute while other types stay fixed.
        """
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
                            in_tangent_type=TangentType.AUTO,
                            out_tangent_type=TangentType.AUTO,
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
        self._set_label("FLAT(0).out -> AUTO(1) -> FLAT(2).in (initial)")

        flat_out_half_dt = (KEY_1_TIME - KEY_0_TIME) / 2
        flat_in_half_dt = (KEY_1_TIME - KEY_2_TIME) / 2
        k1_auto_in_x, k1_auto_in_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=True
        )
        k1_auto_out_x, k1_auto_out_y = self._auto_tangent(
            KEY_0_TIME, KEY_0_VALUE, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=False
        )

        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=flat_out_half_dt,
            expected_y=0.0,
            msg="Initial: Key 0 OUT FLAT horizontal",
        )
        self._assert_tangent(
            1, is_in_tangent=True, expected_x=k1_auto_in_x, expected_y=k1_auto_in_y, msg="Initial: Key 1 IN AUTO"
        )
        self._assert_tangent(
            1, is_in_tangent=False, expected_x=k1_auto_out_x, expected_y=k1_auto_out_y, msg="Initial: Key 1 OUT AUTO"
        )
        self._assert_tangent(
            2, is_in_tangent=True, expected_x=flat_in_half_dt, expected_y=0.0, msg="Initial: Key 2 IN FLAT horizontal"
        )

        await self._wait_for_continue()

        dy_up = -50
        self._set_label("Dragging key 0 UP - AUTO recomputes, FLAT stays horizontal")
        await self._drag_key(0, 0, dy_up)

        curve = self._get_curve()
        self.assertAlmostEqual(curve.keys[0].value, 0.38, delta=0.02, msg="Key 0 should have moved up")

        self._assert_tangent(
            0,
            is_in_tangent=False,
            expected_x=flat_out_half_dt,
            expected_y=0.0,
            msg="After drag: Key 0 OUT FLAT still horizontal",
        )
        self._assert_tangent(
            2,
            is_in_tangent=True,
            expected_x=flat_in_half_dt,
            expected_y=0.0,
            msg="After drag: Key 2 IN FLAT still horizontal",
        )

        k1_auto_in_after_x, k1_auto_in_after_y = self._auto_tangent(
            KEY_0_TIME, curve.keys[0].value, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=True
        )
        k1_auto_out_after_x, k1_auto_out_after_y = self._auto_tangent(
            KEY_0_TIME, curve.keys[0].value, KEY_1_TIME, KEY_1_VALUE, KEY_2_TIME, KEY_2_VALUE, is_in=False
        )

        self._assert_tangent(
            1,
            is_in_tangent=True,
            expected_x=k1_auto_in_after_x,
            expected_y=k1_auto_in_after_y,
            delta=0.02,
            msg="After drag: Key 1 IN AUTO recomputed",
        )
        self._assert_tangent(
            1,
            is_in_tangent=False,
            expected_x=k1_auto_out_after_x,
            expected_y=k1_auto_out_after_y,
            delta=0.02,
            msg="After drag: Key 1 OUT AUTO recomputed",
        )

        await self._wait_for_continue()
