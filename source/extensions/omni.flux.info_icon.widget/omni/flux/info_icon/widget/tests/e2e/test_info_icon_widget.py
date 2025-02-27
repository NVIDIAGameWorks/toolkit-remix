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

import omni.kit
import omni.kit.test
import omni.usd
from omni import ui
from omni.flux.info_icon.widget import InfoIconWidget
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows

_MESSAGE_TEXT = "This is a test. 123!"


class TestOmniFluxInfoIcon(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.stage = None

    async def _setup_window(self):
        await arrange_windows(topleft_window="Stage")

        window = ui.Window("TestInfoIconWindow", height=400, width=800)

        # create and destroy
        with window.frame:
            info = InfoIconWidget(_MESSAGE_TEXT)

        self.assertIsNotNone(window)
        self.assertIsNotNone(info)

        return window, info

    async def smoke_test_message_box(self):
        # create and destroy
        window, info = await self._setup_window()
        info.destroy()
        window.destroy()

    async def test_message_box_functionality(self):
        window, info = await self._setup_window()

        await ui_test.human_delay(1)

        # This doesnt work when theres no image associated with an image which is the case here because theres no style
        # image_icon = ui_test.find(f"{window.title}//Frame/**/Image[*].identifier=='info_icon_image_id'")
        # self.assertIsNotNone(image_icon)
        # mouse_move_to = image_icon.position

        mouse_move_to = ui_test.Vec2(window.position_x + 16, window.position_y + 32)

        # Move mouse over the image to trigger "on hover" event
        await ui_test.emulate_mouse_move(mouse_move_to)

        await ui_test.human_delay(1)

        # Find the message box window that's created by InfoIconWidget on mouse hover
        message_box_label = ui_test.find("Context Info//Frame/**/Label[*].identifier=='context_tooltip'")

        # Make sure the message box showed up
        self.assertIsNotNone(message_box_label)

        # Make sure everything is rendered correctly
        self.assertEqual(_MESSAGE_TEXT, message_box_label.widget.text)

        # Tear down the widget
        info.destroy()
        window.destroy()
