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

__all__ = ("TestAbstractDragFieldGroup",)

import uuid
from typing import cast

import carb.input
import omni.appwindow
import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.float_value.drag import FloatDragFieldGroup
from omni.flux.property_widget_builder.widget import Delegate, FieldBuilderList, Model, PropertyWidget

from .mocks import MockItem


class TestAbstractDragFieldGroup(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._fields: list[FloatDragFieldGroup] = []

    async def tearDown(self):
        for field in self._fields:
            field.destroy()
        self._fields.clear()
        await omni.kit.ui_test.wait_n_updates(2)

    def _make_field(self, *args, **kwargs) -> FloatDragFieldGroup:
        field = FloatDragFieldGroup(*args, **kwargs)
        self._fields.append(field)
        return field

    def _make_property_widget(self, values: list[float], *, step=None, width: int = 500):
        window = ui.Window(
            f"TestAbstractDrag_{str(uuid.uuid1())}",
            height=240,
            width=width,
            position_x=0,
            position_y=100,
        )
        item = MockItem(values)
        model = Model()
        field_builders = FieldBuilderList()

        @field_builders.register_build(lambda _: True)
        def build_field(item):
            return self._make_field(step=step)(item)

        delegate = Delegate(field_builders=field_builders)
        with window.frame:
            widget = PropertyWidget(model=model, delegate=delegate)
        model.set_items([item])
        return window, widget, item

    @staticmethod
    async def _type_text(text: str) -> None:
        await omni.kit.ui_test.emulate_char_press(text)
        await omni.kit.ui_test.human_delay(human_delay_speed=1)

    @staticmethod
    async def _press_key(key: carb.input.KeyboardInput) -> None:
        await omni.kit.ui_test.emulate_keyboard_press(key)
        await omni.kit.ui_test.human_delay(human_delay_speed=1)

    @staticmethod
    async def _emulate_keyboard(
        event_type: carb.input.KeyboardEventType, key: carb.input.KeyboardInput, modifier: int = 0
    ) -> None:
        keyboard = omni.appwindow.get_default_app_window().get_keyboard()
        carb.input.acquire_input_provider().buffer_keyboard_key_event(keyboard, event_type, key, modifier)
        await omni.kit.ui_test.human_delay(human_delay_speed=1)

    def _find_float_drag_widgets(self, window_title: str, expected_count: int):
        widget_refs = omni.kit.ui_test.find_all(f"{window_title}//Frame/**/FloatBoundedDrag[*]")
        self.assertEqual(len(widget_refs), expected_count)
        return widget_refs

    # ------------------------------------------------------------------
    # __call__ delegation
    # ------------------------------------------------------------------

    async def test_callable_delegates_to_build_ui(self):
        """Calling the field instance should delegate to build_ui."""
        window = ui.Window(
            f"TestAbstractDrag_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=100,
        )
        item = MockItem(values=[1.0])
        field = self._make_field(min_value=0.0, max_value=10.0)

        with window.frame:
            widgets = cast(list[ui.Widget], field(item))

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertIsNotNone(widgets)
        self.assertEqual(len(widgets), 1)

        for w in widgets:
            w.destroy()
        window.destroy()

    # ------------------------------------------------------------------
    # build_ui tests (common layout behaviour)
    # ------------------------------------------------------------------

    async def test_build_ui_single_element(self):
        """build_ui should produce exactly one drag widget for a single-element item."""
        window = ui.Window(
            f"TestAbstractDrag_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=100,
        )
        item = MockItem(values=[42.0])
        field = self._make_field(min_value=0.0, max_value=100.0)

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(widgets), 1)

        for w in widgets:
            w.destroy()
        window.destroy()

    async def test_build_ui_multiple_elements(self):
        """build_ui should produce one drag widget per element."""
        window = ui.Window(
            f"TestAbstractDrag_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=100,
        )
        item = MockItem(values=[1.0, 2.0, 3.0])
        field = self._make_field(min_value=0.0, max_value=10.0)

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(widgets), 3)

        for w in widgets:
            w.destroy()
        window.destroy()

    async def test_build_ui_read_only_appends_read_suffix(self):
        """When a value model is read-only, the style override should end with 'Read'."""
        build_calls: list[dict] = []
        original_build = FloatDragFieldGroup.build_drag_widget

        def spy_build(
            self_inner,
            model,
            style_type_name_override,
            read_only,
            min_val,
            max_val,
            hard_min_val,
            hard_max_val,
            step,
        ):
            build_calls.append({"style": style_type_name_override, "read_only": read_only})
            return original_build(
                self_inner,
                model,
                style_type_name_override,
                read_only,
                min_val,
                max_val,
                hard_min_val,
                hard_max_val,
                step,
            )

        window = ui.Window(
            f"TestAbstractDrag_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[5.0], read_only=True)
        field = self._make_field(min_value=0.0, max_value=10.0)
        field.build_drag_widget = lambda *a, **kw: spy_build(field, *a, **kw)

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(build_calls), 1)
        self.assertTrue(build_calls[0]["style"].endswith("Read"))
        self.assertTrue(build_calls[0]["read_only"])

        for w in widgets:
            w.destroy()
        window.destroy()

    async def test_build_ui_writable_uses_plain_style(self):
        """When a value model is writable, the style override should NOT have 'Read' suffix."""
        build_calls: list[dict] = []
        original_build = FloatDragFieldGroup.build_drag_widget

        def spy_build(
            self_inner,
            model,
            style_type_name_override,
            read_only,
            min_val,
            max_val,
            hard_min_val,
            hard_max_val,
            step,
        ):
            build_calls.append({"style": style_type_name_override, "read_only": read_only})
            return original_build(
                self_inner,
                model,
                style_type_name_override,
                read_only,
                min_val,
                max_val,
                hard_min_val,
                hard_max_val,
                step,
            )

        window = ui.Window(
            f"TestAbstractDrag_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[5.0], read_only=False)
        field = self._make_field(min_value=0.0, max_value=10.0)
        field.build_drag_widget = lambda *a, **kw: spy_build(field, *a, **kw)

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(build_calls), 1)
        self.assertFalse(build_calls[0]["style"].endswith("Read"))
        self.assertFalse(build_calls[0]["read_only"])

        for w in widgets:
            w.destroy()
        window.destroy()

    async def test_build_ui_passes_min_max_step_to_drag(self):
        """build_drag_widget should receive the field's min, max, and step values."""
        build_calls: list[dict] = []
        original_build = FloatDragFieldGroup.build_drag_widget

        def spy_build(
            self_inner,
            model,
            style_type_name_override,
            read_only,
            min_val,
            max_val,
            hard_min_val,
            hard_max_val,
            step,
        ):
            build_calls.append({"min": min_val, "max": max_val, "step": step})
            return original_build(
                self_inner,
                model,
                style_type_name_override,
                read_only,
                min_val,
                max_val,
                hard_min_val,
                hard_max_val,
                step,
            )

        window = ui.Window(
            f"TestAbstractDrag_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[5.0])
        field = self._make_field(min_value=-10.0, max_value=10.0, step=0.5)
        field.build_drag_widget = lambda *a, **kw: spy_build(field, *a, **kw)

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(build_calls), 1)
        self.assertEqual(build_calls[0]["min"], -10.0)
        self.assertEqual(build_calls[0]["max"], 10.0)
        self.assertEqual(build_calls[0]["step"], 0.5)

        for w in widgets:
            w.destroy()
        window.destroy()

    async def test_build_ui_unbounded_passes_none(self):
        """For unbounded fields, build_drag_widget should receive None for min/max."""
        build_calls: list[dict] = []
        original_build = FloatDragFieldGroup.build_drag_widget

        def spy_build(
            self_inner,
            model,
            style_type_name_override,
            read_only,
            min_val,
            max_val,
            hard_min_val,
            hard_max_val,
            step,
        ):
            build_calls.append({"min": min_val, "max": max_val, "step": step})
            return original_build(
                self_inner,
                model,
                style_type_name_override,
                read_only,
                min_val,
                max_val,
                hard_min_val,
                hard_max_val,
                step,
            )

        window = ui.Window(
            f"TestAbstractDrag_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[5.0])
        field = self._make_field()
        field.build_drag_widget = lambda *a, **kw: spy_build(field, *a, **kw)

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(build_calls), 1)
        self.assertIsNone(build_calls[0]["min"])
        self.assertIsNone(build_calls[0]["max"])

        for w in widgets:
            w.destroy()
        window.destroy()

    # ------------------------------------------------------------------
    # Hard-bounds clamping via drag and typed entry
    # ------------------------------------------------------------------

    async def test_hard_bounds_clamp_on_drag(self):
        """Dragging should clamp to soft bounds."""
        window = ui.Window(
            f"TestAbstractDrag_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[50.0])
        field = self._make_field(
            min_value=0.0,
            max_value=100.0,
            hard_min_value=-10.0,
            hard_max_value=110.0,
            step=1.0,
        )

        with window.frame:
            field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        widget_refs = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatBoundedDrag[*]")
        self.assertTrue(len(widget_refs) > 0, "No FloatBoundedDrag widgets found")
        widget_ref = widget_refs[0]

        # Drag far left -- FloatDrag clamps to min_value (soft bound)
        target = widget_ref.center
        target.x = target.x - 600
        await omni.kit.ui_test.human_delay(30)
        await omni.kit.ui_test.emulate_mouse_drag_and_drop(widget_ref.center, target)
        await omni.kit.ui_test.wait_n_updates(2)
        self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 0.0)

        # Drag far right -- FloatDrag clamps to max_value (soft bound)
        target = widget_ref.center
        target.x = target.x + 600
        await omni.kit.ui_test.human_delay(30)
        await omni.kit.ui_test.emulate_mouse_drag_and_drop(widget_ref.center, target)
        await omni.kit.ui_test.wait_n_updates(2)
        self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 100.0)

        window.destroy()

    async def test_double_click_numeric_field_selects_existing_value_for_replacement(self):
        """Double-clicking a delegate numeric field should prefill the editor with selected existing text."""
        window, property_widget, item = self._make_property_widget([8.0])
        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widgets = self._find_float_drag_widgets(window.title, 1)

            # Double-click into the field and type a new value through the real UI input path.
            await widgets[0].click()
            await widgets[0].double_click()
            await self._type_text("12")
            self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 12.0, places=5)

            await self._press_key(carb.input.KeyboardInput.ENTER)
        finally:
            property_widget.destroy()
            window.destroy()

    async def test_math_expression_and_arrow_step_update_delegate_field(self):
        """Typed math should update the delegate model immediately; Arrow Up should step from that result."""
        window, property_widget, item = self._make_property_widget([0.0], step=0.25)
        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widgets = self._find_float_drag_widgets(window.title, 1)

            # Enter a math expression and verify the model changes while the text editor is still active.
            await widgets[0].click()
            await widgets[0].double_click()
            await self._type_text("2*100")
            self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 200.0, places=5)

            # Arrow Up uses the widget step and continues from the evaluated expression result.
            await self._press_key(carb.input.KeyboardInput.UP)
            self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 200.25, places=5)

            await self._press_key(carb.input.KeyboardInput.ENTER)
        finally:
            property_widget.destroy()
            window.destroy()

    async def test_tab_after_expression_focuses_next_delegate_field(self):
        """Tab after a math expression should commit it and focus the next vector component."""
        window, property_widget, item = self._make_property_widget([5.0, 6.0, 7.0])
        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widgets = self._find_float_drag_widgets(window.title, 3)

            # Type an expression in X, then Tab once.
            await widgets[0].click()
            await widgets[0].double_click()
            await self._type_text("3*10")
            self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 30.0, places=5)

            # The same Tab press should move focus to Y; no second Tab should be needed.
            await self._press_key(carb.input.KeyboardInput.TAB)
            self.assertAlmostEqual(widgets[0].widget.model.get_value_as_float(), 30.0, places=5)

            # Typing now should replace Y, proving focus moved to the next delegate field.
            await self._type_text("12")
            self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 30.0, places=5)
            self.assertAlmostEqual(item.value_models[1].get_value_as_float(), 12.0, places=5)
            self.assertAlmostEqual(item.value_models[2].get_value_as_float(), 7.0, places=5)

            await self._press_key(carb.input.KeyboardInput.ENTER)
        finally:
            property_widget.destroy()
            window.destroy()

    async def test_vector_tab_loop_and_hold_arrow_step_focused_delegate_field(self):
        """Tabbing X/Y/Z/X and holding Arrow Up should keep editing the focused field, not the hovered field."""
        window, property_widget, item = self._make_property_widget([1.0, 2.0, 3.0], step=[0.1, 0.2, 0.3])
        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widgets = self._find_float_drag_widgets(window.title, 3)

            # Step X, then Tab to Y and Z through real keyboard focus.
            await widgets[0].click()
            await widgets[0].double_click()
            await self._press_key(carb.input.KeyboardInput.UP)
            self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 1.1, places=5)

            await self._press_key(carb.input.KeyboardInput.TAB)
            await self._press_key(carb.input.KeyboardInput.UP)
            self.assertAlmostEqual(item.value_models[1].get_value_as_float(), 2.2, places=5)

            await self._press_key(carb.input.KeyboardInput.TAB)
            await self._press_key(carb.input.KeyboardInput.DOWN)
            self.assertAlmostEqual(item.value_models[2].get_value_as_float(), 2.7, places=5)

            # Tabbing after Z loops back to X.
            await self._press_key(carb.input.KeyboardInput.TAB)

            # Move the cursor over Y, then hold Arrow Up; the focused X field should receive every repeat.
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

            self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 1.6, places=5)
            self.assertAlmostEqual(item.value_models[1].get_value_as_float(), 2.2, places=5)
            self.assertAlmostEqual(item.value_models[2].get_value_as_float(), 2.7, places=5)

            await self._press_key(carb.input.KeyboardInput.ENTER)
        finally:
            property_widget.destroy()
            window.destroy()

    async def test_ctrl_click_middle_field_uses_real_property_widget_row_loop(self):
        """Ctrl+clicking a middle field in another row should edit that field and loop inside that row."""
        window = ui.Window(
            f"TestAbstractDrag_{str(uuid.uuid1())}",
            height=260,
            width=520,
            position_x=0,
            position_y=100,
        )
        first_item = MockItem([1.0, 2.0, 3.0])
        second_item = MockItem([10.0, 20.0, 30.0])
        model = Model()
        field_builders = FieldBuilderList()

        @field_builders.register_build(lambda _: True)
        def build_field(item):
            return self._make_field(step=[1.0, 10.0, 100.0])(item)

        delegate = Delegate(field_builders=field_builders)
        with window.frame:
            property_widget = PropertyWidget(model=model, delegate=delegate)
        model.set_items([first_item, second_item])

        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=10)
            widgets = self._find_float_drag_widgets(window.title, 6)

            await widgets[0].click()
            await widgets[0].double_click()

            await self._emulate_keyboard(
                carb.input.KeyboardEventType.KEY_PRESS,
                carb.input.KeyboardInput.LEFT_CONTROL,
                carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL,
            )
            await widgets[4].click()
            await self._emulate_keyboard(
                carb.input.KeyboardEventType.KEY_RELEASE, carb.input.KeyboardInput.LEFT_CONTROL
            )

            await self._press_key(carb.input.KeyboardInput.UP)
            self.assertEqual([model.get_value_as_float() for model in first_item.value_models], [1.0, 2.0, 3.0])
            self.assertEqual([model.get_value_as_float() for model in second_item.value_models], [10.0, 30.0, 30.0])

            await self._press_key(carb.input.KeyboardInput.TAB)
            await self._press_key(carb.input.KeyboardInput.UP)
            self.assertEqual([model.get_value_as_float() for model in second_item.value_models], [10.0, 30.0, 130.0])

            await self._press_key(carb.input.KeyboardInput.TAB)
            await self._press_key(carb.input.KeyboardInput.UP)
            self.assertEqual([model.get_value_as_float() for model in second_item.value_models], [11.0, 30.0, 130.0])

            await self._press_key(carb.input.KeyboardInput.ENTER)
        finally:
            property_widget.destroy()
            window.destroy()
