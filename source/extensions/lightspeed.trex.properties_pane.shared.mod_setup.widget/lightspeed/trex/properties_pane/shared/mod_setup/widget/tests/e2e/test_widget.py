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

import contextlib
import os
import shutil
import tempfile
from pathlib import Path

import carb.input as carb_input
import omni.ui as ui
import omni.usd
from carb.input import KeyboardInput
from lightspeed.trex.properties_pane.shared.mod_setup.widget import ModSetupPane as _ModSetupPane
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, open_stage, wait_stage_loading


@contextlib.asynccontextmanager
async def make_temp_directory(context):
    temp_dir = tempfile.TemporaryDirectory()  # noqa PLR1732
    try:
        yield temp_dir
    finally:
        if context.can_close_stage():
            await context.close_stage_async()
        temp_dir.cleanup()


class TestModSetupWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await arrange_windows()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    async def __setup_widget(self, title: str):
        window = ui.Window(title, height=800, width=400)
        with window.frame:
            wid = _ModSetupPane("")
            wid.show(True)

        await ui_test.human_delay(human_delay_speed=1)

        return window, wid

    async def __destroy(self, window, wid):
        wid.destroy()
        window.destroy()
        for other_window in ui.Workspace.get_windows():
            try:
                prompt_dialog = ui_test.find(other_window.title)
                if prompt_dialog and not prompt_dialog.window.visible:
                    prompt_dialog.widget.destroy()
            except AttributeError:
                pass

    async def test_capture_item_centered(self):
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            # setup
            shutil.copytree(_get_test_data("usd/project_example"), f"{temp_dir.name}/project_example")
            # we duplicate a lot of capture to have the current one in the middle of the list
            number_captures = 20
            chars = ["a", "d"]
            for char in chars:
                for i in range(number_captures):
                    shutil.copy(
                        _get_test_data("usd/project_example/.deps/captures/capture.usda"),
                        f"{temp_dir.name}/project_example/.deps/captures/{char}_capture{i}.usda",
                    )

            await open_stage(f"{temp_dir.name}/project_example/combined.usda")
            _window, _wid = await self.__setup_widget("test_capture_item_centered")  # Keep in memory during test

            await ui_test.human_delay(human_delay_speed=10)

            tree_capture_scroll_frame = ui_test.find(
                f"{_window.title}//Frame/**/ScrollingFrame[*].identifier=='TreeCaptureScrollFrame'"
            )
            items = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_title'")
            self.assertIsNotNone(tree_capture_scroll_frame)
            self.assertEqual(len(items), (number_captures * len(chars)) + 1)

            # 2 pixels delta
            self.assertTrue(
                tree_capture_scroll_frame.center.y - 2
                < items[number_captures].center.y
                < tree_capture_scroll_frame.center.y + 2
            )

            await self.__destroy(_window, _wid)

    async def test_capture_list_refresh(self):
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            # Setup
            shutil.copytree(_get_test_data("usd/project_example"), f"{temp_dir.name}/project_example")
            await open_stage(f"{temp_dir.name}/project_example/combined.usda")
            _window, _wid = await self.__setup_widget("test_capture_item_centered")  # Keep in memory during test
            await ui_test.human_delay(human_delay_speed=10)

            # Ensure there is one capture
            items = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_title'")
            self.assertEqual(len(items), 1)

            # Duplicate the capture file
            shutil.copy(
                _get_test_data("usd/project_example/.deps/captures/capture.usda"),
                f"{temp_dir.name}/project_example/.deps/captures/duplicate_capture.usda",
            )

            # Check if refresh icon button exists and click it
            refresh_capture_tree_button = ui_test.find(f"{_window.title}//Frame/**/Image[*].name=='Refresh'")
            self.assertIsNotNone(refresh_capture_tree_button)
            await refresh_capture_tree_button.click()
            await ui_test.human_delay(human_delay_speed=5)

            # Ensure there are now two captures
            items = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_title'")
            self.assertEqual(len(items), 2)

            # Delete the duplicate capture
            os.remove(f"{temp_dir.name}/project_example/.deps/captures/duplicate_capture.usda")
            await ui_test.human_delay(human_delay_speed=3)

            # Refresh again
            await refresh_capture_tree_button.click()
            await ui_test.human_delay(human_delay_speed=5)

            # Ensure there is only one capture
            items = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_title'")
            self.assertEqual(len(items), 1)

            await self.__destroy(_window, _wid)

    async def test_delete_capture_path(self):
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            # Setup
            shutil.copytree(_get_test_data("usd/project_example"), f"{temp_dir.name}/project_example")
            await open_stage(f"{temp_dir.name}/project_example/combined.usda")
            _window, _wid = await self.__setup_widget("test_capture_item_centered")  # Keep in memory during test
            await ui_test.human_delay(human_delay_speed=10)

            # Select capture path text field, save orig path, and ensure empty path label not visible
            capture_path_field = ui_test.find(f"{_window.title}//Frame/**/StringField[*].name=='CapturePathField'")
            empty_path_label = ui_test.find(
                f"{_window.title}//Frame/**/Label[*].name=='USDPropertiesWidgetValueOverlay'"
            )
            self.assertIsNotNone(capture_path_field)
            original_capture_path = capture_path_field.widget.model.get_value_as_string()
            self.assertFalse(empty_path_label.widget.visible)

            # Select and delete the contents of the string field
            await capture_path_field.double_click()
            await ui_test.emulate_keyboard_press(carb_input.KeyboardInput.DEL)

            # Ensure that the model path is empty
            self.assertEqual(capture_path_field.widget.model.get_value_as_string(), "")

            # Ensure that the empty field label is visible and accurate
            self.assertTrue(empty_path_label.widget.visible)
            self.assertEqual(empty_path_label.widget.text, "Capture directory path...")

            # Press enter and ensure  the origi path has returned and label is not visible/overlapping
            await ui_test.emulate_keyboard_press(carb_input.KeyboardInput.ENTER)
            self.assertEqual(capture_path_field.widget.model.get_value_as_string(), original_capture_path)
            self.assertFalse(empty_path_label.widget.visible)

            await self.__destroy(_window, _wid)

    async def test_mod_file_import_valid(self):
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            # Setup
            example_dir = _get_test_data("usd/project_example")
            shutil.copytree(example_dir, f"{temp_dir.name}/project_example")
            shutil.copyfile(f"{example_dir}/replacements.usda", f"{temp_dir.name}/project_example/replacements02.usda")
            await open_stage(f"{temp_dir.name}/project_example/combined.usda")
            _window, _wid = await self.__setup_widget("test_mod_file_import_valid")  # Keep in memory during test
            await ui_test.human_delay(human_delay_speed=80)

            load_mod_button = ui_test.find(f"{_window.title}//Frame/**/Button[*].text=='Load existing mod file'")
            await load_mod_button.click()
            await ui_test.human_delay(10)

            # The choose mod file window should now be opened
            file_picker_window_title = "Select an existing mod file"
            select_button = ui_test.find(f"{file_picker_window_title}//Frame/**/Button[*].text=='Select'")

            file_name_field = ui_test.find(
                f"{file_picker_window_title}//Frame/**/StringField[*].style_type_name_override=='Field'"
            )

            self.assertIsNotNone(select_button)
            self.assertIsNotNone(file_name_field)

            await file_name_field.input("replacements02.usda", end_key=KeyboardInput.ENTER)
            await ui_test.human_delay(100)

            await select_button.click()
            await ui_test.human_delay(100)

            buttons = []
            for other_window in ui.Workspace.get_windows():
                button = ui_test.find(f"{other_window.title}//Frame/**/Button[*].text=='Okay'")
                if button:
                    buttons.append(button)

            # Making sure that we are hitting a message dialog
            self.assertEqual(len(buttons), 0)

            await self.__destroy(_window, _wid)

    async def test_mod_file_import_invalid(self):
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            # Setup
            example_dir = _get_test_data("usd/project_example")
            shutil.copytree(example_dir, f"{temp_dir.name}/project_example")
            dir_path = Path(temp_dir.name)
            file_name = "test.usda"
            layer_path = dir_path / "project_example" / file_name
            layer_path.touch()
            layer_path.write_text("#usda 1.0")
            await open_stage(f"{temp_dir.name}/project_example/combined.usda")
            _window, _wid = await self.__setup_widget("test_mod_file_import_invalid")  # Keep in memory during test
            await ui_test.human_delay(human_delay_speed=80)

            load_mod_button = ui_test.find(f"{_window.title}//Frame/**/Button[*].text=='Load existing mod file'")
            await load_mod_button.click()
            await ui_test.human_delay(10)

            # The choose mod file window should now be opened
            file_picker_window_title = "Select an existing mod file"
            select_button = ui_test.find(f"{file_picker_window_title}//Frame/**/Button[*].text=='Select'")
            file_name_field = ui_test.find(
                f"{file_picker_window_title}//Frame/**/StringField[*].style_type_name_override=='Field'"
            )

            self.assertIsNotNone(select_button)
            self.assertIsNotNone(file_name_field)

            await file_name_field.input("test.usda", end_key=KeyboardInput.ENTER)
            await ui_test.human_delay(150)

            await select_button.click()
            await ui_test.human_delay(100)

            buttons = []
            for other_window in ui.Workspace.get_windows():
                button = ui_test.find(f"{other_window.title}//Frame/**/Button[*].text=='Okay'")
                if button:
                    buttons.append(button)

            # Making sure that we are hitting a message dialog
            self.assertEqual(len(buttons), 1)
            await buttons[0].click()
            await ui_test.human_delay(3)

            file_browser = ui_test.find(file_picker_window_title)
            file_browser.widget.destroy()

            await self.__destroy(_window, _wid)
