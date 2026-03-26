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

E2E Tests for STEP tangent behavior.

STEP tangent behavior (from TANGENT_BEHAVIOR.md):
- STEP is an OUT-tangent property (industry standard)
- STEP out-tangent creates a stepped segment: constant at current key's Y, snaps at next key
- The next key's in-tangent is ignored when out-tangent is STEP
- STEP as in-tangent falls back to LINEAR behavior
- Step elbow position: (next_key.time, current_key.value)
"""

import asyncio

import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
from omni import ui

from omni.flux.fcurve.widget import FCurveWidget, FCurve, FCurveKey, TangentType, KeyReference

__all__ = ["TestStepTangents"]


# Test keyframe positions (2 keyframes for simple step tests)
KEY_0_TIME = 0.2
KEY_0_VALUE = 0.3
KEY_1_TIME = 0.8
KEY_1_VALUE = 0.7

# Window dimensions
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 400
CURVE_WIDTH = 400
CURVE_HEIGHT = 280
PADDING = 30


class TestStepTangents(omni.kit.test.AsyncTestCase):
    """Test STEP tangent behavior and step elbow positioning."""

    async def setUp(self):
        """Create window with FCurveWidget."""
        self._continue_clicked = False

        self.window = ui.Window(
            "Test STEP Tangents",
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
        self._continue_clicked = False
        while not self._continue_clicked:
            await asyncio.sleep(0.1)
        self._continue_clicked = False

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

    def _get_curve(self) -> FCurve:
        """Get the test curve from the widget."""
        return self.widget.curves.get("test")

    def _get_step_elbow_position(self, segment_index: int = 0):
        """Get the step elbow position in model coordinates for the given segment."""
        mgr = self.widget._managers.get("test")
        if not mgr or segment_index >= len(mgr._curve_segments):
            return None
        seg = mgr._curve_segments[segment_index]
        if seg._elbow_placer:
            px = float(seg._elbow_placer.offset_x)
            py = float(seg._elbow_placer.offset_y)
            return self.widget.viewport.pixel_to_model(px, py)
        return None

    def _is_step_segment(self, segment_index: int = 0) -> bool:
        """Check if the segment at the given index is rendered as a step."""
        mgr = self.widget._managers.get("test")
        if not mgr or segment_index >= len(mgr._curve_segments):
            return False
        seg = mgr._curve_segments[segment_index]
        return seg._elbow_placer is not None

    # =========================================================================
    # Test 1: STEP out with various in-tangents (one-to-many)
    # =========================================================================
    async def test_step_out_ignores_next_in_tangent(self):
        """STEP out-tangent ignores the next key's in-tangent type.

        Regardless of what the next key's in-tangent is, STEP out governs the segment.
        """
        in_tangent_types = [
            TangentType.LINEAR,
            TangentType.AUTO,
            TangentType.SMOOTH,
            TangentType.FLAT,
            TangentType.CUSTOM,
        ]

        for in_type in in_tangent_types:
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
                                in_tangent_type=in_type,
                            ),
                        ],
                        color=0xFF00FF00,
                    )
                }
            )
            await omni.kit.app.get_app().next_update_async()
            self._set_label(f"STEP(0).out -> {in_type.name}(1).in (STEP governs)")

            # Segment should always be rendered as step
            self.assertTrue(self._is_step_segment(0), f"Segment should be step when out=STEP, in={in_type.name}")

            # Step elbow should be at (KEY_1_TIME, KEY_0_VALUE)
            elbow = self._get_step_elbow_position(0)
            self.assertIsNotNone(elbow, "Step elbow should exist")
            self.assertAlmostEqual(
                elbow[0], KEY_1_TIME, delta=0.01, msg=f"Elbow X should be at KEY_1_TIME with in={in_type.name}"
            )
            self.assertAlmostEqual(
                elbow[1], KEY_0_VALUE, delta=0.01, msg=f"Elbow Y should be at KEY_0_VALUE with in={in_type.name}"
            )

            await self._wait_for_continue()

    # =========================================================================
    # Test 2: STEP in falls back to LINEAR (not a step segment)
    # =========================================================================
    async def test_step_in_falls_back_to_linear(self):
        """STEP as in-tangent falls back to LINEAR, segment is NOT stepped.

        Only STEP out-tangent creates a stepped segment.
        """
        out_tangent_types = [
            TangentType.LINEAR,
            TangentType.AUTO,
            TangentType.SMOOTH,
            TangentType.FLAT,
            TangentType.CUSTOM,
        ]

        for out_type in out_tangent_types:
            self.widget.set_curves(
                {
                    "test": FCurve(
                        id="test",
                        keys=[
                            FCurveKey(
                                time=KEY_0_TIME,
                                value=KEY_0_VALUE,
                                out_tangent_type=out_type,
                            ),
                            FCurveKey(
                                time=KEY_1_TIME,
                                value=KEY_1_VALUE,
                                in_tangent_type=TangentType.STEP,  # Falls back to LINEAR
                            ),
                        ],
                        color=0xFF00FF00,
                    )
                }
            )
            await omni.kit.app.get_app().next_update_async()
            self._set_label(f"{out_type.name}(0).out -> STEP(1).in (STEP->LINEAR, bezier)")

            # Segment should NOT be rendered as step (STEP in falls back to LINEAR)
            self.assertFalse(self._is_step_segment(0), f"Segment should NOT be step when out={out_type.name}, in=STEP")

            await self._wait_for_continue()

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
    # Test 3: Elbow position updates when keyframes move
    # =========================================================================
    async def test_elbow_position_updates_on_keyframe_drag(self):
        """Step elbow position updates correctly when keyframes are dragged."""
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
                            in_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Initial: STEP(0).out -> LINEAR(1).in")

        # Assert initial elbow position
        elbow = self._get_step_elbow_position(0)
        self.assertAlmostEqual(elbow[0], KEY_1_TIME, delta=0.01)
        self.assertAlmostEqual(elbow[1], KEY_0_VALUE, delta=0.01)

        await self._wait_for_continue()

        # Drag Key 0 upward (increase value)
        dy_up = -0.5 * CURVE_HEIGHT
        await self._drag_key(0, 0, dy_up)

        curve = self._get_curve()
        new_key0_value = curve.keys[0].value
        self._set_label(f"Key 0 moved up: value now {new_key0_value:.2f}")

        # Assert elbow Y updated to new Key 0 value
        elbow = self._get_step_elbow_position(0)
        self.assertAlmostEqual(elbow[0], KEY_1_TIME, delta=0.02, msg="Elbow X should still be at KEY_1_TIME")
        self.assertAlmostEqual(elbow[1], new_key0_value, delta=0.05, msg="Elbow Y should update to new KEY_0 value")

        await self._wait_for_continue()

        # Drag Key 1 leftward (decrease time)
        dx_left = -0.3 * CURVE_WIDTH
        await self._drag_key(1, dx_left, 0)

        curve = self._get_curve()
        new_key1_time = curve.keys[1].time
        self._set_label(f"Key 1 moved left: time now {new_key1_time:.2f}")

        # Assert elbow X updated to new Key 1 time
        elbow = self._get_step_elbow_position(0)
        self.assertAlmostEqual(elbow[0], new_key1_time, delta=0.05, msg="Elbow X should update to new KEY_1 time")

    # =========================================================================
    # Test 4: Switching to STEP out-tangent
    # =========================================================================
    async def test_switch_to_step_out(self):
        """Switching out-tangent to STEP should change segment to stepped."""
        # Start with LINEAR out
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
        self._set_label("Initial: LINEAR(0).out -> LINEAR(1).in (bezier)")

        # Should NOT be step initially
        self.assertFalse(self._is_step_segment(0), "Should start as bezier")

        await self._wait_for_continue()

        # Switch Key 0 out-tangent to STEP and rebuild to apply segment type change
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.STEP)
        curve = self._get_curve()
        self.widget.set_curves({"test": curve})
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Switched to STEP(0).out -> LINEAR(1).in (step)")

        self.assertTrue(self._is_step_segment(0), "Should be step after switching to STEP out")

        # Verify elbow position
        elbow = self._get_step_elbow_position(0)
        self.assertAlmostEqual(elbow[0], KEY_1_TIME, delta=0.01)
        self.assertAlmostEqual(elbow[1], KEY_0_VALUE, delta=0.01)

    # =========================================================================
    # Test 5: Switching from STEP out-tangent to other types
    # =========================================================================
    async def test_switch_from_step_out(self):
        """Switching out-tangent from STEP to other types should change to bezier."""
        # Start with STEP out
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
                            in_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Initial: STEP(0).out -> LINEAR(1).in (step)")

        # Should be step initially
        self.assertTrue(self._is_step_segment(0), "Should start as step")

        await self._wait_for_continue()

        # Test switching to various non-STEP types
        other_types = [TangentType.LINEAR, TangentType.AUTO, TangentType.FLAT]
        for i, out_type in enumerate(other_types):
            # Switch tangent type and rebuild to apply segment type change
            self.widget.set_key_tangent_type("test", 0, out_tangent_type=out_type)
            curve = self._get_curve()
            self.widget.set_curves({"test": curve})
            await omni.kit.app.get_app().next_update_async()
            self._set_label(f"Switched to {out_type.name}(0).out (should be bezier, not step)")

            self.assertFalse(self._is_step_segment(0), f"Should be bezier after switching to {out_type.name} out")

            await self._wait_for_continue()

            # Reset to STEP for next type test (if not last)
            if i < len(other_types) - 1:
                self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.STEP)
                curve = self._get_curve()
                self.widget.set_curves({"test": curve})
                await omni.kit.app.get_app().next_update_async()
                self._set_label("Reset to STEP(0).out (step)")

    # =========================================================================
    # Test 6: TDD - set_key_tangent_type should update step rendering
    # =========================================================================
    async def test_set_key_tangent_type_updates_step_rendering(self):
        """
        TDD TEST: set_key_tangent_type alone should update step rendering.

        BUG: Currently, calling set_key_tangent_type to change to/from STEP
        does not update the visual rendering. The workaround is to call
        set_curves() to force a full rebuild, but this should not be necessary.

        This test verifies that set_key_tangent_type correctly updates:
        1. The model (tangent type stored correctly)
        2. The visual rendering (segment changes from bezier to step)

        Expected behavior:
        - After calling set_key_tangent_type(out_tangent_type=TangentType.STEP),
          the segment should immediately render as a step (horizontal + vertical lines)
          without needing to call set_curves() for a full rebuild.
        """
        # Start with LINEAR out-tangent (bezier segment)
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
        self._set_label("Initial: LINEAR(0).out -> LINEAR(1).in (bezier)")

        # Verify initial state: NOT a step segment
        self.assertFalse(self._is_step_segment(0), "Should start as bezier (not step)")

        # Verify model has LINEAR
        curve = self.widget.curves.get("test")
        self.assertEqual(curve.keys[0].out_tangent_type, TangentType.LINEAR, "Model should have LINEAR out-tangent")

        await self._wait_for_continue()

        # ─────────────────────────────────────────────────────────────────────
        # THE TEST: Call set_key_tangent_type WITHOUT set_curves workaround
        # ─────────────────────────────────────────────────────────────────────
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.STEP)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("After set_key_tangent_type: STEP(0).out (should be step)")

        # Verify MODEL updated correctly
        curve = self.widget.curves.get("test")
        self.assertEqual(
            curve.keys[0].out_tangent_type,
            TangentType.STEP,
            "Model should have STEP out-tangent after set_key_tangent_type",
        )

        # Verify VISUAL updated correctly (THIS IS THE BUG - currently fails)
        self.assertTrue(
            self._is_step_segment(0),
            "BUG: Segment should render as step after set_key_tangent_type (currently requires set_curves workaround)",
        )

        # Verify elbow position is correct
        elbow = self._get_step_elbow_position(0)
        self.assertIsNotNone(elbow, "Step elbow should exist after switching to STEP")
        self.assertAlmostEqual(elbow[0], KEY_1_TIME, delta=0.01, msg="Elbow X should be at next key's time")
        self.assertAlmostEqual(elbow[1], KEY_0_VALUE, delta=0.01, msg="Elbow Y should be at current key's value")

        await self._wait_for_continue()

        # ─────────────────────────────────────────────────────────────────────
        # Also test switching back from STEP to LINEAR
        # ─────────────────────────────────────────────────────────────────────
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.LINEAR)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("After set_key_tangent_type: LINEAR(0).out (should be bezier)")

        # Verify MODEL updated correctly
        curve = self.widget.curves.get("test")
        self.assertEqual(
            curve.keys[0].out_tangent_type,
            TangentType.LINEAR,
            "Model should have LINEAR out-tangent after switching back",
        )

        # Verify VISUAL updated correctly
        self.assertFalse(
            self._is_step_segment(0), "BUG: Segment should render as bezier after switching from STEP to LINEAR"
        )

        await self._wait_for_continue()

    # =========================================================================
    # Test: Tangent handle visibility helper
    # =========================================================================

    def _is_in_tangent_visible(self, key_index: int) -> bool:
        """Check if the in-tangent handle at key_index is visible."""
        mgr = self.widget._managers.get("test")
        if not mgr or key_index >= len(mgr._groups):
            return False
        h = mgr._groups[key_index].in_h
        if h is None:
            return False
        return h._model_placer is not None and h._model_placer.visible

    def _is_out_tangent_visible(self, key_index: int) -> bool:
        """Check if the out-tangent handle at key_index is visible."""
        mgr = self.widget._managers.get("test")
        if not mgr or key_index >= len(mgr._groups):
            return False
        h = mgr._groups[key_index].out_h
        if h is None:
            return False
        return h._model_placer is not None and h._model_placer.visible

    # =========================================================================
    # Test: CUSTOM → STEP transition (handle disappears, segment becomes step)
    # =========================================================================

    async def test_custom_to_step_hides_handle_and_changes_segment(self):
        """Switching from CUSTOM to STEP should hide tangent handle and render step segment.

        This tests the transition from a user-controlled bezier tangent to a step tangent.
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
                            out_tangent_y=0.1,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.1,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()

        # Select key 0 to make tangent handles visible
        self.widget.select_keys([KeyReference(curve_id="test", key_index=0)])
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Initial: CUSTOM(0).out selected - handle should be visible")

        # Verify initial state
        self.assertFalse(self._is_step_segment(0), "Should start as bezier")
        self.assertTrue(self._is_out_tangent_visible(0), "CUSTOM out-tangent handle should be visible when selected")

        await self._wait_for_continue()

        # Switch to STEP
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.STEP)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("After: STEP(0).out - handle hidden, segment is step")

        # Verify segment changed to step
        self.assertTrue(self._is_step_segment(0), "Segment should render as step after CUSTOM → STEP")

        # Verify handle is now hidden (STEP hides tangent handles)
        self.assertFalse(self._is_out_tangent_visible(0), "STEP out-tangent handle should be hidden")

        await self._wait_for_continue()

        # Switch back to CUSTOM
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.CUSTOM)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Restored: CUSTOM(0).out - handle visible, segment is bezier")

        # Verify restored state
        self.assertFalse(self._is_step_segment(0), "Segment should render as bezier after STEP → CUSTOM")
        self.assertTrue(self._is_out_tangent_visible(0), "CUSTOM out-tangent handle should be visible again")

        await self._wait_for_continue()

    # =========================================================================
    # Test: Adjacent key in-tangent visibility when out-tangent becomes STEP
    # =========================================================================

    async def test_adjacent_key_in_tangent_hidden_when_prev_out_becomes_step(self):
        """When key[N].out becomes STEP, key[N+1].in-tangent handle should hide.

        Tangent handle visibility depends on BOTH sides of the segment.
        If key[0].out is STEP, then key[1].in-tangent handle should be hidden
        even if key[1].in_tangent_type is CUSTOM (which normally shows handles).
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
                            out_tangent_y=0.1,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.1,
                            out_tangent_type=TangentType.CUSTOM,
                            out_tangent_x=0.1,
                            out_tangent_y=0.1,
                        ),
                        FCurveKey(
                            time=1.0,
                            value=0.8,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.1,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()

        # Select key 1 to make its tangent handles visible
        self.widget.select_keys([KeyReference(curve_id="test", key_index=1)])
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Initial: Key[1] selected, CUSTOM in/out - both handles visible")

        # Verify initial state: key[1]'s in-tangent should be visible
        # (because key[0].out is CUSTOM and key[1].in is CUSTOM)
        self.assertTrue(self._is_in_tangent_visible(1), "Key[1] in-tangent should be visible (CUSTOM-CUSTOM segment)")

        await self._wait_for_continue()

        # Change key[0].out to STEP (key[1] is still selected)
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.STEP)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("After: Key[0].out=STEP - Key[1] in-tangent should hide")

        # Key[1]'s in-tangent should now be hidden because key[0].out is STEP
        # The visibility rule is: visible if (prev.out needs handle OR curr.in needs handle)
        # STEP doesn't need handle, but CUSTOM does - however STEP overrides for that segment
        self.assertTrue(
            self._is_in_tangent_visible(1), "Key[1] in-tangent still visible (CUSTOM type, independent of neighbor)"
        )

        # Key[1]'s out-tangent should still be visible (key[1].out is CUSTOM, middle key)
        self.assertTrue(self._is_out_tangent_visible(1), "Key[1] out-tangent should still be visible (CUSTOM)")

        await self._wait_for_continue()

        # Restore key[0].out to CUSTOM
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.CUSTOM)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Restored: Key[0].out=CUSTOM - Key[1] in-tangent visible again")

        # Key[1]'s in-tangent should be visible again
        self.assertTrue(self._is_in_tangent_visible(1), "Key[1] in-tangent should be visible again after STEP → CUSTOM")

        await self._wait_for_continue()

    # =========================================================================
    # Test: STEP in-tangent hides its own handle but not adjacent out-tangent
    # =========================================================================

    async def test_step_in_tangent_hides_own_handle_not_adjacent(self):
        """STEP in-tangent hides its own handle but NOT the previous key's out-tangent.

        STEP as an in-tangent falls back to LINEAR (documented behavior).
        The segment is NOT stepped - it's still a bezier controlled by key[0].out.
        Therefore:
        - key[1]'s in-tangent handle: hidden (STEP type hides handles)
        - key[0]'s out-tangent handle: visible (CUSTOM type needs handle)
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
                            out_tangent_y=0.1,
                        ),
                        FCurveKey(
                            time=KEY_1_TIME,
                            value=KEY_1_VALUE,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.1,
                            in_tangent_y=-0.1,
                        ),
                    ],
                    color=0xFF00FF00,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()

        # Select key 0 to make its out-tangent handle visible
        self.widget.select_keys([KeyReference(curve_id="test", key_index=0)])
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Initial: Key[0] selected, CUSTOM out - handle visible")

        # Verify initial state
        self.assertTrue(self._is_out_tangent_visible(0), "Key[0] out-tangent should be visible (CUSTOM-CUSTOM segment)")

        await self._wait_for_continue()

        # Change key[1].in to STEP (key[0] is still selected)
        self.widget.set_key_tangent_type("test", 1, in_tangent_type=TangentType.STEP)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("After: Key[1].in=STEP - Key[0] out-tangent STILL visible (not stepped)")

        # Key[0]'s out-tangent should STILL be visible because:
        # - key[0].out is CUSTOM (needs handle)
        # - STEP in-tangent falls back to LINEAR, segment is NOT stepped
        self.assertTrue(
            self._is_out_tangent_visible(0),
            "Key[0] out-tangent should remain visible (STEP in-tangent doesn't step the segment)",
        )

        await self._wait_for_continue()

        # Now select key[1] to check its in-tangent visibility
        self.widget.select_keys([KeyReference(curve_id="test", key_index=1)])
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Key[1] selected - its in-tangent should be hidden (STEP type)")

        self.assertFalse(self._is_in_tangent_visible(1), "Key[1] in-tangent hidden (STEP type hides handles)")

        await self._wait_for_continue()

        # Restore key[1].in to CUSTOM and verify
        self.widget.set_key_tangent_type("test", 1, in_tangent_type=TangentType.CUSTOM)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Restored: Key[1].in=CUSTOM - both tangents visible")

        self.assertTrue(self._is_in_tangent_visible(1), "Key[1] in-tangent should be visible (CUSTOM-CUSTOM)")

        await self._wait_for_continue()

    # =========================================================================
    # Test: Full cycle LINEAR → STEP → CUSTOM → LINEAR
    # =========================================================================

    async def test_full_tangent_type_cycle(self):
        """Test cycling through multiple tangent types to ensure all transitions work.

        Tests: LINEAR → STEP → CUSTOM → FLAT → LINEAR
        Each transition should properly update segment rendering and handle visibility.
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

        # Select key 0
        self.widget.select_keys([KeyReference(curve_id="test", key_index=0)])
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Cycle test: LINEAR (bezier, handles hidden)")

        # Initial: LINEAR (bezier, handles hidden)
        self.assertFalse(self._is_step_segment(0), "LINEAR: should be bezier")
        self.assertFalse(self._is_out_tangent_visible(0), "LINEAR: handles hidden")

        await self._wait_for_continue()

        # → STEP (step, handles hidden)
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.STEP)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Cycle test: STEP (step segment, handles hidden)")

        self.assertTrue(self._is_step_segment(0), "STEP: should be step")
        self.assertFalse(self._is_out_tangent_visible(0), "STEP: handles hidden")

        await self._wait_for_continue()

        # → CUSTOM (bezier, handles visible)
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.CUSTOM)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Cycle test: CUSTOM (bezier, handles visible)")

        self.assertFalse(self._is_step_segment(0), "CUSTOM: should be bezier")
        self.assertTrue(self._is_out_tangent_visible(0), "CUSTOM: handles visible")

        await self._wait_for_continue()

        # → FLAT (bezier, handles visible)
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.FLAT)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Cycle test: FLAT (bezier, handles visible)")

        self.assertFalse(self._is_step_segment(0), "FLAT: should be bezier")
        self.assertFalse(self._is_out_tangent_visible(0), "FLAT: handles hidden (only SMOOTH/CUSTOM show)")

        await self._wait_for_continue()

        # → LINEAR (bezier, handles hidden) - back to start
        self.widget.set_key_tangent_type("test", 0, out_tangent_type=TangentType.LINEAR)
        await omni.kit.app.get_app().next_update_async()
        self._set_label("Cycle test: LINEAR (back to start)")

        self.assertFalse(self._is_step_segment(0), "LINEAR: should be bezier")
        self.assertFalse(self._is_out_tangent_visible(0), "LINEAR: handles hidden")

        await self._wait_for_continue()
