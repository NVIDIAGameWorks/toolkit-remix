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

from contextlib import AsyncExitStack

import omni.kit.test
import omni.kit.undo
import omni.ui as ui
import omni.usd
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardEventType, KeyboardInput
from omni.flux.property_widget_builder.model.usd import (
    USDAttributeItem,
    USDDelegate,
    USDModel,
    USDPropertyWidget,
    VirtualUSDAttributeItem,
)
from omni.kit import ui_test
from omni.kit.ui_test.input import emulate_keyboard
from pxr import Gf, Sdf

__all__ = ["TestVirtualAttributeDefaults"]


class TestVirtualAttributeDefaults(omni.kit.test.AsyncTestCase):
    """Exercise numeric defaults, first edits, and reset through real property controls."""

    _WINDOW_WIDTH = ui.Pixel(600)
    _WINDOW_HEIGHT = ui.Pixel(200)

    async def test_edit_numeric_defaults_preserves_untouched_channels_and_reset_values(self):
        """Preserve complete numeric defaults through field construction, edits, and row reset."""
        cases = [
            (Sdf.ValueTypeNames.Float2, Gf.Vec2f(1, 2), 7.5, "missing"),
            (Sdf.ValueTypeNames.Float3, Gf.Vec3f(1, 2, 3), 7.5, "missing"),
            (Sdf.ValueTypeNames.Float4, Gf.Vec4f(1, 2, 3, 4), 7.5, "missing"),
            (Sdf.ValueTypeNames.Int2, Gf.Vec2i(3, 5), 9, "missing"),
            (Sdf.ValueTypeNames.Int3, Gf.Vec3i(3, 5, 8), 9, "missing"),
            (Sdf.ValueTypeNames.Int4, Gf.Vec4i(3, 5, 8, 13), 9, "missing"),
            (Sdf.ValueTypeNames.Double2, Gf.Vec2d(1.5, 2.5), 7.5, "missing"),
            (Sdf.ValueTypeNames.Double3, Gf.Vec3d(1.5, 2.5, 3.5), 7.5, "missing"),
            (Sdf.ValueTypeNames.Double4, Gf.Vec4d(1.5, 2.5, 3.5, 4.5), 7.5, "missing"),
            (Sdf.ValueTypeNames.Float, 0.75, 7.5, "missing"),
            (Sdf.ValueTypeNames.Float2, Gf.Vec2f(1, 2), 7.5, "value_less"),
            (Sdf.ValueTypeNames.Float2, Gf.Vec2f(1, 2), 7.5, "authored"),
        ]
        for value_type, default_value, edit_value, source_kind in cases:
            with self.subTest(value_type=str(value_type), source_kind=source_kind):
                async with AsyncExitStack() as cleanup:
                    context = omni.usd.get_context("")
                    cleanup.push_async_callback(context.close_stage_async)
                    cleanup.callback(omni.kit.undo.clear_stack)
                    await context.new_stage_async()
                    stage = context.get_stage()
                    prim = stage.DefinePrim("/Defaults", "Xform")
                    path = Sdf.Path("/Defaults.value")
                    scalar = value_type == Sdf.ValueTypeNames.Float
                    default_components = [default_value] if scalar else list(default_value)
                    if source_kind != "missing":
                        attribute = prim.CreateAttribute("value", value_type)
                        if source_kind == "authored":
                            attribute.Set(Gf.Vec2f(20, 30))
                    if source_kind == "authored":
                        item = USDAttributeItem("", [path], default_value=default_value)
                        expected_components = [20.0, 30.0]
                    else:
                        item = VirtualUSDAttributeItem(
                            "", [path], value_type_name=value_type, default_value=default_value
                        )
                        expected_components = list(default_components)
                    model = USDModel(context_name="")
                    cleanup.callback(model.destroy)
                    window = ui.Window(
                        f"Numeric defaults {value_type} {source_kind}",
                        width=self._WINDOW_WIDTH,
                        height=self._WINDOW_HEIGHT,
                    )
                    cleanup.callback(window.destroy)
                    with window.frame:
                        widget = USDPropertyWidget(context_name="", model=model, delegate=USDDelegate())
                        cleanup.callback(widget.destroy)
                    model.set_items([item])
                    await ui_test.human_delay()

                    # Building the actual fields must expose the distinct defaults without authoring them.
                    fields = self.__fields(window, item)
                    self.assertEqual([field.widget.model.get_value_as_float() for field in fields], expected_components)
                    if source_kind != "authored":
                        self.assertTrue(all(value_model.is_default for value_model in item.value_models))
                        await self.__enter_value(fields[-1], default_components[-1])
                        self.assertEqual(prim.GetAttribute("value").IsValid(), source_kind == "value_less")
                        if source_kind == "value_less":
                            self.assertFalse(prim.GetAttribute("value").HasAuthoredValue())

                    # Editing each channel preserves the others and never mutates the shared reset defaults.
                    for channel in range(len(default_components)):
                        field = self.__fields(window, item)[channel]
                        await self.__enter_value(field, edit_value)
                        expected_components[channel] = edit_value
                        attribute = prim.GetAttribute("value")
                        self.assertTrue(attribute.IsValid())
                        actual_value = attribute.Get()
                        self.assertEqual([actual_value] if scalar else list(actual_value), expected_components)
                        self.assertEqual(
                            [item_model.get_default_reset_value() for item_model in item.value_models],
                            default_components,
                        )
                        self.assertEqual([default_value] if scalar else list(default_value), default_components)
                        self.assertFalse(item.value_models[channel].is_default)

                    # The row's reset indicator restores every channel to its own default.
                    indicators = ui_test.find_all(
                        f"{window.title}//Frame/**/Circle[*].style_type_name_override=='OverrideIndicator'"
                    )
                    self.assertEqual(len(indicators), 1)
                    await indicators[0].click()
                    await ui_test.human_delay()
                    self.assertEqual(prim.GetAttribute("value").Get(), default_value)
                    self.assertEqual(
                        [field.widget.model.get_value_as_float() for field in self.__fields(window, item)],
                        default_components,
                    )
                    self.assertTrue(all(value_model.is_default for value_model in item.value_models))

    def __fields(self, window, item):
        fields = [
            *ui_test.find_all(f"{window.title}//Frame/**/FloatBoundedDrag[*]"),
            *ui_test.find_all(f"{window.title}//Frame/**/IntBoundedDrag[*]"),
        ]
        return [next(field for field in fields if field.widget.model is model) for model in item.value_models]

    async def __enter_value(self, field, value):
        await field.click()
        await emulate_keyboard(KeyboardEventType.KEY_PRESS, KeyboardInput.LEFT_CONTROL, KEYBOARD_MODIFIER_FLAG_CONTROL)
        try:
            await field.click()
        finally:
            await emulate_keyboard(KeyboardEventType.KEY_RELEASE, KeyboardInput.LEFT_CONTROL, 0)
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay()
        await ui_test.emulate_char_press(str(value))
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
        await ui_test.human_delay()
