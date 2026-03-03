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

__all__ = ("TestAbstractSliderField",)

import uuid
from typing import Any

import carb.input
import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.base import AbstractSliderField

from .mocks import MockItem


class _StubSliderField(AbstractSliderField):
    """Thin concrete subclass that records build_drag_widget calls."""

    def __init__(self, **kwargs):
        kwargs.setdefault("style_name", "StubSliderField")
        super().__init__(**kwargs)

    def _get_value_from_model(self, model) -> float:
        return model.get_value_as_float()

    def build_drag_widget(
        self,
        model: ui.AbstractValueModel,
        style_type_name_override: str,
        read_only: bool,
        min_val: float | int,
        max_val: float | int,
        step: float | int,
    ) -> Any:
        return ui.FloatDrag(
            model=model,
            style_type_name_override=style_type_name_override,
            read_only=read_only,
            min=min_val,
            max=max_val,
            step=step,
        )


class TestAbstractSliderField(omni.kit.test.AsyncTestCase):
    # ------------------------------------------------------------------
    # __call__ delegation
    # ------------------------------------------------------------------

    async def test_callable_delegates_to_build_ui(self):
        """Calling the field instance should delegate to build_ui."""
        window = ui.Window(
            f"TestAbstractSlider_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[1.0])
        field = _StubSliderField(min_value=0.0, max_value=10.0)

        with window.frame:
            widgets = field(item)

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
            f"TestAbstractSlider_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[42.0])
        field = _StubSliderField(min_value=0.0, max_value=100.0)

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
            f"TestAbstractSlider_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[1.0, 2.0, 3.0])
        field = _StubSliderField(min_value=0.0, max_value=10.0)

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(widgets), 3)

        for w in widgets:
            w.destroy()
        window.destroy()

    async def test_build_ui_subscribes_begin_end_edit(self):
        """build_ui should subscribe to begin_edit and end_edit on each value model."""
        window = ui.Window(
            f"TestAbstractSlider_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[1.0, 2.0])
        field = _StubSliderField(min_value=0.0, max_value=10.0)

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        # 2 elements × 2 subscriptions (begin + end) = 4
        self.assertEqual(len(field._subs), 4)

        for w in widgets:
            w.destroy()
        window.destroy()

    async def test_build_ui_read_only_appends_read_suffix(self):
        """When a value model is read-only, the style override should end with 'Read'."""
        build_calls: list[dict] = []
        original_build = _StubSliderField.build_drag_widget

        def spy_build(self_inner, model, style_type_name_override, read_only, min_val, max_val, step):
            build_calls.append({"style": style_type_name_override, "read_only": read_only})
            return original_build(self_inner, model, style_type_name_override, read_only, min_val, max_val, step)

        window = ui.Window(
            f"TestAbstractSlider_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[5.0], read_only=True)
        field = _StubSliderField(min_value=0.0, max_value=10.0)
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
        original_build = _StubSliderField.build_drag_widget

        def spy_build(self_inner, model, style_type_name_override, read_only, min_val, max_val, step):
            build_calls.append({"style": style_type_name_override, "read_only": read_only})
            return original_build(self_inner, model, style_type_name_override, read_only, min_val, max_val, step)

        window = ui.Window(
            f"TestAbstractSlider_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[5.0], read_only=False)
        field = _StubSliderField(min_value=0.0, max_value=10.0)
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
        original_build = _StubSliderField.build_drag_widget

        def spy_build(self_inner, model, style_type_name_override, read_only, min_val, max_val, step):
            build_calls.append({"min": min_val, "max": max_val, "step": step})
            return original_build(self_inner, model, style_type_name_override, read_only, min_val, max_val, step)

        window = ui.Window(
            f"TestAbstractSlider_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[5.0])
        field = _StubSliderField(min_value=-10.0, max_value=10.0, step=0.5)
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

    # ------------------------------------------------------------------
    # Hard-bounds clamping via drag and typed entry
    # ------------------------------------------------------------------

    async def test_hard_bounds_clamp_on_drag_and_type(self):
        """Dragging should clamp to soft bounds; typing should clamp to hard bounds on end-edit."""
        window = ui.Window(
            f"TestAbstractSlider_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[50.0])
        field = _StubSliderField(
            min_value=0.0,
            max_value=100.0,
            hard_min_value=-10.0,
            hard_max_value=110.0,
            step=1.0,
        )

        with window.frame:
            field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        widget_refs = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatDrag[*]")
        self.assertTrue(len(widget_refs) > 0, "No FloatDrag widgets found")
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

        # Type value above hard_max -- end_edit clamps to hard_max_value
        await widget_ref.double_click()
        await omni.kit.ui_test.emulate_char_press("200")
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
        await omni.kit.ui_test.wait_n_updates(2)
        self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 110.0)

        # Type value below hard_min -- end_edit clamps to hard_min_value
        await widget_ref.double_click()
        await omni.kit.ui_test.emulate_char_press("-50")
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
        await omni.kit.ui_test.wait_n_updates(2)
        self.assertAlmostEqual(item.value_models[0].get_value_as_float(), -10.0)

        # Type value between soft max and hard max -- within hard bounds, not clamped
        await widget_ref.double_click()
        await omni.kit.ui_test.emulate_char_press("105")
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
        await omni.kit.ui_test.wait_n_updates(2)
        self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 105.0)

        window.destroy()
