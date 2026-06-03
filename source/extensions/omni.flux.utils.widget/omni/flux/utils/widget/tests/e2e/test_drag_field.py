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

__all__ = ("TestDragField",)

import uuid
from typing import Any

import carb.input
import omni.appwindow
import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.flux.utils.widget import FloatBoundedDrag


class _TestValueModel(ui.AbstractValueModel):
    def __init__(self, value: float = 0.0, *, supports_batch_edit: bool = False):
        super().__init__()
        self._value = value
        self._pre_set_callback = None
        self._cancel_callbacks = []
        self.supports_batch_edit = supports_batch_edit
        self.is_batch_editing = False
        self.begin_count = 0
        self.end_count = 0
        self.begin_batch_count = 0
        self.end_batch_count = 0

    def begin_edit(self):
        self.begin_count += 1
        super().begin_edit()

    def end_edit(self):
        self.end_count += 1
        super().end_edit()

    def set_callback_pre_set_value(self, callback):
        self._pre_set_callback = callback

    def begin_batch_edit(self):
        self.begin_batch_count += 1
        self.is_batch_editing = True

    def end_batch_edit(self):
        self.end_batch_count += 1
        self.is_batch_editing = False

    def subscribe_property_edit_cancel_fn(self, callback):
        self._cancel_callbacks.append(callback)

        def unsubscribe():
            if callback in self._cancel_callbacks:
                self._cancel_callbacks.remove(callback)

        return unsubscribe

    def set_value(self, value: Any):
        if self._pre_set_callback is not None:
            self._pre_set_callback(self._set_value, value)
            return
        self._set_value(value)

    def _set_value(self, value: Any):
        self._value = value
        self._value_changed()

    def get_value(self) -> Any:
        return self._value

    def get_value_as_float(self) -> float:
        return float(self._value)

    def get_value_as_int(self) -> int:
        return int(self._value)

    def get_value_as_bool(self) -> bool:
        return bool(self._value)

    def get_value_as_string(self) -> str:
        return str(self._value)


class TestDragField(omni.kit.test.AsyncTestCase):
    async def tearDown(self):
        await omni.kit.ui_test.wait_n_updates(2)

    @staticmethod
    async def _emulate_keyboard(
        event_type: carb.input.KeyboardEventType, key: carb.input.KeyboardInput, modifier: int = 0
    ) -> None:
        keyboard = omni.appwindow.get_default_app_window().get_keyboard()
        carb.input.acquire_input_provider().buffer_keyboard_key_event(keyboard, event_type, key, modifier)
        await omni.kit.ui_test.human_delay(human_delay_speed=1)

    @staticmethod
    async def _type_text(text: str) -> None:
        await omni.kit.ui_test.emulate_char_press(text)
        await omni.kit.ui_test.human_delay(human_delay_speed=1)

    @staticmethod
    async def _press_key(key: carb.input.KeyboardInput) -> None:
        await omni.kit.ui_test.emulate_keyboard_press(key)
        await omni.kit.ui_test.human_delay(human_delay_speed=1)

    @staticmethod
    def _build_two_row_drag_grid():
        """Build two row-local numeric edit groups for tab-loop regression coverage."""
        first_models = [_TestValueModel(value) for value in (1.0, 2.0, 3.0)]
        second_models = [_TestValueModel(value) for value in (10.0, 20.0, 30.0)]
        first_widgets = []
        second_widgets = []
        with ui.VStack():
            with ui.HStack():
                for model in first_models:
                    first_widgets.append(FloatBoundedDrag(model=model, step=1.0, width=ui.Pixel(120)))
            with ui.HStack():
                for model in second_models:
                    second_widgets.append(FloatBoundedDrag(model=model, step=10.0, width=ui.Pixel(120)))

        for row_widgets in (first_widgets, second_widgets):
            row_widget_map = dict(enumerate(row_widgets))
            for index, widget in enumerate(row_widgets):
                widget.set_numeric_edit_widgets(row_widget_map, index)

        return first_models, second_models, first_widgets, second_widgets

    async def test_direct_float_drag_expression_and_arrow_step_update_focused_widget(self):
        window = ui.Window(
            f"TestDragField_{str(uuid.uuid1())}",
            height=160,
            width=260,
            position_x=0,
            position_y=100,
        )
        first_model = _TestValueModel(0.0)
        with window.frame:
            with ui.HStack():
                first_drag = FloatBoundedDrag(model=first_model, step=0.25, width=ui.Pixel(160))
        edit_widgets = {0: first_drag}
        first_drag.set_numeric_edit_widgets(edit_widgets, 0)

        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widgets = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatBoundedDrag[*]")
            self.assertEqual(len(widgets), 1)

            await widgets[0].click()
            await widgets[0].double_click()
            await self._type_text("2*100")
            self.assertAlmostEqual(first_model.get_value_as_float(), 200.0, places=5)

            await self._press_key(carb.input.KeyboardInput.UP)
            self.assertAlmostEqual(first_model.get_value_as_float(), 200.25, places=5)

            await self._press_key(carb.input.KeyboardInput.ENTER)
        finally:
            window.destroy()

    async def test_direct_float_drag_double_click_text_edit_does_not_start_drag_batch(self):
        window = ui.Window(
            f"TestDragField_{str(uuid.uuid1())}",
            height=160,
            width=260,
            position_x=0,
            position_y=100,
        )
        model = _TestValueModel(-157.0, supports_batch_edit=True)
        with window.frame:
            with ui.HStack():
                FloatBoundedDrag(model=model, step=1.0, width=ui.Pixel(160))

        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widgets = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatBoundedDrag[*]")
            self.assertEqual(len(widgets), 1)

            await widgets[0].double_click()
            for char in "12":
                await omni.kit.ui_test.emulate_char_press(char)
                await omni.kit.ui_test.wait_n_updates(1)

            self.assertAlmostEqual(model.get_value_as_float(), 12.0, places=5)
            self.assertEqual(model.begin_batch_count, 0)
            self.assertFalse(model.is_batch_editing)

            await self._press_key(carb.input.KeyboardInput.ENTER)
        finally:
            window.destroy()

    async def test_direct_float_drag_switching_fields_updates_only_focused_widget(self):
        window = ui.Window(
            f"TestDragField_{str(uuid.uuid1())}",
            height=160,
            width=520,
            position_x=0,
            position_y=100,
        )
        first_model = _TestValueModel(10.0)
        second_model = _TestValueModel(20.0)
        third_model = _TestValueModel(30.0)
        with window.frame:
            with ui.HStack():
                first_drag = FloatBoundedDrag(model=first_model, step=1.0, width=ui.Pixel(160))
                second_drag = FloatBoundedDrag(model=second_model, step=1.0, width=ui.Pixel(160))
                third_drag = FloatBoundedDrag(model=third_model, step=1.0, width=ui.Pixel(160))
        edit_widgets = {0: first_drag, 1: second_drag, 2: third_drag}
        first_drag.set_numeric_edit_widgets(edit_widgets, 0)
        second_drag.set_numeric_edit_widgets(edit_widgets, 1)
        third_drag.set_numeric_edit_widgets(edit_widgets, 2)

        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widgets = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatBoundedDrag[*]")
            self.assertEqual(len(widgets), 3)

            await widgets[0].click()
            await widgets[0].double_click()
            await self._type_text("1")
            self.assertAlmostEqual(first_model.get_value_as_float(), 1.0, places=5)

            await widgets[1].click()
            await widgets[1].double_click()
            await self._type_text("2")
            self.assertAlmostEqual(first_model.get_value_as_float(), 1.0, places=5)
            self.assertAlmostEqual(second_model.get_value_as_float(), 2.0, places=5)

            await widgets[2].click()
            await widgets[2].double_click()
            await self._type_text("3")
            self.assertAlmostEqual(first_model.get_value_as_float(), 1.0, places=5)
            self.assertAlmostEqual(second_model.get_value_as_float(), 2.0, places=5)
            self.assertAlmostEqual(third_model.get_value_as_float(), 3.0, places=5)

            await self._press_key(carb.input.KeyboardInput.ENTER)
        finally:
            window.destroy()

    async def test_direct_float_drag_inserts_text_at_tracked_cursor(self):
        window = ui.Window(
            f"TestDragField_{str(uuid.uuid1())}",
            height=160,
            width=260,
            position_x=0,
            position_y=100,
        )
        model = _TestValueModel(0.0)
        with window.frame:
            with ui.HStack():
                FloatBoundedDrag(model=model, step=1.0, width=ui.Pixel(160))

        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widgets = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatBoundedDrag[*]")
            self.assertEqual(len(widgets), 1)

            await widgets[0].click()
            await widgets[0].double_click()
            await self._type_text("1234")
            self.assertAlmostEqual(model.get_value_as_float(), 1234.0, places=5)

            await self._press_key(carb.input.KeyboardInput.LEFT)
            await self._press_key(carb.input.KeyboardInput.LEFT)
            await self._type_text("9")
            self.assertAlmostEqual(model.get_value_as_float(), 12934.0, places=5)

            await self._press_key(carb.input.KeyboardInput.ENTER)
        finally:
            window.destroy()

    async def test_direct_float_drag_clicking_other_field_commits_active_edit(self):
        window = ui.Window(
            f"TestDragField_{str(uuid.uuid1())}",
            height=160,
            width=360,
            position_x=0,
            position_y=100,
        )
        first_model = _TestValueModel(10.0)
        second_model = _TestValueModel(20.0)
        with window.frame:
            with ui.HStack():
                first_drag = FloatBoundedDrag(model=first_model, step=1.0, width=ui.Pixel(160))
                second_drag = FloatBoundedDrag(model=second_model, step=1.0, width=ui.Pixel(160))
        edit_widgets = {0: first_drag, 1: second_drag}
        first_drag.set_numeric_edit_widgets(edit_widgets, 0)
        second_drag.set_numeric_edit_widgets(edit_widgets, 1)

        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widgets = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatBoundedDrag[*]")
            self.assertEqual(len(widgets), 2)

            await widgets[0].click()
            await widgets[0].double_click()
            await self._type_text("12")
            self.assertAlmostEqual(first_model.get_value_as_float(), 12.0, places=5)
            self.assertEqual(first_model.begin_count, 1)
            self.assertEqual(first_model.end_count, 0)

            await widgets[1].click()
            await omni.kit.ui_test.human_delay(human_delay_speed=1)

            self.assertEqual(first_model.end_count, 1)
            self.assertAlmostEqual(first_model.get_value_as_float(), 12.0, places=5)
        finally:
            window.destroy()

    async def test_direct_float_drag_ctrl_click_new_row_edit_loops_active_row_fields(self):
        window = ui.Window(
            f"TestDragField_{str(uuid.uuid1())}",
            height=180,
            width=420,
            position_x=0,
            position_y=100,
        )
        with window.frame:
            first_models, second_models, _, _ = self._build_two_row_drag_grid()

        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widget_refs = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatBoundedDrag[*]")
            self.assertEqual(len(widget_refs), 6)

            await widget_refs[0].click()
            await widget_refs[0].double_click()
            await self._press_key(carb.input.KeyboardInput.TAB)

            await self._emulate_keyboard(
                carb.input.KeyboardEventType.KEY_PRESS,
                carb.input.KeyboardInput.LEFT_CONTROL,
                carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL,
            )
            await widget_refs[4].click()
            await self._emulate_keyboard(
                carb.input.KeyboardEventType.KEY_RELEASE, carb.input.KeyboardInput.LEFT_CONTROL
            )

            await self._press_key(carb.input.KeyboardInput.UP)
            self.assertListEqual([model.get_value_as_float() for model in second_models], [10.0, 30.0, 30.0])

            await self._press_key(carb.input.KeyboardInput.TAB)
            await self._press_key(carb.input.KeyboardInput.UP)
            self.assertListEqual([model.get_value_as_float() for model in second_models], [10.0, 30.0, 40.0])

            await self._press_key(carb.input.KeyboardInput.TAB)
            await self._press_key(carb.input.KeyboardInput.UP)
            self.assertListEqual([model.get_value_as_float() for model in second_models], [20.0, 30.0, 40.0])

            await self._press_key(carb.input.KeyboardInput.TAB)
            await self._press_key(carb.input.KeyboardInput.UP)
            self.assertListEqual([model.get_value_as_float() for model in second_models], [20.0, 40.0, 40.0])

            self.assertListEqual([model.get_value_as_float() for model in first_models], [1.0, 2.0, 3.0])

            await self._press_key(carb.input.KeyboardInput.ENTER)
        finally:
            window.destroy()

    async def test_direct_float_drag_holding_arrow_repeats_on_focused_widget(self):
        window = ui.Window(
            f"TestDragField_{str(uuid.uuid1())}",
            height=160,
            width=360,
            position_x=0,
            position_y=100,
        )
        first_model = _TestValueModel(1.0)
        second_model = _TestValueModel(5.0)
        with window.frame:
            with ui.HStack():
                first_drag = FloatBoundedDrag(model=first_model, step=0.1, width=ui.Pixel(160))
                second_drag = FloatBoundedDrag(model=second_model, step=10.0, width=ui.Pixel(160))
        edit_widgets = {0: first_drag, 1: second_drag}
        first_drag.set_numeric_edit_widgets(edit_widgets, 0)
        second_drag.set_numeric_edit_widgets(edit_widgets, 1)

        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widgets = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatBoundedDrag[*]")
            self.assertEqual(len(widgets), 2)

            await widgets[0].click()
            await widgets[0].double_click()
            await omni.kit.ui_test.emulate_mouse_move(widgets[1].position + omni.kit.ui_test.Vec2(3, 3))

            keyboard = omni.appwindow.get_default_app_window().get_keyboard()
            input_provider = carb.input.acquire_input_provider()
            input_provider.buffer_keyboard_key_event(
                keyboard, carb.input.KeyboardEventType.KEY_PRESS, carb.input.KeyboardInput.UP, 0
            )
            for _ in range(4):
                input_provider.buffer_keyboard_key_event(
                    keyboard, carb.input.KeyboardEventType.KEY_REPEAT, carb.input.KeyboardInput.UP, 0
                )
                await omni.kit.ui_test.human_delay(human_delay_speed=1)
            input_provider.buffer_keyboard_key_event(
                keyboard, carb.input.KeyboardEventType.KEY_RELEASE, carb.input.KeyboardInput.UP, 0
            )
            await omni.kit.ui_test.human_delay(human_delay_speed=1)

            self.assertAlmostEqual(first_model.get_value_as_float(), 1.5, places=5)
            self.assertAlmostEqual(second_model.get_value_as_float(), 5.0, places=5)

            await self._press_key(carb.input.KeyboardInput.ENTER)
        finally:
            window.destroy()

    async def test_direct_float_drag_new_row_edit_closes_previous_tabbed_row(self):
        window = ui.Window(
            f"TestDragField_{str(uuid.uuid1())}",
            height=180,
            width=420,
            position_x=0,
            position_y=100,
        )
        with window.frame:
            first_models, second_models, _, _ = self._build_two_row_drag_grid()

        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widget_refs = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatBoundedDrag[*]")
            self.assertEqual(len(widget_refs), 6)

            await widget_refs[0].click()
            await widget_refs[0].double_click()
            await self._press_key(carb.input.KeyboardInput.TAB)

            await widget_refs[3].click()
            await widget_refs[3].double_click()
            await self._press_key(carb.input.KeyboardInput.UP)

            self.assertListEqual([model.get_value_as_float() for model in first_models], [1.0, 2.0, 3.0])
            self.assertListEqual([model.get_value_as_float() for model in second_models], [20.0, 20.0, 30.0])

            await self._press_key(carb.input.KeyboardInput.ENTER)
        finally:
            window.destroy()
