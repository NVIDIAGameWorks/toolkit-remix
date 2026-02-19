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

__all__ = ("TestAbstractSliderField",)

import uuid
from typing import Any

import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.base import AbstractSliderField


# ---------------------------------------------------------------------------
# Shared mocks – importable by sibling test modules
# ---------------------------------------------------------------------------


class MockValueModel(ui.AbstractValueModel):
    """Minimal value model that satisfies AbstractSliderField.build_ui requirements."""

    def __init__(self, value: float | int = 0.0, read_only: bool = False):
        super().__init__()
        self._value = value
        self._read_only = read_only

    @property
    def read_only(self) -> bool:
        return self._read_only

    def get_value(self):
        return self._value

    def get_value_as_float(self) -> float:
        return float(self._value)

    def get_value_as_int(self) -> int:
        return int(self._value)

    def set_value(self, value):
        self._value = value
        self._value_changed()

    def get_tool_tip(self):
        return None


class MockItem(ui.AbstractItem):
    """Minimal item with a configurable number of value models."""

    def __init__(self, values: list[float | int] | None = None, read_only: bool = False):
        super().__init__()
        if values is None:
            values = [0.0]
        self.value_models = [MockValueModel(v, read_only=read_only) for v in values]

    @property
    def element_count(self) -> int:
        return len(self.value_models)


# ---------------------------------------------------------------------------
# Concrete stub used exclusively for testing AbstractSliderField behaviour
# ---------------------------------------------------------------------------


class _StubSliderField(AbstractSliderField):
    """Thin concrete subclass that records build_drag_widget calls."""

    def __init__(self, **kwargs):
        style_name = kwargs.get("style_name", "StubSliderField")
        kwargs["style_name"] = style_name
        super().__init__(**kwargs)

    def build_drag_widget(
        self,
        model: ui.AbstractValueModel,
        style_type_name_override: str,
        read_only: bool,
        min_val: float | int,
        max_val: float | int,
        step: float | int,
    ) -> Any:
        # Use a real widget so build_ui can call set_mouse_hovered_fn etc.
        return ui.FloatDrag(
            model=model,
            style_type_name_override=style_type_name_override,
            read_only=read_only,
            min=min_val,
            max=max_val,
            step=step,
        )


# ---------------------------------------------------------------------------
# Tests for behaviour defined in AbstractSliderField
# ---------------------------------------------------------------------------


class TestAbstractSliderField(omni.kit.test.AsyncTestCase):
    # ------------------------------------------------------------------
    # Constructor & property tests
    # ------------------------------------------------------------------

    async def test_stores_min_max_step(self):
        """Constructor should persist min_value, max_value, and _step."""
        field = _StubSliderField(min_value=-5.0, max_value=5.0, step=0.25)
        self.assertEqual(field.min_value, -5.0)
        self.assertEqual(field.max_value, 5.0)
        self.assertEqual(field._step, 0.25)

    async def test_step_property_returns_explicit_value(self):
        """The base step property should return _step when it is set."""
        field = _StubSliderField(min_value=0.0, max_value=100.0, step=3.0)
        self.assertEqual(field.step, 3.0)

    async def test_step_property_returns_none_when_unset(self):
        """The base step property should return None when _step is not set."""
        field = _StubSliderField(min_value=0.0, max_value=100.0)
        self.assertIsNone(field.step)

    async def test_custom_style_name(self):
        """style_name should be forwarded through kwargs."""
        field = _StubSliderField(min_value=0.0, max_value=1.0, style_name="Custom")
        self.assertEqual(field.style_name, "Custom")

    async def test_default_style_name(self):
        """Default style_name for the stub should be 'StubSliderField'."""
        field = _StubSliderField(min_value=0.0, max_value=1.0)
        self.assertEqual(field.style_name, "StubSliderField")

    async def test_invalid_min_max_raises(self):
        """min_value must be strictly less than max_value."""
        with self.assertRaises(AssertionError):
            _StubSliderField(min_value=100.0, max_value=0.0)

    async def test_equal_min_max_raises(self):
        """Equal min and max should be rejected."""
        with self.assertRaises(AssertionError):
            _StubSliderField(min_value=50.0, max_value=50.0)

    async def test_identifier_forwarded(self):
        """The identifier kwarg defined in AbstractField should propagate."""
        field = _StubSliderField(min_value=0.0, max_value=1.0, identifier="my_id")
        self.assertEqual(field.identifier, "my_id")

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
