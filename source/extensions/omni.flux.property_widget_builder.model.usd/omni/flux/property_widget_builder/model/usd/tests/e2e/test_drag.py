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

__all__ = ("TestUSDDragField",)

import omni.kit.app
import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
import omni.usd
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardInput
from omni.flux.property_widget_builder.model.usd import USDAttributeXformItem, USDDelegate, USDModel
from omni.flux.property_widget_builder.model.usd.setup_ui import USDPropertyWidget
from pxr import Gf, Sdf


class TestUSDDragField(omni.kit.test.AsyncTestCase):
    """Exercise linked numeric groups through real USD data and production builders."""

    async def setUp(self):
        """Create real integer and float vector attributes."""
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        stage = self._context.get_stage()
        prim = stage.DefinePrim("/World/LinkedFields", "Xform")
        self._int_attr = prim.CreateAttribute("intValues", Sdf.ValueTypeNames.Int3)
        self._int_attr.Set(Gf.Vec3i(2, 4, 8))
        self._float_attr = prim.CreateAttribute("floatValues", Sdf.ValueTypeNames.Float3)
        self._float_attr.Set(Gf.Vec3f(1.0, 3.0, 5.0))

    async def tearDown(self):
        """Close the temporary stage."""
        await self._context.close_stage_async()

    async def test_int_link_uses_real_data_and_shared_row_coordination(self):
        """Production Int linking should edit USD and yield when another row links."""
        int_item = USDAttributeXformItem("", [self._int_attr.GetPath()], display_attr_names=["Integers"])
        float_item = USDAttributeXformItem("", [self._float_attr.GetPath()], display_attr_names=["Floats"])
        model = USDModel(context_name="")
        delegate = USDDelegate()
        window = ui.Window("TestUSDIntLinkedEdit", width=500, height=240)
        with window.frame:
            widget = USDPropertyWidget(context_name="", model=model, delegate=delegate)
        model.set_items([int_item, float_item])

        try:
            await omni.kit.ui_test.human_delay(human_delay_speed=8)
            int_identifier = "linked_drag_field_link_" + "".join(
                name_model.get_value_as_string() for name_model in int_item.name_models
            )
            float_identifier = "linked_drag_field_link_" + "".join(
                name_model.get_value_as_string() for name_model in float_item.name_models
            )
            int_links = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/Image[*].identifier=='{int_identifier}'")
            self.assertEqual(len(int_links), 2)

            await int_links[0].click()
            await omni.kit.ui_test.human_delay(human_delay_speed=4)
            self.assertEqual(self._int_attr.Get(), Gf.Vec3i(2, 2, 2))

            await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
            await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.BACKSPACE)
            await omni.kit.ui_test.emulate_char_press("6")
            await omni.kit.ui_test.human_delay()
            await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
            await omni.kit.ui_test.human_delay(human_delay_speed=8)
            self.assertEqual(self._int_attr.Get(), Gf.Vec3i(6, 6, 6))

            float_links = omni.kit.ui_test.find_all(
                f"{window.title}//Frame/**/Image[*].identifier=='{float_identifier}'"
            )
            await float_links[0].click()
            await omni.kit.ui_test.human_delay(human_delay_speed=4)
            int_links = omni.kit.ui_test.find_all(f"{window.title}//Frame/**/Image[*].identifier=='{int_identifier}'")
            self.assertEqual([link.widget.name for link in int_links], ["LinkOff", "LinkOff"])
            self.assertEqual([link.widget.name for link in float_links], ["Link", "Link"])
        finally:
            widget.destroy()
            window.destroy()
