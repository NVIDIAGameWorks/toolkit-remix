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

E2E Tests for keyframe position clamping and reorder prevention.

Keyframes should not be able to cross each other (reorder). When a keyframe
is dragged past its neighbor, it should be clamped with a configurable threshold.
A ghost line should show the user's actual drag position vs the clamped position.
"""

import os

import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
from omni import ui

from omni.flux.fcurve.widget import FCurveWidget, FCurve, FCurveKey

__all__ = ["TestKeyframeClamping"]


# Test keyframe positions (3 keyframes for neighbor clamping tests)
KEY_0_TIME = 0.2
KEY_0_VALUE = 0.3
KEY_1_TIME = 0.5
KEY_1_VALUE = 0.6
KEY_2_TIME = 0.8
KEY_2_VALUE = 0.4

# Window dimensions
WINDOW_WIDTH = 600
WINDOW_HEIGHT = 500
CURVE_WIDTH = 500
CURVE_HEIGHT = 380
PADDING = 30

# Default clamping threshold (in model time units)
DEFAULT_THRESHOLD = 0.01


class TestKeyframeClamping(omni.kit.test.AsyncTestCase):
    """Test keyframe position clamping to prevent reordering."""

    async def setUp(self):
        """Create window with FCurveWidget."""
        self._continue_clicked = False

        self.window = ui.Window(
            "Test Keyframe Clamping",
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

                # Curve widget in sized container
                ui.Spacer(height=PADDING)
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

    async def tearDown(self):
        """Clean up."""
        self.widget = None
        self.window = None
        await omni.kit.app.get_app().next_update_async()

    def _on_continue_clicked(self):
        self._continue_clicked = True

    async def _wait_for_continue(self, message: str = ""):
        """Wait for user to click continue (for interactive debugging)."""
        # Uncomment below for interactive debugging:
        # if message:
        #     self._label.text = message
        # self._continue_clicked = False
        # while not self._continue_clicked:
        #     await asyncio.sleep(0.1)
        # self._label.text = ""
        return

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _setup_three_key_curve(self) -> None:
        """Set up a curve with 3 keyframes for neighbor clamping tests."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=KEY_0_TIME, value=KEY_0_VALUE),
                        FCurveKey(time=KEY_1_TIME, value=KEY_1_VALUE),
                        FCurveKey(time=KEY_2_TIME, value=KEY_2_VALUE),
                    ],
                    color=0xFF00FF00,
                )
            }
        )

    def _get_key_pixel_position(self, key_index: int) -> tuple[float, float]:
        """Get keyframe pixel position from manager."""
        mgr = self.widget._managers.get("test")
        if not mgr or key_index >= len(mgr.key_handles):
            return (0.0, 0.0)
        handle = mgr.key_handles[key_index]
        return handle.position

    def _get_key_model_position(self, key_index: int) -> tuple[float, float]:
        """Get keyframe model position from the curve."""
        curve = self.widget.curves.get("test")
        if not curve or key_index >= len(curve.keys):
            return (0.0, 0.0)
        key = curve.keys[key_index]
        return key.time, key.value

    async def _select_key(self, key_index: int) -> None:
        """Select a keyframe by clicking on it."""
        mgr = self.widget._managers["test"]
        handle = mgr.key_handles[key_index]
        pos = ui_test.Vec2(*handle.screen_center)
        await ui_test.input.emulate_mouse_move(pos)
        await ui_test.human_delay(3)
        await ui_test.emulate_mouse_click()
        await ui_test.human_delay(3)
        await omni.kit.app.get_app().next_update_async()

    async def _drag_key(self, key_index: int, dx: float, dy: float) -> None:
        """Drag a keyframe by pixel delta."""
        mgr = self.widget._managers["test"]
        handle = mgr.key_handles[key_index]
        start = ui_test.Vec2(*handle.screen_center)
        end = start + ui_test.Vec2(dx, dy)
        await ui_test.input.emulate_mouse_move(start)
        await ui_test.human_delay(3)
        await ui_test.emulate_mouse_drag_and_drop(start, end)
        await omni.kit.app.get_app().next_update_async()

    # =========================================================================
    # Test: Keyframe cannot cross previous neighbor
    # =========================================================================

    async def test_keyframe_clamps_to_previous_neighbor(self):
        """
        Dragging a keyframe left should clamp before crossing the previous keyframe.

        Setup: 3 keys at times [0.2, 0.5, 0.8]
        Action: Drag middle key (0.5) far left past first key (0.2)
        Expected: Key clamps to 0.2 + threshold, not crossing key[0]
        """
        self._setup_three_key_curve()
        await omni.kit.app.get_app().next_update_async()

        # Record initial positions
        initial_key0_time, _ = self._get_key_model_position(0)
        initial_key1_time, _ = self._get_key_model_position(1)

        self.assertAlmostEqual(initial_key0_time, KEY_0_TIME, delta=0.01)
        self.assertAlmostEqual(initial_key1_time, KEY_1_TIME, delta=0.01)

        # Drag middle key far to the left (past key[0])
        # This should be a large drag that would cross key[0] if not clamped
        await self._drag_key(1, dx=-300, dy=0)

        # Get new position
        new_key1_time, _ = self._get_key_model_position(1)
        key0_time, _ = self._get_key_model_position(0)

        # Key[1] should NOT cross key[0] - should be clamped at key[0].time + threshold
        self.assertGreater(
            new_key1_time, key0_time, f"BUG: Key[1] crossed key[0]! key1={new_key1_time}, key0={key0_time}"
        )

        # Verify it's close to but not past the threshold
        self.assertAlmostEqual(
            new_key1_time,
            key0_time + DEFAULT_THRESHOLD,
            delta=0.02,
            msg="Key[1] should be clamped near key[0]+threshold",
        )

    async def test_keyframe_clamps_to_next_neighbor(self):
        """
        Dragging a keyframe right should clamp before crossing the next keyframe.

        Setup: 3 keys at times [0.2, 0.5, 0.8]
        Action: Drag middle key (0.5) far right past last key (0.8)
        Expected: Key clamps to 0.8 - threshold, not crossing key[2]
        """
        self._setup_three_key_curve()
        await omni.kit.app.get_app().next_update_async()

        # Record initial positions
        initial_key1_time, _ = self._get_key_model_position(1)
        initial_key2_time, _ = self._get_key_model_position(2)

        self.assertAlmostEqual(initial_key1_time, KEY_1_TIME, delta=0.01)
        self.assertAlmostEqual(initial_key2_time, KEY_2_TIME, delta=0.01)

        # Drag middle key far to the right (past key[2])
        await self._drag_key(1, dx=300, dy=0)

        # Get new position
        new_key1_time, _ = self._get_key_model_position(1)
        key2_time, _ = self._get_key_model_position(2)

        # Key[1] should NOT cross key[2] - should be clamped at key[2].time - threshold
        self.assertLess(new_key1_time, key2_time, f"BUG: Key[1] crossed key[2]! key1={new_key1_time}, key2={key2_time}")

        # Verify it's close to but not past the threshold
        self.assertAlmostEqual(
            new_key1_time,
            key2_time - DEFAULT_THRESHOLD,
            delta=0.02,
            msg="Key[1] should be clamped near key[2]-threshold",
        )

    async def test_first_keyframe_has_no_left_constraint(self):
        """
        The first keyframe should not have a left neighbor constraint.

        Setup: 3 keys at times [0.2, 0.5, 0.8]
        Action: Drag first key (0.2) far left
        Expected: Key can move freely left (only bounded by viewport)
        """
        self._setup_three_key_curve()
        await omni.kit.app.get_app().next_update_async()

        initial_key0_time, _ = self._get_key_model_position(0)

        # Drag first key left
        await self._drag_key(0, dx=-100, dy=0)

        new_key0_time, _ = self._get_key_model_position(0)

        # First key should have moved left (no neighbor to clamp against)
        self.assertLess(new_key0_time, initial_key0_time, "First key should be able to move left freely")

    async def test_last_keyframe_has_no_right_constraint(self):
        """
        The last keyframe should not have a right neighbor constraint.

        Setup: 3 keys at times [0.2, 0.5, 0.8]
        Action: Drag last key (0.8) far right
        Expected: Key can move freely right (only bounded by viewport)
        """
        self._setup_three_key_curve()
        await omni.kit.app.get_app().next_update_async()

        initial_key2_time, _ = self._get_key_model_position(2)

        # Drag last key right
        await self._drag_key(2, dx=100, dy=0)

        new_key2_time, _ = self._get_key_model_position(2)

        # Last key should have moved right (no neighbor to clamp against)
        self.assertGreater(new_key2_time, initial_key2_time, "Last key should be able to move right freely")

    async def test_y_movement_not_constrained_by_neighbors(self):
        """
        Y movement should not be affected by neighbor constraints.
        Only X (time) is constrained.
        """
        self._setup_three_key_curve()
        await omni.kit.app.get_app().next_update_async()

        _, initial_key1_value = self._get_key_model_position(1)

        # Drag middle key up (Y change only)
        await self._drag_key(1, dx=0, dy=-100)

        _, new_key1_value = self._get_key_model_position(1)

        # Y should have changed (moved up = higher value)
        self.assertGreater(new_key1_value, initial_key1_value, "Y movement should not be constrained by neighbors")

    # =========================================================================
    # Test: Configurable threshold
    # =========================================================================

    async def test_custom_threshold_is_respected(self):
        """
        The clamping threshold should be configurable via FCurveWidget.

        Setup: Set a custom threshold (e.g., 0.05)
        Action: Drag key towards neighbor
        Expected: Key clamps at custom threshold distance
        """
        # Set custom threshold before creating curve
        custom_threshold = 0.05
        self.widget.keyframe_clamp_threshold = custom_threshold

        self._setup_three_key_curve()
        await omni.kit.app.get_app().next_update_async()

        # Drag middle key far left
        await self._drag_key(1, dx=-300, dy=0)

        new_key1_time, _ = self._get_key_model_position(1)
        key0_time, _ = self._get_key_model_position(0)

        # Verify clamped at custom threshold
        self.assertAlmostEqual(
            new_key1_time,
            key0_time + custom_threshold,
            delta=0.02,
            msg=f"Key should be clamped at custom threshold {custom_threshold}",
        )

    async def test_zero_threshold_allows_keys_to_touch(self):
        """
        With threshold=0, keys should be able to have the same time
        (but still not cross).
        """
        # Set zero threshold
        self.widget.keyframe_clamp_threshold = 0.0

        self._setup_three_key_curve()
        await omni.kit.app.get_app().next_update_async()

        # Drag middle key far left
        await self._drag_key(1, dx=-300, dy=0)

        new_key1_time, _ = self._get_key_model_position(1)
        key0_time, _ = self._get_key_model_position(0)

        # Keys should be at same position (or very close)
        self.assertAlmostEqual(
            new_key1_time, key0_time, delta=0.01, msg="With threshold=0, keys should be able to touch"
        )

        # But key[1] should still not be LESS than key[0]
        self.assertGreaterEqual(new_key1_time, key0_time, "Keys should never cross, even with threshold=0")

    # =========================================================================
    # Test: Interactive debugging
    # =========================================================================

    async def test_interactive_keyframe_clamping(self):
        """
        Interactive test for manual verification of keyframe clamping behavior.

        Skip this test in CI by checking for interactive mode.
        """
        if os.environ.get("CI") or os.environ.get("OMNI_KIT_TEST_NO_INTERACTIVE"):
            self.skipTest("Skipping interactive test in CI")

        self._setup_three_key_curve()
        await omni.kit.app.get_app().next_update_async()

        await self._wait_for_continue(
            "Try dragging the middle keyframe past its neighbors. "
            "It should clamp and show a ghost line. Click Continue when done."
        )
