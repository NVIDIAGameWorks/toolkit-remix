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

E2E Test for infinity curve rendering and keyframe dragging.

This test simulates how a client (like the Grid panel) would embed the
FCurveWidget. The client is responsible for constraining the widget using
clipping containers, following the same pattern as the original curve editor:
- VStack with content_clipping=True wraps the content
- Frame with horizontal_clipping and vertical_clipping constrains the curves
- HStack with content_clipping=True for the curve area

The test uses keyframes at the boundaries (0.0 and 1.0) to verify that
infinity lines render beyond the curve bounds but within the clipping window.
"""

import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
from omni import ui

from omni.flux.fcurve.widget import FCurveWidget, FCurve, FCurveKey, InfinityType, TangentType
from omni.flux.fcurve.widget._internal.math import Vector2

__all__ = ["TestInfinityCurves"]

_FAR = 10000.0

# Window and layout dimensions
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 400
CLIP_FRAME_WIDTH = 400  # Clipping container size
CLIP_FRAME_HEIGHT = 300
CURVE_WIDTH = 300  # Actual curve widget size (smaller)
CURVE_HEIGHT = 200
OUTER_PADDING = 50  # Padding around the clipping frame
INNER_PADDING = 50  # Padding inside clipping frame around curve


class TestInfinityCurves(omni.kit.test.AsyncTestCase):
    """Test infinity curve rendering updates when keyframes are dragged."""

    async def setUp(self):
        """Create window with FCurveWidget in a clipping container."""
        self._continue_clicked = False

        self.window = ui.Window(
            "Test Infinity Curves",
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
                # Curve area with clipping frame for infinity rendering
                # The outer Frame clips infinity curves at its boundary (400x300)
                # The widget is positioned with padding so infinity extends into padding area
                with ui.HStack():
                    ui.Spacer(width=OUTER_PADDING)
                    with ui.Frame(
                        width=ui.Pixel(CLIP_FRAME_WIDTH),
                        height=ui.Pixel(CLIP_FRAME_HEIGHT),
                    ):
                        # content_clipping=True clips infinity lines without showing scrollbars
                        with ui.ZStack(content_clipping=True):
                            # Dark background for entire clip frame
                            ui.Rectangle(style={"background_color": 0xFF0A0A0A})
                            # Position the widget with padding using absolute positioning
                            with ui.Placer(offset_x=INNER_PADDING, offset_y=INNER_PADDING):
                                with ui.ZStack(
                                    width=ui.Pixel(CURVE_WIDTH),
                                    height=ui.Pixel(CURVE_HEIGHT),
                                ):
                                    # Darker background for curve area
                                    ui.Rectangle(style={"background_color": 0xFF1A1A1A})
                                    # FCurveWidget doesn't clip internally - the outer
                                    # ZStack with content_clipping=True handles clipping
                                    self.widget = FCurveWidget(
                                        time_range=(0.0, 1.0),
                                        value_range=(0.0, 1.0),
                                        viewport_size=(CURVE_WIDTH, CURVE_HEIGHT),
                                    )
                    ui.Spacer(width=OUTER_PADDING)
                ui.Spacer(height=OUTER_PADDING)

        await omni.kit.app.get_app().next_update_async()

    def _on_continue_clicked(self):
        self._continue_clicked = True

    def _set_label(self, text: str):
        """Set the label text to describe the current test configuration."""
        self._label.text = text

    async def _wait_for_continue(self):
        """
        Wait for the continue button to be clicked.

        To enable interactive debugging, comment out the return statement
        and uncomment the loop below.
        """
        return
        # self._continue_clicked = False
        # while not self._continue_clicked:
        # await asyncio.sleep(0.1)
        # self._continue_clicked = False

    async def tearDown(self):
        await self._wait_for_continue()  # Wait for button click before cleanup
        if self.widget:
            self.widget.destroy()
            self.widget = None
        if self.window:
            self.window.destroy()
            self.window = None

    def _get_infinity_positions(self):
        """Get all four infinity positions: (pre_far, pre_near, post_near, post_far)."""
        mgr = self.widget._managers["test"]
        pre = mgr._pre_infinity
        post = mgr._post_infinity
        self.assertIsNotNone(pre, "Pre-infinity widget should exist")
        self.assertIsNotNone(post, "Post-infinity widget should exist")
        pre_far = (float(pre._far_placer.offset_x), float(pre._far_placer.offset_y))
        pre_near = pre._handle.position
        post_near = post._handle.position
        post_far = (float(post._far_placer.offset_x), float(post._far_placer.offset_y))
        return pre_far, pre_near, post_near, post_far

    def _expected_infinity_far(self, is_pre: bool, mode: InfinityType):
        """Compute the expected far-point of a pre/post infinity line (matches InfinityCurveWidget.update)."""
        mgr = self.widget._managers["test"]
        keys = self.widget.curves["test"].keys
        vp = mgr._vp

        if is_pre:
            k = keys[0]
            key_pos = Vector2(*mgr._groups[0].key_h.position)
            tangent_pos = Vector2(*vp.model_to_pixel(k.time + k.out_tangent_x, k.value + k.out_tangent_y))
        else:
            k = keys[-1]
            key_pos = Vector2(*mgr._groups[-1].key_h.position)
            tangent_pos = Vector2(*vp.model_to_pixel(k.time + k.in_tangent_x, k.value + k.in_tangent_y))

        tangent = tangent_pos - key_pos

        if mode == InfinityType.LINEAR:
            pos = key_pos - tangent.normalized() * _FAR
        else:
            pos = key_pos - Vector2(tangent.x, 0.0).normalized() * _FAR
        return pos.x, pos.y

    async def _drag_key(self, key_index: int, dx: float, dy: float):
        """Drag a keyframe by the given delta."""
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
    # LINEAR Infinity Tests
    # =========================================================================

    async def test_linear_infinity_two_keys_drag_first(self):
        """Drag first keyframe with LINEAR infinity and verify slope updates."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=0.0, value=0.3),
                        FCurveKey(time=1.0, value=0.7),
                    ],
                    color=0xFF00FF00,
                    pre_infinity=InfinityType.LINEAR,
                    post_infinity=InfinityType.LINEAR,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("LINEAR infinity: 2 keys, drag first")
        await self._wait_for_continue()

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.LINEAR)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=1.0)
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=1.0)
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=1.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=1.0)

        await self._drag_key(0, dx=50, dy=-30)

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.LINEAR)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=2.0)
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=2.0)
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=2.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=2.0)

        # Verify model updated
        keys = self.widget.curves["test"].keys
        self.assertAlmostEqual(keys[0].time, 0.1653, delta=0.01)
        self.assertAlmostEqual(keys[0].value, 0.452, delta=0.01)
        self.assertAlmostEqual(keys[1].time, 1.0, delta=0.001)
        self.assertAlmostEqual(keys[1].value, 0.7, delta=0.001)

    async def test_linear_infinity_three_keys_drag_middle(self):
        """Drag middle keyframe with LINEAR infinity and AUTO tangents."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.0, value=0.3, in_tangent_type=TangentType.AUTO, out_tangent_type=TangentType.AUTO
                        ),
                        FCurveKey(
                            time=0.5, value=0.9, in_tangent_type=TangentType.AUTO, out_tangent_type=TangentType.AUTO
                        ),
                        FCurveKey(
                            time=1.0, value=0.7, in_tangent_type=TangentType.AUTO, out_tangent_type=TangentType.AUTO
                        ),
                    ],
                    color=0xFF00FF00,
                    pre_infinity=InfinityType.LINEAR,
                    post_infinity=InfinityType.LINEAR,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("LINEAR infinity: 3 keys AUTO, drag middle")
        await self._wait_for_continue()

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.LINEAR)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=1.0)
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=1.0)
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=1.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=1.0)

        # Drag middle key down to ~Y=0.05 (170px down from Y=0.9)
        await self._drag_key(1, dx=0, dy=170)

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.LINEAR)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=2.0)
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=2.0)
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=2.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=2.0)

    # =========================================================================
    # CONSTANT Infinity Tests
    # =========================================================================

    async def test_constant_infinity_two_keys_drag_first(self):
        """Drag first keyframe with CONSTANT infinity - lines stay horizontal."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=0.0, value=0.3),
                        FCurveKey(time=1.0, value=0.7),
                    ],
                    color=0xFF00FF00,
                    pre_infinity=InfinityType.CONSTANT,
                    post_infinity=InfinityType.CONSTANT,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CONSTANT infinity: 2 keys, drag first")
        await self._wait_for_continue()

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=1.0)
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=1.0)
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=1.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=1.0)

        await self._drag_key(0, dx=50, dy=-30)

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=2.0)
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=2.0)
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=2.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=2.0)

    async def test_constant_infinity_three_keys_drag_middle(self):
        """Drag middle keyframe with CONSTANT infinity - lines stay horizontal."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.0, value=0.3, in_tangent_type=TangentType.AUTO, out_tangent_type=TangentType.AUTO
                        ),
                        FCurveKey(
                            time=0.5, value=0.9, in_tangent_type=TangentType.AUTO, out_tangent_type=TangentType.AUTO
                        ),
                        FCurveKey(
                            time=1.0, value=0.7, in_tangent_type=TangentType.AUTO, out_tangent_type=TangentType.AUTO
                        ),
                    ],
                    color=0xFF00FF00,
                    pre_infinity=InfinityType.CONSTANT,
                    post_infinity=InfinityType.CONSTANT,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CONSTANT infinity: 3 keys AUTO, drag middle")
        await self._wait_for_continue()

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=1.0)
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=1.0)
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=1.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=1.0)

        # Drag middle key down
        await self._drag_key(1, dx=0, dy=170)

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=2.0)
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=2.0)
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=2.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=2.0)

    # =========================================================================
    # STEP/FLAT Tangent Override Tests
    # STEP and FLAT tangent types force infinity to behave as CONSTANT
    # Pre-infinity depends on first key's OUT tangent
    # Post-infinity depends on last key's IN tangent
    # =========================================================================

    async def test_first_key_step_forces_constant_pre_infinity(self):
        """First key with STEP out_tangent forces pre-infinity to be horizontal (like CONSTANT)."""
        # Start with LINEAR infinity but STEP tangent on first key
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.0, value=0.3, out_tangent_type=TangentType.STEP
                        ),  # Forces pre-infinity horizontal
                        FCurveKey(time=1.0, value=0.7),
                    ],
                    color=0xFF00FF00,
                    pre_infinity=InfinityType.LINEAR,  # Should be overridden by STEP
                    post_infinity=InfinityType.LINEAR,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("STEP out on first key forces CONSTANT pre-infinity")
        await self._wait_for_continue()

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre_const = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post_const = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre_const[0], delta=1.0, msg="Pre should be horizontal (STEP)")
        self.assertAlmostEqual(pre_0[1], exp_pre_const[1], delta=1.0, msg="Pre should be horizontal (STEP)")
        self.assertAlmostEqual(post_1[0], exp_post_const[0], delta=1.0, msg="Post should be horizontal (STEP segment)")
        self.assertAlmostEqual(post_1[1], exp_post_const[1], delta=1.0, msg="Post should be horizontal (STEP segment)")

        # Drag second key up
        await self._drag_key(1, dx=0, dy=-50)
        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre_const = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post_const = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre_const[0], delta=2.0, msg="Pre still horizontal")
        self.assertAlmostEqual(pre_0[1], exp_pre_const[1], delta=2.0, msg="Pre still horizontal")
        self.assertAlmostEqual(post_1[0], exp_post_const[0], delta=2.0, msg="Post still horizontal (STEP)")
        self.assertAlmostEqual(post_1[1], exp_post_const[1], delta=2.0, msg="Post still horizontal (STEP)")

        # Switch to CONSTANT infinity (was already effectively constant due to STEP segment)
        self.widget.set_curve_infinity("test", InfinityType.CONSTANT, InfinityType.CONSTANT)
        await omni.kit.app.get_app().next_update_async()
        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre_const = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post_const = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre_const[0], delta=2.0, msg="Pre still horizontal")
        self.assertAlmostEqual(pre_0[1], exp_pre_const[1], delta=2.0, msg="Pre still horizontal")
        self.assertAlmostEqual(post_1[0], exp_post_const[0], delta=2.0, msg="Post horizontal at second key Y")
        self.assertAlmostEqual(post_1[1], exp_post_const[1], delta=2.0, msg="Post horizontal at second key Y")

        # Drag second key down
        await self._drag_key(1, dx=0, dy=80)
        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre_const = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post_const = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre_const[0], delta=2.0)
        self.assertAlmostEqual(pre_0[1], exp_pre_const[1], delta=2.0)
        self.assertAlmostEqual(post_1[0], exp_post_const[0], delta=2.0, msg="Post horizontal at new Y")
        self.assertAlmostEqual(post_1[1], exp_post_const[1], delta=2.0, msg="Post horizontal at new Y")

    async def test_last_key_step_in_is_noop_post_infinity(self):
        """STEP on in_tangent is a no-op — only out_tangent controls segment shape.

        Setting in_tangent_type=STEP on the last key should NOT force post-infinity
        horizontal. The tangent falls back to LINEAR, so post-infinity follows the slope.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=0.0, value=0.3),
                        FCurveKey(
                            time=1.0, value=0.7, in_tangent_type=TangentType.STEP
                        ),  # No-op: STEP on in_tangent falls back to LINEAR
                    ],
                    color=0xFF00FF00,
                    pre_infinity=InfinityType.LINEAR,
                    post_infinity=InfinityType.LINEAR,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("STEP in on last key is no-op: post-infinity still LINEAR")
        await self._wait_for_continue()

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.LINEAR)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=1.0, msg="Pre should have LINEAR slope")
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=1.0, msg="Pre should have LINEAR slope")
        self.assertAlmostEqual(
            post_1[0], exp_post[0], delta=1.0, msg="Post should have LINEAR slope (STEP in is no-op)"
        )
        self.assertAlmostEqual(
            post_1[1], exp_post[1], delta=1.0, msg="Post should have LINEAR slope (STEP in is no-op)"
        )

        # Drag first key up — both slopes should update
        await self._drag_key(0, dx=0, dy=-50)
        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.LINEAR)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=2.0, msg="Pre slope updated")
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=2.0, msg="Pre slope updated")
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=2.0, msg="Post slope updated (still LINEAR)")
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=2.0, msg="Post slope updated (still LINEAR)")

    async def test_first_key_flat_forces_constant_pre_infinity(self):
        """First key with FLAT out_tangent forces pre-infinity to be horizontal (like CONSTANT)."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.0, value=0.3, out_tangent_type=TangentType.FLAT
                        ),  # Forces pre-infinity horizontal
                        FCurveKey(time=1.0, value=0.7),
                    ],
                    color=0xFF00FF00,
                    pre_infinity=InfinityType.LINEAR,  # Should be overridden by FLAT
                    post_infinity=InfinityType.LINEAR,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("FLAT out on first key forces CONSTANT pre-infinity")
        await self._wait_for_continue()

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre_const = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)

        self.assertAlmostEqual(pre_0[0], exp_pre_const[0], delta=1.0, msg="Pre should be horizontal (FLAT)")
        self.assertAlmostEqual(pre_0[1], exp_pre_const[1], delta=1.0, msg="Pre should be horizontal (FLAT)")
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=1.0, msg="Post should have LINEAR slope")
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=1.0, msg="Post should have LINEAR slope")

        # Drag second key up
        await self._drag_key(1, dx=0, dy=-50)
        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre_const = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)

        self.assertAlmostEqual(pre_0[0], exp_pre_const[0], delta=2.0, msg="Pre still horizontal")
        self.assertAlmostEqual(pre_0[1], exp_pre_const[1], delta=2.0, msg="Pre still horizontal")
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=2.0, msg="Post slope changed")
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=2.0, msg="Post slope changed")

        # Switch to CONSTANT infinity
        self.widget.set_curve_infinity("test", InfinityType.CONSTANT, InfinityType.CONSTANT)
        await omni.kit.app.get_app().next_update_async()
        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre_const = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post_const = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre_const[0], delta=2.0, msg="Pre still horizontal")
        self.assertAlmostEqual(pre_0[1], exp_pre_const[1], delta=2.0, msg="Pre still horizontal")
        self.assertAlmostEqual(post_1[0], exp_post_const[0], delta=2.0, msg="Post now horizontal")
        self.assertAlmostEqual(post_1[1], exp_post_const[1], delta=2.0, msg="Post now horizontal")

        # Drag second key down
        await self._drag_key(1, dx=0, dy=80)
        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre_const = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post_const = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre_const[0], delta=2.0)
        self.assertAlmostEqual(pre_0[1], exp_pre_const[1], delta=2.0)
        self.assertAlmostEqual(post_1[0], exp_post_const[0], delta=2.0, msg="Post horizontal at new Y")
        self.assertAlmostEqual(post_1[1], exp_post_const[1], delta=2.0, msg="Post horizontal at new Y")

    async def test_last_key_flat_forces_constant_post_infinity(self):
        """Last key with FLAT in_tangent forces post-infinity to be horizontal (like CONSTANT)."""
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=0.0, value=0.3),
                        FCurveKey(
                            time=1.0, value=0.7, in_tangent_type=TangentType.FLAT
                        ),  # Forces post-infinity horizontal
                    ],
                    color=0xFF00FF00,
                    pre_infinity=InfinityType.LINEAR,
                    post_infinity=InfinityType.LINEAR,  # Should be overridden by FLAT
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("FLAT in on last key forces CONSTANT post-infinity")
        await self._wait_for_continue()

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.LINEAR)
        exp_post_const = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=1.0, msg="Pre should have LINEAR slope")
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=1.0, msg="Pre should have LINEAR slope")
        self.assertAlmostEqual(post_1[0], exp_post_const[0], delta=1.0, msg="Post should be horizontal (FLAT)")
        self.assertAlmostEqual(post_1[1], exp_post_const[1], delta=1.0, msg="Post should be horizontal (FLAT)")

        # Drag first key up
        await self._drag_key(0, dx=0, dy=-50)
        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.LINEAR)
        exp_post_const = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=2.0, msg="Pre slope less steep")
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=2.0, msg="Pre slope less steep")
        self.assertAlmostEqual(post_1[0], exp_post_const[0], delta=2.0, msg="Post still horizontal")
        self.assertAlmostEqual(post_1[1], exp_post_const[1], delta=2.0, msg="Post still horizontal")

        # Switch to CONSTANT infinity
        self.widget.set_curve_infinity("test", InfinityType.CONSTANT, InfinityType.CONSTANT)
        await omni.kit.app.get_app().next_update_async()
        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre_const = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post_const = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre_const[0], delta=2.0, msg="Pre now horizontal")
        self.assertAlmostEqual(pre_0[1], exp_pre_const[1], delta=2.0, msg="Pre now horizontal")
        self.assertAlmostEqual(post_1[0], exp_post_const[0], delta=2.0, msg="Post still horizontal")
        self.assertAlmostEqual(post_1[1], exp_post_const[1], delta=2.0, msg="Post still horizontal")

        # Drag first key down
        await self._drag_key(0, dx=0, dy=80)
        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre_const = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post_const = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre_const[0], delta=2.0)
        self.assertAlmostEqual(pre_0[1], exp_pre_const[1], delta=2.0, msg="Pre horizontal at new Y")
        self.assertAlmostEqual(post_1[0], exp_post_const[0], delta=2.0)
        self.assertAlmostEqual(post_1[1], exp_post_const[1], delta=2.0)

    # =========================================================================
    # SMOOTH and CUSTOM Tangent Tests
    # Tests that verify tangent handle manipulation affects infinity curves
    # =========================================================================

    def _get_tangent_widget(self, key_index: int, is_in_tangent: bool):
        """Get a tangent handle widget from the manager."""
        mgr = self.widget._managers.get("test")
        if not mgr or key_index >= len(mgr._groups):
            return None
        g = mgr._groups[key_index]
        return g.in_h if is_in_tangent else g.out_h

    async def _select_key(self, key_index: int):
        """Ensure a keyframe is selected (makes tangent handles visible).

        Skips the click if already selected to avoid toggling it off.
        """
        mgr = self.widget._managers["test"]
        handle = mgr.key_handles[key_index]
        if handle.selected:
            return
        click_pos = ui_test.Vec2(*handle.screen_center)
        await ui_test.input.emulate_mouse_move(click_pos)
        await ui_test.human_delay(3)
        await ui_test.emulate_mouse_click()
        await ui_test.human_delay(3)
        await omni.kit.app.get_app().next_update_async()

    async def _drag_tangent(self, tangent_handle, dx: float, dy: float):
        """Drag a tangent handle by the given delta."""
        start_pos = ui_test.Vec2(*tangent_handle.screen_center)
        end_pos = start_pos + ui_test.Vec2(dx, dy)

        await ui_test.input.emulate_mouse_move(start_pos)
        await ui_test.human_delay(3)
        await ui_test.emulate_mouse_drag_and_drop(start_pos, end_pos)
        await ui_test.human_delay(3)
        await omni.kit.app.get_app().next_update_async()

    async def test_smooth_tangent_affects_post_infinity(self):
        """SMOOTH tangent on last key affects post-infinity slope via mouse gestures."""
        # Start with 2 LINEAR keyframes - last key not at top to leave room for tangent
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=0.0, value=0.3),
                        FCurveKey(
                            time=1.0, value=0.6, in_tangent_type=TangentType.SMOOTH
                        ),  # SMOOTH allows tangent manipulation
                    ],
                    color=0xFF00FF00,
                    pre_infinity=InfinityType.LINEAR,
                    post_infinity=InfinityType.LINEAR,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("SMOOTH in on last key: drag tangent affects post-infinity")
        await self._wait_for_continue()

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)

        self.assertAlmostEqual(post_1[0], exp_post[0], delta=1.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=1.0)

        # Select the last keyframe to make tangent handles visible
        await self._select_key(1)

        in_tangent = self._get_tangent_widget(1, is_in_tangent=True)
        self.assertIsNotNone(in_tangent, "Last key should have IN tangent widget for SMOOTH")

        key = self.widget.curves["test"].keys[1]
        self.assertAlmostEqual(key.in_tangent_x, -0.5000, delta=0.01)
        self.assertAlmostEqual(key.in_tangent_y, 0.0000, delta=0.01)

        # STEP 1: Drag tangent handle up-left (makes post-infinity go upward)
        await self._drag_tangent(in_tangent, dx=-30, dy=-40)

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)
        key = self.widget.curves["test"].keys[1]

        self.assertAlmostEqual(key.in_tangent_x, -0.334, delta=0.02)
        self.assertAlmostEqual(key.in_tangent_y, 0.1116, delta=0.02)
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=1.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=1.0)

        # STEP 2: Drag keyframe down
        await self._drag_key(1, dx=0, dy=40)

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.LINEAR)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=2.0)
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=2.0)
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=2.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=2.0)

        # Re-select keyframe and re-fetch tangent handle (rebuilt after keyframe drag)
        await self._select_key(1)
        in_tangent = self._get_tangent_widget(1, is_in_tangent=True)
        self.assertIsNotNone(in_tangent, "Last key should have IN tangent widget after re-select")

        # STEP 3: Drag tangent handle down-right (makes post-infinity go downward)
        await self._drag_tangent(in_tangent, dx=30, dy=50)

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)
        key = self.widget.curves["test"].keys[1]

        self.assertLess(key.in_tangent_x, -0.001, "IN tangent X should be negative after drag")
        self.assertNotAlmostEqual(key.in_tangent_y, 0.0, delta=0.001, msg="IN tangent Y should be non-zero after drag")
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=2.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=2.0)

    async def test_custom_tangent_affects_post_infinity(self):
        """CUSTOM tangent on last key affects post-infinity slope via mouse gestures."""
        # Start with 2 LINEAR keyframes - last key not at top
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=0.0, value=0.3),
                        FCurveKey(
                            time=1.0,
                            value=0.6,
                            in_tangent_type=TangentType.CUSTOM,
                            in_tangent_x=-0.3,  # Initial custom tangent pointing left-up
                            in_tangent_y=0.1,
                        ),
                    ],
                    color=0xFF00FF00,
                    pre_infinity=InfinityType.LINEAR,
                    post_infinity=InfinityType.LINEAR,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("CUSTOM in on last key: drag tangent affects post-infinity")
        await self._wait_for_continue()

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)

        self.assertAlmostEqual(post_1[0], exp_post[0], delta=1.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=1.0)

        # Select the last keyframe to make tangent handles visible
        await self._select_key(1)

        in_tangent = self._get_tangent_widget(1, is_in_tangent=True)
        self.assertIsNotNone(in_tangent, "Last key should have IN tangent widget for CUSTOM")

        key = self.widget.curves["test"].keys[1]
        self.assertAlmostEqual(key.in_tangent_x, -0.3000, delta=0.01)
        self.assertAlmostEqual(key.in_tangent_y, 0.1000, delta=0.01)

        # STEP 1: Drag tangent handle to steep up-left angle
        await self._drag_tangent(in_tangent, dx=-40, dy=-60)

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)
        key = self.widget.curves["test"].keys[1]

        self.assertAlmostEqual(key.in_tangent_x, -0.4333, delta=0.02)
        self.assertAlmostEqual(key.in_tangent_y, 0.4000, delta=0.02)
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=2.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=2.0)

        # STEP 2: Drag keyframe up
        await self._drag_key(1, dx=0, dy=-30)

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.LINEAR)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)
        key = self.widget.curves["test"].keys[1]

        self.assertAlmostEqual(key.in_tangent_x, -0.2687, delta=0.02)
        self.assertAlmostEqual(key.in_tangent_y, 0.2480, delta=0.02)
        self.assertAlmostEqual(key.value, 0.7520, delta=0.02)
        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=2.0)
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=2.0)
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=2.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=2.0)

        # Re-select keyframe and re-fetch tangent handle (rebuilt after keyframe drag)
        await self._select_key(1)
        in_tangent = self._get_tangent_widget(1, is_in_tangent=True)
        self.assertIsNotNone(in_tangent, "Last key should have IN tangent widget after re-select")

        # STEP 3: Drag tangent handle to shallow down-right angle
        await self._drag_tangent(in_tangent, dx=50, dy=80)

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)
        key = self.widget.curves["test"].keys[1]

        self.assertLess(key.in_tangent_y, 0.2480, msg="Y should be lower after dragging down")
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=2.0)
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=2.0)

    # =========================================================================
    # STEP Incoming Segment Tests
    # When the segment BEFORE the boundary key is STEP, the boundary key's
    # in-tangent has no visual effect. Infinity should fall back to CONSTANT.
    # =========================================================================

    async def test_step_incoming_segment_forces_constant_post_infinity(self):
        """Post-infinity should be CONSTANT when incoming segment is STEP.

        When keys[-2].out is STEP, the segment before the last key is stepped.
        This means the last key's in-tangent has no visual effect (the curve
        holds at keys[-2].value and snaps at keys[-1].time).
        Therefore, post-infinity LINEAR should fall back to CONSTANT.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=0.0, value=0.3, out_tangent_type=TangentType.LINEAR),
                        FCurveKey(
                            time=0.5, value=0.5, in_tangent_type=TangentType.LINEAR, out_tangent_type=TangentType.STEP
                        ),  # STEP makes next segment stepped
                        FCurveKey(
                            time=1.0, value=0.8, in_tangent_type=TangentType.LINEAR
                        ),  # This is ignored due to STEP
                    ],
                    color=0xFF00FF00,
                    pre_infinity=InfinityType.LINEAR,
                    post_infinity=InfinityType.LINEAR,  # Should behave as CONSTANT
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("STEP incoming segment forces CONSTANT post-infinity")
        await self._wait_for_continue()

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre = self._expected_infinity_far(is_pre=True, mode=InfinityType.LINEAR)
        exp_post_const = self._expected_infinity_far(is_pre=False, mode=InfinityType.CONSTANT)

        self.assertAlmostEqual(pre_0[0], exp_pre[0], delta=1.0, msg="Pre should have LINEAR slope")
        self.assertAlmostEqual(pre_0[1], exp_pre[1], delta=1.0, msg="Pre should have LINEAR slope")
        self.assertAlmostEqual(post_1[0], exp_post_const[0], delta=1.0, msg="Post horizontal (STEP segment)")
        self.assertAlmostEqual(post_1[1], exp_post_const[1], delta=1.0, msg="Post horizontal (STEP segment)")

        await self._wait_for_continue()

        # Change second key's out_tangent from STEP to LINEAR
        self.widget.set_key_tangent_type("test", 1, out_tangent_type=TangentType.LINEAR)
        await omni.kit.app.get_app().next_update_async()

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)

        self.assertAlmostEqual(post_1[0], exp_post[0], delta=1.0, msg="Post should have LINEAR slope now")
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=1.0, msg="Post should have LINEAR slope now")

        await self._wait_for_continue()

    async def test_step_outgoing_segment_forces_constant_pre_infinity(self):
        """Pre-infinity is already CONSTANT when first key's out is STEP (existing behavior).

        This test verifies that when keys[0].out is STEP, pre-infinity is horizontal.
        This is the existing behavior that should be maintained.
        """
        self.widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=0.0, value=0.3, out_tangent_type=TangentType.STEP),  # STEP out-tangent
                        FCurveKey(
                            time=0.5, value=0.6, in_tangent_type=TangentType.LINEAR, out_tangent_type=TangentType.LINEAR
                        ),
                        FCurveKey(time=1.0, value=0.8, in_tangent_type=TangentType.LINEAR),
                    ],
                    color=0xFF00FF00,
                    pre_infinity=InfinityType.LINEAR,  # Should behave as CONSTANT
                    post_infinity=InfinityType.LINEAR,
                )
            }
        )
        await omni.kit.app.get_app().next_update_async()
        self._set_label("STEP outgoing segment forces CONSTANT pre-infinity")
        await self._wait_for_continue()

        pre_0, pre_1, post_0, post_1 = self._get_infinity_positions()
        exp_pre_const = self._expected_infinity_far(is_pre=True, mode=InfinityType.CONSTANT)
        exp_post = self._expected_infinity_far(is_pre=False, mode=InfinityType.LINEAR)

        self.assertAlmostEqual(pre_0[0], exp_pre_const[0], delta=1.0, msg="Pre horizontal (STEP out)")
        self.assertAlmostEqual(pre_0[1], exp_pre_const[1], delta=1.0, msg="Pre horizontal (STEP out)")
        self.assertAlmostEqual(post_1[0], exp_post[0], delta=1.0, msg="Post should have LINEAR slope")
        self.assertAlmostEqual(post_1[1], exp_post[1], delta=1.0, msg="Post should have LINEAR slope")

        await self._wait_for_continue()
