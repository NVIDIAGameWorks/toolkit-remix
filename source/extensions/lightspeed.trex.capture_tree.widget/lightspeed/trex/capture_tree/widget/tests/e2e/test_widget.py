"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
from lightspeed.trex.capture_tree.widget import CaptureWidget as _CaptureWidget
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, open_stage


@contextlib.asynccontextmanager
async def make_temp_directory(context):
    temp_dir = tempfile.TemporaryDirectory()  # noqa PLR1732
    try:
        yield temp_dir
    finally:
        if context.can_close_stage():
            await context.close_stage_async()
        await ui_test.human_delay(human_delay_speed=10)
        temp_dir.cleanup()


class TestCaptureTreeWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await arrange_windows()

    # After running each test
    async def tearDown(self):
        pass

    async def __setup_widget(self, title: str):
        window = ui.Window(title, height=800, width=400)
        with window.frame:
            wid = _CaptureWidget("")
            wid.show(True)

        await ui_test.human_delay(human_delay_speed=1)

        return window, wid

    async def __destroy(self, window, wid):
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
                        _get_test_data("usd/project_example/deps/captures/capture.usda"),
                        f"{temp_dir.name}/project_example/deps/captures/{char}_capture{i}.usda",
                    )

            await open_stage(f"{temp_dir.name}/project_example/combined.usda")
            _window, _wid = await self.__setup_widget("test_capture_item_centered")  # Keep in memory during test

            # Set the capture directory path
            _wid.set_capture_dir_field(f"{temp_dir.name}/project_example/deps/captures")

            await ui_test.human_delay(human_delay_speed=50)

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
            _window, _wid = await self.__setup_widget("test_capture_list_refresh")  # Keep in memory during test

            # Set the capture directory path
            _wid.set_capture_dir_field(f"{temp_dir.name}/project_example/deps/captures")

            await ui_test.human_delay(human_delay_speed=10)

            # Ensure there is one capture
            items = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_title'")
            self.assertEqual(len(items), 1)

            # Duplicate the capture file
            shutil.copy(
                _get_test_data("usd/project_example/deps/captures/capture.usda"),
                f"{temp_dir.name}/project_example/deps/captures/duplicate_capture.usda",
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
            os.remove(f"{temp_dir.name}/project_example/deps/captures/duplicate_capture.usda")
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

            # Set the capture directory path
            _wid.set_capture_dir_field(f"{temp_dir.name}/project_example/deps/captures")

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
            # Normalize paths to handle different separators on Windows
            returned_path = capture_path_field.widget.model.get_value_as_string().replace("\\", "/")
            expected_path = original_capture_path.replace("\\", "/")
            self.assertEqual(returned_path, expected_path)
            self.assertFalse(empty_path_label.widget.visible)

            await self.__destroy(_window, _wid)

    async def test_capture_window_hover(self):
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

            # Set the capture directory path
            _wid.set_capture_dir_field(f"{temp_dir.name}/project_example/deps/captures")

            await ui_test.human_delay(human_delay_speed=80)

            # Make sure we have the capture window and it's not visible.
            capture_window = ui_test.find("Capture tree window")
            self.assertIsNotNone(capture_window)
            self.assertFalse(capture_window.widget.visible)

            # Hover over the capture file to make the capture window visible.
            capture_item = ui_test.find(f"{_window.title}//Frame/**/Label[*].identifier=='item_title'")
            await ui_test.emulate_mouse_move(capture_item.position)
            await ui_test.human_delay(80)

            self.assertTrue(capture_window.widget.visible)

            # Make sure when interacting with the capture dir field, the behavior remains by moving over
            # the capture window a few times.
            capture_dir_field = ui_test.find(f"{_window.title}//Frame/**/StringField[*].name=='CapturePathField'")
            click_pos = ui_test.Vec2(
                capture_dir_field.widget.screen_position_x + 10, capture_dir_field.widget.screen_position_y + 5
            )
            await ui_test.emulate_mouse_move_and_click(click_pos)
            await ui_test.human_delay(5)
            await ui_test.emulate_mouse_move(capture_item.position)

            self.assertTrue(capture_window.widget.visible)

            capture_dir_label = ui_test.find(f"{_window.title}//Frame/**/Label[*].text=='Capture Directory'")

            self.assertIsNotNone(capture_dir_label)

            await ui_test.emulate_mouse_move_and_click(capture_dir_label.position)
            await ui_test.human_delay(5)

            self.assertFalse(capture_window.widget.visible)

            await ui_test.emulate_mouse_move(capture_item.position)
            await ui_test.human_delay(5)

            self.assertTrue(capture_window.widget.visible)

            await self.__destroy(_window, _wid)
