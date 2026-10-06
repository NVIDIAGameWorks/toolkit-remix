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

__all__ = ("TestColorField",)

import uuid

import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from carb.input import KeyboardInput
from omni.flux.property_widget_builder.model.usd import USDAttributeItem, USDDelegate, USDModel
from omni.flux.property_widget_builder.model.usd.setup_ui import USDPropertyWidget
from omni.kit.commands import execute
from omni.kit.undo import clear_stack, redo, undo
from omni.usd import get_context
from pxr import Gf, Sdf


class TestColorField(omni.kit.test.AsyncTestCase):
    """Exercise live color picker edits and cleanup through real USD property rows."""

    async def setUp(self):
        """Build a production color row backed by an in-memory USD attribute."""
        self.context = get_context("")
        await self.context.new_stage_async()
        prim = self.context.get_stage().DefinePrim("/World/Color", "Xform")
        self.color_attribute = prim.CreateAttribute("color", Sdf.ValueTypeNames.Color3f)
        self.color_attribute.Set(Gf.Vec3f(0.2, 0.2, 0.2))
        self.other_attribute = prim.CreateAttribute("intensity", Sdf.ValueTypeNames.Float)
        self.other_attribute.Set(1.0)
        self.model = USDModel(context_name="")
        self.window = ui.Window(
            f"{self.__class__.__name__}_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        with self.window.frame:
            self.property_widget = USDPropertyWidget(context_name="", model=self.model, delegate=USDDelegate())
        self.model.set_items([USDAttributeItem("", [self.color_attribute.GetPath()])])
        await omni.kit.ui_test.human_delay(human_delay_speed=1)

    async def tearDown(self):
        """Cancel active edits before releasing the UI and temporary stage."""
        self.model.set_items([])
        self.property_widget.destroy()
        self.model.destroy()
        self.window.destroy()
        clear_stack()
        await self.context.close_stage_async()

    async def test_edit_color_with_picker_open_updates_usd_and_dismissal_groups_undo(self):
        """Successive picker edits update USD live and undo as one completed session."""
        widget_ref = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'"
        )
        # Keep the popup open while each RGB field changes the scene color.
        await widget_ref.click()
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.TAB)
        await omni.kit.ui_test.human_delay()
        expected_color = [0.2, 0.2, 0.2]
        for index, value in enumerate((0.8, 0.5, 0.4)):
            await omni.kit.ui_test.emulate_char_press(str(value))
            await omni.kit.ui_test.human_delay()
            await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.TAB)
            await omni.kit.ui_test.human_delay()
            expected_color[index] = value
            self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(*expected_color))

        # Dismissing the popup must leave one undo step for all three component edits.
        await omni.kit.ui_test.emulate_mouse_move_and_click(widget_ref.offset(-3, -3))
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.5, 0.4))
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.5, 0.4))

    async def test_remove_color_row_with_picker_open_keeps_later_command_undo_separate(self):
        """Removing an actively edited row releases its undo group before the next command."""
        widget_ref = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'"
        )
        await widget_ref.click()
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.TAB)
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.emulate_char_press("0.8")
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.TAB)
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))

        # Replacing the property selection cancels the row while its picker is still open.
        self.model.set_items([])
        await omni.kit.ui_test.human_delay()
        execute(
            "ChangeProperty",
            prop_path=self.other_attribute.GetPath(),
            value=2.0,
            prev=1.0,
            usd_context_name="",
        )
        self.assertEqual(self.other_attribute.Get(), 2.0)
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.other_attribute.Get(), 1.0)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
