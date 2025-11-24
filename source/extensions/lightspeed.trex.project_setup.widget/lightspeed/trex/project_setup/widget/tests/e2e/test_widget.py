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
import shutil
import tempfile
from pathlib import Path

import omni.ui as ui
import omni.usd
from carb.input import KeyboardInput
from lightspeed.trex.project_setup.widget import ProjectSetupPane as _ProjectSetupPane
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
        temp_dir.cleanup()


class TestProjectSetupWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await arrange_windows()

    async def __setup_widget(self, title: str):
        window = ui.Window(title, height=800, width=400)
        with window.frame:
            wid = _ProjectSetupPane("")
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

            load_mod_button = ui_test.find(f"{_window.title}//Frame/**/Button[*].text=='Load Existing File'")
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

            # Clear the value of the filename field
            file_name_field.widget.model.set_value("")
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

            load_mod_button = ui_test.find(f"{_window.title}//Frame/**/Button[*].text=='Load Existing File'")
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
