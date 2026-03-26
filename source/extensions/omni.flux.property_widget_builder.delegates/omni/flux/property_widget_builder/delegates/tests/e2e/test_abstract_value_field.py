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

__all__ = ("TestAbstractValueField",)

import uuid

import carb.input
import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.base import AbstractValueField

from .mocks import MockItem


class _StubValueField(AbstractValueField):
    """Thin concrete subclass for testing AbstractValueField."""

    def __init__(self, **kwargs):
        kwargs.setdefault("widget_type", ui.FloatDrag)
        kwargs.setdefault("style_name", "StubValueField")
        super().__init__(**kwargs)

    def _get_value_from_model(self, model) -> float:
        return model.get_value_as_float()


class TestAbstractValueField(omni.kit.test.AsyncTestCase):
    # ------------------------------------------------------------------
    # build_ui tests
    # ------------------------------------------------------------------

    async def test_build_ui_single_element(self):
        """build_ui should produce one widget for a single-element item."""
        window = ui.Window(
            f"TestAbstractValueField_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[42.0])
        field = _StubValueField()

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(widgets), 1)

        for w in widgets:
            w.destroy()
        window.destroy()

    async def test_build_ui_multiple_elements(self):
        """build_ui should produce one widget per element."""
        window = ui.Window(
            f"TestAbstractValueField_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[1.0, 2.0, 3.0])
        field = _StubValueField()

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(widgets), 3)

        for w in widgets:
            w.destroy()
        window.destroy()

    async def test_build_ui_read_only_style_suffix(self):
        """Read-only models should get the 'Read' suffix on the style name."""
        window = ui.Window(
            f"TestAbstractValueField_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[5.0], read_only=True)
        field = _StubValueField()

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(widgets), 1)
        self.assertTrue(widgets[0].style_type_name_override.endswith("Read"))

        for w in widgets:
            w.destroy()
        window.destroy()

    async def test_build_ui_subscribes_begin_end_edit(self):
        """build_ui should subscribe to begin_edit and end_edit on each value model."""
        window = ui.Window(
            f"TestAbstractValueField_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[1.0, 2.0])
        field = _StubValueField()

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        # 2 elements x 2 subscriptions (begin + end) = 4
        self.assertEqual(len(field._subs), 4)

        for w in widgets:
            w.destroy()
        window.destroy()

    # ------------------------------------------------------------------
    # Clamp-on-edit via keyboard entry
    # ------------------------------------------------------------------

    async def test_clamp_on_type_above_max(self):
        """Typing a value above clamp_max should clamp to clamp_max on end-edit."""
        window = ui.Window(
            f"TestAbstractValueField_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[50.0])
        field = _StubValueField(clamp_min=0.0, clamp_max=100.0)

        with window.frame:
            field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        widget_refs = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatDrag[*]")
        self.assertTrue(len(widget_refs) > 0, "No FloatDrag widgets found")
        widget_ref = widget_refs[0]

        await widget_ref.double_click()
        await omni.kit.ui_test.emulate_char_press("200")
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
        await omni.kit.ui_test.wait_n_updates(2)
        self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 100.0)

        window.destroy()

    async def test_clamp_on_type_below_min(self):
        """Typing a value below clamp_min should clamp to clamp_min on end-edit."""
        window = ui.Window(
            f"TestAbstractValueField_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[50.0])
        field = _StubValueField(clamp_min=0.0, clamp_max=100.0)

        with window.frame:
            field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        widget_refs = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatDrag[*]")
        self.assertTrue(len(widget_refs) > 0, "No FloatDrag widgets found")
        widget_ref = widget_refs[0]

        await widget_ref.double_click()
        await omni.kit.ui_test.emulate_char_press("-50")
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
        await omni.kit.ui_test.wait_n_updates(2)
        self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 0.0)

        window.destroy()

    async def test_no_clamp_within_bounds(self):
        """Typing a value within bounds should not be altered."""
        window = ui.Window(
            f"TestAbstractValueField_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[50.0])
        field = _StubValueField(clamp_min=0.0, clamp_max=100.0)

        with window.frame:
            field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        widget_refs = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatDrag[*]")
        self.assertTrue(len(widget_refs) > 0, "No FloatDrag widgets found")
        widget_ref = widget_refs[0]

        await widget_ref.double_click()
        await omni.kit.ui_test.emulate_char_press("75")
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
        await omni.kit.ui_test.wait_n_updates(2)
        self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 75.0)

        window.destroy()

    async def test_one_sided_clamp_min_only(self):
        """With only clamp_min set, values below min should be clamped but no upper limit enforced."""
        window = ui.Window(
            f"TestAbstractValueField_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[50.0])
        field = _StubValueField(clamp_min=10.0)

        with window.frame:
            field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        widget_refs = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatDrag[*]")
        self.assertTrue(len(widget_refs) > 0, "No FloatDrag widgets found")
        widget_ref = widget_refs[0]

        # Type below min -- should clamp
        await widget_ref.double_click()
        await omni.kit.ui_test.emulate_char_press("5")
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
        await omni.kit.ui_test.wait_n_updates(2)
        self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 10.0)

        # Type above -- no upper clamp, value accepted
        await widget_ref.double_click()
        await omni.kit.ui_test.emulate_char_press("9999")
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
        await omni.kit.ui_test.wait_n_updates(2)
        self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 9999.0)

        window.destroy()

    async def test_one_sided_clamp_max_only(self):
        """With only clamp_max set, values above max should be clamped but no lower limit enforced."""
        window = ui.Window(
            f"TestAbstractValueField_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[50.0])
        field = _StubValueField(clamp_max=100.0)

        with window.frame:
            field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        widget_refs = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/FloatDrag[*]")
        self.assertTrue(len(widget_refs) > 0, "No FloatDrag widgets found")
        widget_ref = widget_refs[0]

        # Type above max -- should clamp
        await widget_ref.double_click()
        await omni.kit.ui_test.emulate_char_press("200")
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
        await omni.kit.ui_test.wait_n_updates(2)
        self.assertAlmostEqual(item.value_models[0].get_value_as_float(), 100.0)

        # Type below -- no lower clamp, value accepted
        await widget_ref.double_click()
        await omni.kit.ui_test.emulate_char_press("-9999")
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
        await omni.kit.ui_test.wait_n_updates(2)
        self.assertAlmostEqual(item.value_models[0].get_value_as_float(), -9999.0)

        window.destroy()
