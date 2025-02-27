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
import omni.ui as ui
import omni.usd
from carb.input import KeyboardInput
from omni.flux.utils.widget.file_pickers.file_picker import destroy_file_picker as _destroy_file_picker
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker
from omni.kit import ui_test
from omni.kit.test_suite.helpers import get_test_data_path


class TestFilePicker(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def __setup_widget(self, name):
        window = ui.Window(f"TestFilePicker{name}", height=500, width=700)
        _open_file_picker(
            name,
            lambda *_: None,
            lambda *_: None,
            current_file=get_test_data_path(__name__, "usd/test_file_picker_assets"),
        )

        await ui_test.human_delay(human_delay_speed=1)
        return window

    async def __destroy_setup(self, window):
        await ui_test.human_delay(human_delay_speed=1)
        _destroy_file_picker()
        window.frame.clear()
        window.destroy()
        await ui_test.human_delay(human_delay_speed=1)

    async def test_search_bar(self):
        # Setup
        test_name = "test_search_bar"
        _window = await self.__setup_widget(test_name)
        await ui_test.human_delay(human_delay_speed=10)

        # Ensure that all expected test cube assets are present
        tree_view = ui_test.find_all(f"{test_name}//Frame/**/TreeView[*]")[1]
        tree_view_items = tree_view.widget.model.get_item_children(None)
        self.assertEqual(len(tree_view_items), 3)

        # Search for "cube_0" and TAB off to search
        search_field = ui_test.find_all(f"{test_name}//Frame/**/StringField[*]")[1]
        await search_field.input("cube_0", end_key=KeyboardInput.TAB)
        await ui_test.human_delay(human_delay_speed=1)

        # Ensure that only cube_0.usda is present
        searched_items = ui_test.find_all(f"{test_name}//Frame/**/TreeView[*]")[1].widget.model.get_item_children(None)
        self.assertEqual(len(searched_items), 1)
        self.assertEqual(searched_items[0].name, "cube_0.usda")

        # Click 'x' to reset
        word_button = ui_test.find(f"{test_name}//Frame/**/Button[*].identifier=='search_word_button'")
        self.assertIsNotNone(word_button)
        await word_button.click()

        # Search for ".usda" and TAB off to search
        await search_field.input(".usda", end_key=KeyboardInput.TAB)
        await ui_test.human_delay(human_delay_speed=1)

        # Ensure that all cube assets are present
        searched_items = ui_test.find_all(f"{test_name}//Frame/**/TreeView[*]")[1].widget.model.get_item_children(None)
        self.assertEqual(len(searched_items), 3)

        # Click 'x' to reset
        word_button = ui_test.find(f"{test_name}//Frame/**/Button[*].identifier=='search_word_button'")
        self.assertIsNotNone(word_button)
        await word_button.click()

        # Search for "big cube"
        await search_field.input("big cube", end_key=KeyboardInput.TAB)
        await ui_test.human_delay(human_delay_speed=1)

        # Ensure only cube_big.usda is present
        searched_items = ui_test.find_all(f"{test_name}//Frame/**/TreeView[*]")[1].widget.model.get_item_children(None)
        self.assertEqual(len(searched_items), 1)
        self.assertEqual(searched_items[0].name, "cube_big.usda")

        # Click 'x' for "big" to reduce the search to only "cube"
        word_buttons = ui_test.find_all(f"{test_name}//Frame/**/Button[*].identifier=='search_word_button'")
        self.assertEqual(len(word_buttons), 2)
        await word_buttons[0].click()

        # Ensure that all cube assets are present
        searched_items = ui_test.find_all(f"{test_name}//Frame/**/TreeView[*]")[1].widget.model.get_item_children(None)
        self.assertEqual(len(searched_items), 3)

        await self.__destroy_setup(_window)
