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

__all__ = ("TestColorField",)

import uuid
from collections.abc import Iterable

import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from carb.input import KeyboardInput
from omni.flux.property_widget_builder.delegates.float_value.color import ColorField
from pxr import Gf


class MockValueModel(ui.AbstractValueModel):
    def __init__(self):
        super().__init__()
        self._value = Gf.Vec3d(0.2, 0.2, 0.2)

    def get_attributes_raw_value(self, _):
        return self._value

    def get_value(self):
        return self._value

    def set_value(self, value):
        self._value = value
        self._value_changed()


class MockItem(ui.AbstractItem):
    def __init__(self):
        super().__init__()
        self.value_models = [MockValueModel()]


class TestColorField(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self.window = ui.Window(
            f"{self.__class__.__name__}_{str(uuid.uuid1())}",
            height=200,
            width=200,
            position_x=0,
            position_y=0,
        )
        self.item = MockItem()
        with self.window.frame:
            self.color_field = ColorField()
            self.widgets = self.color_field.build_ui(self.item)
        self.window.width = 200
        self.window.height = 200

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

    async def tearDown(self):
        for widget in self.widgets:
            widget.destroy()
        self.window.destroy()

    def assertColorEquals(self, values: Iterable[float]):  # noqa: N802
        """
        Tests both the item value model and the widget children values are set to the specified values.
        """
        color_widget = self.widgets[0]
        for child, value in zip(color_widget.model.get_item_children(), values):
            current = color_widget.model.get_item_value_model(child).get_value_as_float()
            self.assertAlmostEqual(current, value)

        for v1, v2 in zip(self.item.value_models[0].get_value(), values):
            self.assertAlmostEqual(v1, v2)

    async def test_pick_color(self):
        """
        Emulate picking a value from the color picker.
        """
        # default values
        self.assertColorEquals([0.2, 0.2, 0.2])

        widget_ref = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'"
        )

        # Open color picker
        await widget_ref.click()

        # First float field
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.TAB)
        await omni.kit.ui_test.emulate_char_press("0.8")
        # Second float field
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.TAB)
        await omni.kit.ui_test.emulate_char_press("0.5")
        # Third float field
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.TAB)
        await omni.kit.ui_test.emulate_char_press("0.4")
        # Deselect color picker to commit changes
        await omni.kit.ui_test.emulate_mouse_move_and_click(widget_ref.offset(-3, -3))

        self.assertColorEquals([0.8, 0.5, 0.4])

    async def test_model_changes(self):
        """
        Test changing the model directly forwards events to update the ColorWidget.
        """
        self.assertColorEquals([0.2, 0.2, 0.2])
        self.item.value_models[0].set_value(Gf.Vec3d(0.6, 0.5, 0.4))
        self.assertColorEquals([0.6, 0.5, 0.4])
