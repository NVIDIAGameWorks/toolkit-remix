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
    def __init__(self, value: float = 0.0):
        super().__init__()
        self._value = value
        self._pre_set_callback = None
        self._cancel_callbacks = []
        self.supports_batch_edit = False
        self.is_batch_editing = False

    def set_callback_pre_set_value(self, callback):
        self._pre_set_callback = callback

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
    async def _type_text(text: str) -> None:
        await omni.kit.ui_test.emulate_char_press(text)
        await omni.kit.ui_test.human_delay(human_delay_speed=1)

    @staticmethod
    async def _press_key(key: carb.input.KeyboardInput) -> None:
        await omni.kit.ui_test.emulate_keyboard_press(key)
        await omni.kit.ui_test.human_delay(human_delay_speed=1)

    async def test_direct_float_drag_expression_and_arrow_step_update_focused_widget(self):
        window = ui.Window(
            f"TestDragField_{str(uuid.uuid1())}",
            height=160,
            width=360,
            position_x=0,
            position_y=100,
        )
        first_model = _TestValueModel(0.0)
        second_model = _TestValueModel(5.0)
        with window.frame:
            with ui.HStack():
                FloatBoundedDrag(model=first_model, step=0.25, width=ui.Pixel(160))
                FloatBoundedDrag(model=second_model, step=10.0, width=ui.Pixel(160))

        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widgets = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatBoundedDrag[*]")
            self.assertEqual(len(widgets), 2)

            # Type math through the native double-click edit affordance.
            await widgets[0].click()
            await widgets[0].double_click()
            await self._type_text("2*100")
            self.assertAlmostEqual(first_model.get_value_as_float(), 200.0, places=5)

            # Move the cursor away; Arrow Up should still step the focused edit field.
            await omni.kit.ui_test.emulate_mouse_move(widgets[1].position + omni.kit.ui_test.Vec2(3, 3))
            await self._press_key(carb.input.KeyboardInput.UP)
            self.assertAlmostEqual(first_model.get_value_as_float(), 200.25, places=5)
            self.assertAlmostEqual(second_model.get_value_as_float(), 5.0, places=5)

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
                FloatBoundedDrag(model=first_model, step=0.1, width=ui.Pixel(160))
                FloatBoundedDrag(model=second_model, step=10.0, width=ui.Pixel(160))

        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widgets = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatBoundedDrag[*]")
            self.assertEqual(len(widgets), 2)

            # Start editing first field, hover second, then hold Arrow Up.
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
