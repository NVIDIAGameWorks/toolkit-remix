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
"""

__all__ = ("TestIntDragFieldGroup",)

import uuid

import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardInput
from omni.flux.property_widget_builder.delegates.int_value.drag import IntDragFieldGroup

from .mocks import MockItem


class TestIntDragFieldGroup(omni.kit.test.AsyncTestCase):
    """E2E tests for IntDragFieldGroup widget rendering."""

    async def test_build_drag_widget_creates_int_drag(self):
        """build_ui should produce ui.IntDrag widgets."""
        window = ui.Window(
            f"TestIntDrag_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[25])
        field = IntDragFieldGroup(min_value=0, max_value=100)

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(widgets), 1)
        self.assertIsInstance(widgets[0], ui.IntDrag)

        for w in widgets:
            w.destroy()
        window.destroy()

    async def test_build_unbounded_creates_int_drag(self):
        """build_ui with no bounds should still produce a ui.IntDrag."""
        window = ui.Window(
            f"TestIntDrag_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[25])
        field = IntDragFieldGroup()

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(widgets), 1)
        self.assertIsInstance(widgets[0], ui.IntDrag)

        for w in widgets:
            w.destroy()
        window.destroy()

    async def test_linked_edit_workflow_uses_focus_drag_unlink_and_rebuild(self):
        """A linked integer row should keep user edits linked through a rebuild without stealing focus."""
        window = ui.Window(f"TestIntDrag_{uuid.uuid1()}", height=200, width=400, position_x=0, position_y=0)
        item = MockItem(values=[2, 4, 8])
        field = IntDragFieldGroup(min_value=0, max_value=100, linkable=True)
        try:
            with window.frame:
                field.build_ui(item)
            await omni.kit.ui_test.human_delay(3)

            # Keyboard events after the real link click prove the click focused the inline editor.
            link_widgets = omni.kit.ui_test.find_all(
                f"{window.title}//Frame/**/Image[*].identifier=='linked_drag_field_link_Value'"
            )
            self.assertEqual(len(link_widgets), 2)
            link_widget = link_widgets[0]
            await link_widget.click()
            await omni.kit.ui_test.human_delay(3)
            await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
            await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.BACKSPACE)
            await omni.kit.ui_test.emulate_char_press("6")
            await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
            await omni.kit.ui_test.human_delay()
            self.assertEqual([model.get_value_as_int() for model in item.value_models], [6, 6, 6])

            # A real drag changes the value and keeps every linked channel synchronized.
            drags = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/IntBoundedDrag[*]")
            before_drag = item.value_models[0].get_value_as_int()
            target = drags[1].center
            target.x += 200
            await omni.kit.ui_test.emulate_mouse_drag_and_drop(drags[1].center, target)
            await omni.kit.ui_test.human_delay()
            dragged_value = item.value_models[0].get_value_as_int()
            self.assertNotEqual(dragged_value, before_drag)
            self.assertEqual([model.get_value_as_int() for model in item.value_models], [dragged_value] * 3)

            # Escape abandons focused inline text after an actual link click.
            await link_widget.click()
            await link_widget.click()
            await omni.kit.ui_test.human_delay(3)
            previous_value = item.value_models[0].get_value_as_int()
            await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
            await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.BACKSPACE)
            for character in "99":
                await omni.kit.ui_test.emulate_char_press(character)
            await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
            await omni.kit.ui_test.human_delay()
            self.assertEqual(item.value_models[0].get_value_as_int(), previous_value)

            # After unlinking, a later real edit changes only its source channel.
            await link_widget.click()
            await omni.kit.ui_test.human_delay()
            drags = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/IntBoundedDrag[*]")
            target = drags[2].center
            target.x -= 200
            await omni.kit.ui_test.emulate_mouse_drag_and_drop(drags[2].center, target)
            await omni.kit.ui_test.human_delay()
            unlinked_values = [model.get_value_as_int() for model in item.value_models]
            self.assertEqual(unlinked_values.count(previous_value), 2)
            self.assertEqual(len(set(unlinked_values)), 2)

            # Rebuilding the still-linked row retains propagation but leaves its new editor unfocused.
            await link_widget.click()
            await omni.kit.ui_test.human_delay(3)
            with window.frame:
                field.build_ui(item)
            await omni.kit.ui_test.human_delay(3)
            values_before_unfocused_keyboard = [model.get_value_as_int() for model in item.value_models]
            await omni.kit.ui_test.emulate_char_press("9")
            await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
            await omni.kit.ui_test.human_delay()
            self.assertEqual(
                [model.get_value_as_int() for model in item.value_models], values_before_unfocused_keyboard
            )
            drags = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/IntBoundedDrag[*]")[-3:]
            before_rebuild_drag = item.value_models[0].get_value_as_int()
            target = drags[0].center
            if before_rebuild_drag <= 0:
                target.x += 200
            else:
                target.x -= 200
            await omni.kit.ui_test.emulate_mouse_drag_and_drop(drags[0].center, target)
            await omni.kit.ui_test.human_delay()
            rebuilt_value = item.value_models[0].get_value_as_int()
            self.assertNotEqual(rebuilt_value, before_rebuild_drag)
            self.assertEqual([model.get_value_as_int() for model in item.value_models], [rebuilt_value] * 3)
        finally:
            field.destroy()
            window.destroy()
