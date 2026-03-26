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

E2E Tests for FLAT tangent handle behavior.

FLAT tangent behavior (from TANGENT_BEHAVIOR.md):
- FLAT tangents are horizontal (Y derivative/angle is always 0°)
- The handle's X position equals the neighboring keyframe's X position (full extension)
- IN tangent: X = -(key.time - prev_key.time), Y = 0
- OUT tangent: X = (next_key.time - key.time), Y = 0

This creates a smooth horizontal approach/departure at the keyframe.
"""

import omni.kit.app
import omni.kit.test
from omni import ui

from omni.flux.fcurve.widget import FCurveWidget, FCurve, FCurveKey, TangentType

__all__ = ["TestFlatTangents"]


# Test keyframe positions (3 keyframes)
KEY_0_TIME = 0.0
KEY_0_VALUE = 0.3
KEY_1_TIME = 0.5
KEY_1_VALUE = 0.7
KEY_2_TIME = 1.0
KEY_2_VALUE = 0.4

# Window dimensions
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 400
CURVE_WIDTH = 400
CURVE_HEIGHT = 280
PADDING = 30


class TestFlatTangents(omni.kit.test.AsyncTestCase):
    """Test FLAT tangent handle positions and interactions with other tangent types."""

    async def setUp(self):
        """Create window with FCurveWidget."""
        self._continue_clicked = False

        self.window = ui.Window(
            "Test FLAT Tangents",
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

        To enable interactive debugging, uncomment the loop below and
        comment out the return statement.
        """
        return
        # self._continue_clicked = False
        # while not self._continue_clicked:
        # await asyncio.sleep(0.1)
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

    def _assert_tangent_offset(
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

    # =========================================================================
    # Test 1: All FLAT tangents
    # =========================================================================
    async def test_all_flat_tangents(self):
        """All keyframes with FLAT tangents - handles are horizontal extending to neighbors."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.FLAT,
                            out_tangent_type=TangentType.FLAT,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.FLAT,
                            out_tangent_type=TangentType.FLAT,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.FLAT,
                            out_tangent_type=TangentType.FLAT,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("All FLAT: FLAT(0) -> FLAT(1) -> FLAT(2)")

        # Key 0: No previous neighbor, so IN tangent is (0, 0)
        # OUT tangent extends halfway to Key 1: X = (KEY_1_TIME - KEY_0_TIME) / 2 = 0.25, Y = 0
        self._assert_tangent_offset(
            0, is_in_tangent=True, expected_x=0.0, expected_y=0.0, msg="Key 0 IN: No previous neighbor"
        )
        self._assert_tangent_offset(
            0, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="Key 0 OUT: Extends to Key 1"
        )

        # Key 1: IN tangent extends to Key 0: X = -(KEY_1_TIME - KEY_0_TIME) / 2 = -0.25, Y = 0
        # OUT tangent extends halfway to Key 2: X = (KEY_2_TIME - KEY_1_TIME) / 2 = 0.25, Y = 0
        self._assert_tangent_offset(
            1, is_in_tangent=True, expected_x=-0.25, expected_y=0.0, msg="Key 1 IN: Extends to Key 0"
        )
        self._assert_tangent_offset(
            1, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="Key 1 OUT: Extends to Key 2"
        )

        # Key 2: IN tangent extends halfway to Key 1: X = -(KEY_2_TIME - KEY_1_TIME) / 2 = -0.25, Y = 0
        # No next neighbor, so OUT tangent is (0, 0)
        self._assert_tangent_offset(
            2, is_in_tangent=True, expected_x=-0.25, expected_y=0.0, msg="Key 2 IN: Extends to Key 1"
        )
        self._assert_tangent_offset(
            2, is_in_tangent=False, expected_x=0.0, expected_y=0.0, msg="Key 2 OUT: No next neighbor"
        )

    # =========================================================================
    # Test 2: LINEAR out → FLAT in
    # =========================================================================
    async def test_linear_out_flat_in(self):
        """LINEAR out-tangent paired with FLAT in-tangent."""
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
                            in_tangent_type=TangentType.FLAT,
                            out_tangent_type=TangentType.FLAT,
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
        self._set_label("LINEAR(0).out -> FLAT(1).in | FLAT(1).out -> LINEAR(2).in")

        # Key 0: LINEAR out-tangent = midpoint to Key 1
        # X = (KEY_1_TIME - KEY_0_TIME) / 2 = 0.25
        # Y = (KEY_1_VALUE - KEY_0_VALUE) / 2 = 0.2
        self._assert_tangent_offset(
            0, is_in_tangent=False, expected_x=0.25, expected_y=0.2, msg="Key 0 OUT: LINEAR midpoint to Key 1"
        )

        # Key 1: FLAT in-tangent = horizontal to Key 0
        # X = -(KEY_1_TIME - KEY_0_TIME) / 2 = -0.25, Y = 0
        self._assert_tangent_offset(
            1, is_in_tangent=True, expected_x=-0.25, expected_y=0.0, msg="Key 1 IN: FLAT horizontal to Key 0"
        )

        # Key 1: FLAT out-tangent = horizontal to Key 2
        # X = KEY_2_TIME - KEY_1_TIME = 0.5, Y = 0
        self._assert_tangent_offset(
            1, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="Key 1 OUT: FLAT horizontal to Key 2"
        )

        # Key 2: LINEAR in-tangent = midpoint from Key 1
        # X = -(KEY_2_TIME - KEY_1_TIME) / 2 = -0.25
        # Y = -(KEY_2_VALUE - KEY_1_VALUE) / 2 = 0.15
        self._assert_tangent_offset(
            2, is_in_tangent=True, expected_x=-0.25, expected_y=0.15, msg="Key 2 IN: LINEAR midpoint from Key 1"
        )

    # =========================================================================
    # Test 3: FLAT out → LINEAR in
    # =========================================================================
    async def test_flat_out_linear_in(self):
        """FLAT out-tangent paired with LINEAR in-tangent."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.FLAT,
                            out_tangent_type=TangentType.FLAT,
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
                            in_tangent_type=TangentType.FLAT,
                            out_tangent_type=TangentType.FLAT,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("FLAT(0).out -> LINEAR(1).in | LINEAR(1).out -> FLAT(2).in")

        # Key 0: FLAT out-tangent = horizontal to Key 1
        # X = KEY_1_TIME - KEY_0_TIME / 2 = 0.25, Y = 0
        self._assert_tangent_offset(
            0, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="Key 0 OUT: FLAT horizontal to Key 1"
        )

        # Key 1: LINEAR in-tangent = midpoint from Key 0
        # X = -(KEY_1_TIME - KEY_0_TIME) / 2 = -0.25
        # Y = -(KEY_1_VALUE - KEY_0_VALUE) / 2 = -0.2
        self._assert_tangent_offset(
            1, is_in_tangent=True, expected_x=-0.25, expected_y=-0.2, msg="Key 1 IN: LINEAR midpoint from Key 0"
        )

        # Key 1: LINEAR out-tangent = midpoint to Key 2
        # X = (KEY_2_TIME - KEY_1_TIME) / 2 = 0.25
        # Y = (KEY_2_VALUE - KEY_1_VALUE) / 2 = -0.15
        self._assert_tangent_offset(
            1, is_in_tangent=False, expected_x=0.25, expected_y=-0.15, msg="Key 1 OUT: LINEAR midpoint to Key 2"
        )

        # Key 2: FLAT in-tangent = horizontal to Key 1
        # X = -(KEY_2_TIME - KEY_1_TIME) / 2 = -0.25, Y = 0
        self._assert_tangent_offset(
            2, is_in_tangent=True, expected_x=-0.25, expected_y=0.0, msg="Key 2 IN: FLAT horizontal to Key 1"
        )

    # =========================================================================
    # Test 4: FLAT out → STEP in (STEP in falls back to LINEAR)
    # =========================================================================
    async def test_flat_out_step_in(self):
        """FLAT out-tangent paired with STEP in-tangent.

        Industry standard: STEP as in-tangent falls back to LINEAR behavior.
        STEP only makes sense as out-tangent to govern the departing segment.
        The segment uses normal bezier interpolation with FLAT out and LINEAR in.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.FLAT,
                            out_tangent_type=TangentType.FLAT,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.STEP,  # Falls back to LINEAR
                            out_tangent_type=TangentType.FLAT,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.FLAT,
                            out_tangent_type=TangentType.FLAT,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("FLAT(0).out -> STEP(1).in(->LINEAR) | FLAT(1).out -> FLAT(2).in")

        # Key 0: FLAT out-tangent = horizontal to Key 1
        # X = KEY_1_TIME - KEY_0_TIME = 0.5, Y = 0
        self._assert_tangent_offset(
            0, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="Key 0 OUT: FLAT horizontal to Key 1"
        )

        # Key 1: STEP in-tangent falls back to LINEAR = midpoint from Key 0
        # X = -(KEY_1_TIME - KEY_0_TIME) / 2 = -0.25
        # Y = -(KEY_1_VALUE - KEY_0_VALUE) / 2 = -0.2
        self._assert_tangent_offset(
            1, is_in_tangent=True, expected_x=-0.25, expected_y=-0.2, msg="Key 1 IN: STEP falls back to LINEAR midpoint"
        )

        # Key 1: FLAT out-tangent to Key 2
        self._assert_tangent_offset(
            1, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="Key 1 OUT: FLAT horizontal to Key 2"
        )

        # Key 2: FLAT in-tangent from Key 1
        self._assert_tangent_offset(
            2, is_in_tangent=True, expected_x=-0.25, expected_y=0.0, msg="Key 2 IN: FLAT horizontal from Key 1"
        )

    # =========================================================================
    # Test 5: STEP out → FLAT in (STEP out governs segment)
    # =========================================================================
    async def test_step_out_flat_in(self):
        """STEP out-tangent paired with FLAT in-tangent.

        Industry standard: STEP out-tangent creates a stepped segment.
        The next key's in-tangent (FLAT) is ignored for segment rendering.
        The segment is constant at Key 0's Y, then snaps at Key 1.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            in_tangent_type=TangentType.FLAT,
                            out_tangent_type=TangentType.STEP,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.FLAT,  # Ignored for segment rendering
                            out_tangent_type=TangentType.FLAT,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                            in_tangent_type=TangentType.FLAT,
                            out_tangent_type=TangentType.FLAT,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("STEP(0).out -> FLAT(1).in(ignored) | FLAT(1).out -> FLAT(2).in")

        # Key 0: STEP out-tangent = (0, 0) - no bezier handle, segment is stepped
        self._assert_tangent_offset(
            0, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="Key 0 OUT: STEP has no handle"
        )

        # Key 1: FLAT in-tangent is computed but ignored for segment rendering
        # X = -(KEY_1_TIME - KEY_0_TIME) = -0.5, Y = 0
        self._assert_tangent_offset(
            1,
            is_in_tangent=True,
            expected_x=-0.25,
            expected_y=0.0,
            msg="Key 1 IN: FLAT (computed, but ignored by STEP segment)",
        )

        # Key 1: FLAT out-tangent to Key 2
        self._assert_tangent_offset(
            1, is_in_tangent=False, expected_x=0.25, expected_y=0.0, msg="Key 1 OUT: FLAT horizontal to Key 2"
        )

        # Key 2: FLAT in-tangent from Key 1
        self._assert_tangent_offset(
            2, is_in_tangent=True, expected_x=-0.25, expected_y=0.0, msg="Key 2 IN: FLAT horizontal from Key 1"
        )

    # =========================================================================
    # Test 6: FLAT in-tangent paired with various out-tangents (via API switching)
    # =========================================================================
    async def test_flat_in_against_various_out_tangents(self):
        """FLAT in-tangent paired with SMOOTH, CUSTOM, and AUTO out-tangents.

        The FLAT in-tangent should always produce the same horizontal handle
        regardless of what the previous key's out-tangent type is.
        """
        # Start with SMOOTH out on Key 0
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=KEY_0_TIME,
                            value=KEY_0_VALUE,
                            out_tangent_type=TangentType.SMOOTH,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.FLAT,
                            out_tangent_type=TangentType.FLAT,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("SMOOTH(0).out -> FLAT(1).in (switching modes...)")

        # Key 1 FLAT in-tangent should be horizontal to Key 0
        expected_in_x = -(KEY_1_TIME - KEY_0_TIME) / 2  # -0.25
        expected_in_y = 0.0

        self._assert_tangent_offset(
            1,
            is_in_tangent=True,
            expected_x=expected_in_x,
            expected_y=expected_in_y,
            msg="FLAT in vs SMOOTH out: horizontal",
        )

        # Switch Key 0 to CUSTOM out-tangent
        await self._wait_for_continue()
        self.widget.set_key_tangent_type(
            "test",
            0,
            out_tangent_type=TangentType.CUSTOM,
            out_tangent_x=0.3,
            out_tangent_y=0.2,
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM(0).out -> FLAT(1).in (switching modes...)")

        # Key 1 FLAT in-tangent should still be the same
        self._assert_tangent_offset(
            1,
            is_in_tangent=True,
            expected_x=expected_in_x,
            expected_y=expected_in_y,
            msg="FLAT in vs CUSTOM out: horizontal",
        )

        # Switch Key 0 to AUTO out-tangent
        await self._wait_for_continue()
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.AUTO)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("AUTO(0).out -> FLAT(1).in (FLAT always horizontal)")

        # Key 1 FLAT in-tangent should still be the same
        self._assert_tangent_offset(
            1,
            is_in_tangent=True,
            expected_x=expected_in_x,
            expected_y=expected_in_y,
            msg="FLAT in vs AUTO out: horizontal",
        )

    # =========================================================================
    # Test 7: FLAT out-tangent paired with various in-tangents (via API switching)
    # =========================================================================
    async def test_flat_out_against_various_in_tangents(self):
        """FLAT out-tangent paired with SMOOTH, CUSTOM, and AUTO in-tangents.

        The FLAT out-tangent should always produce the same horizontal handle
        regardless of what the next key's in-tangent type is.
        """
        # Start with SMOOTH in on Key 1
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
                            out_tangent_type=TangentType.FLAT,
                        ),
                        FCurveKey(
                            time=KEY_2_TIME,
                            value=KEY_2_VALUE,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("FLAT(0).out -> SMOOTH(1).in (switching modes...)")

        # Key 0 FLAT out-tangent should be horizontal to Key 1
        expected_out_x = (KEY_1_TIME - KEY_0_TIME) / 2  # 0.25
        expected_out_y = 0.0

        self._assert_tangent_offset(
            0,
            is_in_tangent=False,
            expected_x=expected_out_x,
            expected_y=expected_out_y,
            msg="FLAT out vs SMOOTH in: horizontal",
        )

        # Switch Key 1 to CUSTOM in-tangent
        await self._wait_for_continue()
        self.widget.set_key_tangent_type(
            "test",
            1,
            in_tangent_type=TangentType.CUSTOM,
            in_tangent_x=-0.3,
            in_tangent_y=-0.2,
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("FLAT(0).out -> CUSTOM(1).in (switching modes...)")

        # Key 0 FLAT out-tangent should still be the same
        self._assert_tangent_offset(
            0,
            is_in_tangent=False,
            expected_x=expected_out_x,
            expected_y=expected_out_y,
            msg="FLAT out vs CUSTOM in: horizontal",
        )

        # Switch Key 1 to AUTO in-tangent
        await self._wait_for_continue()
        self.widget.set_key_tangent_type("test", 1, in_tangent_type=TangentType.AUTO)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("FLAT(0).out -> AUTO(1).in (FLAT always horizontal)")

        # Key 0 FLAT out-tangent should still be the same
        self._assert_tangent_offset(
            0,
            is_in_tangent=False,
            expected_x=expected_out_x,
            expected_y=expected_out_y,
            msg="FLAT out vs AUTO in: horizontal",
        )
