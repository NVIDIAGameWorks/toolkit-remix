"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
"""

import omni.kit
import omni.kit.test
import omni.kit.window.cursor as _window_cursor
import omni.usd
from omni import ui
from omni.flux.utils.widget.hover import CursorShapesEnum, hover_helper
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows, wait_stage_loading


class TestHoverHelper(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.stage = None

    async def _setup_window(self, add_hover_helper=True):
        await arrange_windows(topleft_window="Stage")

        window = ui.Window("TestHoverHelperWindow", height=400, width=800)
        size_manipulator_height = 4

        with window.frame:
            self._slide_placer = ui.Placer(
                draggable=True,
                height=size_manipulator_height,
            )
            # Body
            with self._slide_placer:
                self._slider_manip = ui.Rectangle(
                    width=ui.Percent(50),
                    name="TestManipulator",
                )
        self.assertIsNotNone(window)
        self.assertIsNotNone(self._slider_manip)

        if add_hover_helper:
            hover_helper(self._slider_manip)

        return window, self._slider_manip

    async def test_cursor_hover(self):
        window, scrollbar = await self._setup_window(add_hover_helper=False)
        await ui_test.human_delay(1)

        # Get a reference to the scrollbar
        ui_scroll = ui_test.find(f"{window.title}//Frame/**/Rectangle[*].name=='TestManipulator'")
        self.assertIsNotNone(ui_scroll)
        mouse_move_to = ui_scroll.position

        # Move mouse over the scrollbar
        await ui_test.emulate_mouse_move(mouse_move_to)
        await ui_test.human_delay(1)

        expected_normal_shape = CursorShapesEnum.ARROW.value
        expected_hovering_shape = CursorShapesEnum.HAND.value
        cursor = _window_cursor.get_main_window_cursor()

        # Move the mouse away
        away_position = ui_test.Vec2(window.position_x + 32, window.position_y + 32)
        await ui_test.emulate_mouse_move(away_position)
        await ui_test.human_delay(1)
        shape = cursor.get_cursor_shape_override()
        self.assertEqual(expected_normal_shape, shape)

        # Move mouse back over the scrollbar, and show that the cursor isn't changed
        await ui_test.emulate_mouse_move(mouse_move_to)
        await ui_test.human_delay(1)
        shape = cursor.get_cursor_shape_override()
        self.assertEqual(expected_normal_shape, shape)

        # Now run the hover helper on the scrollbar
        hover_helper(scrollbar)

        # Move the mouse away
        away_position = ui_test.Vec2(window.position_x + 32, window.position_y + 32)
        await ui_test.emulate_mouse_move(away_position)
        await ui_test.human_delay(1)

        # Move mouse back over the scrollbar, and show that the cursor has changed.
        await ui_test.emulate_mouse_move(mouse_move_to)
        await ui_test.human_delay(1)
        shape = cursor.get_cursor_shape_override()
        self.assertEqual(expected_hovering_shape, shape)

        # Move the mouse away again, and verify that the cursor has changed back
        end_pos = ui_test.Vec2(0, 0)
        await ui_test.emulate_mouse_drag_and_drop(mouse_move_to, end_pos, right_click=False, human_delay_speed=1)
        await ui_test.human_delay(1)
        shape = cursor.get_cursor_shape_override()
        self.assertEqual(expected_normal_shape, shape)

        # Tear down the widget
        scrollbar.destroy()
        window.destroy()

    async def test_cursor_drag_release(self):
        window, _ = await self._setup_window(add_hover_helper=True)
        await ui_test.human_delay(1)

        # Get a reference to the scrollbar
        ui_scroll = ui_test.find(f"{window.title}//Frame/**/Rectangle[*].name=='TestManipulator'")
        self.assertIsNotNone(ui_scroll)
        scroll_pos = ui_scroll.position

        expected_normal_shape = CursorShapesEnum.ARROW.value
        expected_hovering_shape = CursorShapesEnum.HAND.value
        cursor = _window_cursor.get_main_window_cursor()

        # Move mouse over the scrollbar
        await ui_test.emulate_mouse_move(scroll_pos)
        await ui_test.human_delay(1)
        # Verify that the cursor indicates a hover
        shape = cursor.get_cursor_shape_override()
        self.assertEqual(expected_hovering_shape, shape)

        # Simulate a mouse click and release without moving the mouse off the scrollbar
        await ui_test.emulate_mouse_drag_and_drop(scroll_pos, scroll_pos, right_click=False, human_delay_speed=4)
        await ui_test.human_delay(1)
        # Verify that the cursor still indicates hovering
        shape = cursor.get_cursor_shape_override()
        self.assertEqual(expected_hovering_shape, shape)

        # Now simulate a mouse click and release that moves the mouse off the scrollbar
        end_pos = ui_test.Vec2(0, 0)
        await ui_test.emulate_mouse_drag_and_drop(scroll_pos, end_pos, right_click=False, human_delay_speed=4)
        await ui_test.human_delay(1)
        # Verify that the cursor no longer indicates hovering
        shape = cursor.get_cursor_shape_override()
        self.assertEqual(expected_normal_shape, shape)
