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

import os
import shutil
import tempfile
from pathlib import Path

import omni.kit.app
import omni.ui as ui
import omni.usd
import carb
from carb.input import KeyboardInput
from lightspeed.common import constants
from lightspeed.trex.home.widget import HomePageWidget
from omni.flux.utils.widget.file_pickers import LAST_SELECTED_DIRECTORY_SETTING as _LAST_SELECTED_DIRECTORY_SETTING
from omni.flux.utils.widget.file_pickers import destroy_file_picker as _destroy_file_picker
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows
from omni.kit.widget.prompt import PromptManager

_INVALID_DEPS_DIALOG_TITLE = "Invalid Project Dependencies"
_OPEN_PROJECT_PICKER_TITLE = "Open an RTX Remix project"
_PROJECT_WIZARD_TITLE = "RTX Remix Project Wizard"


class TestHomeWidgetInvalidDepsFlow(AsyncTestCase):
    async def setUp(self):
        await self._destroy_test_windows()
        await arrange_windows()
        self._temp_dir = tempfile.TemporaryDirectory(dir=Path.cwd())
        self._project_path = self._copy_centralized_project_fixture_with_invalid_deps(Path(self._temp_dir.name))
        carb.settings.get_settings().set(
            _LAST_SELECTED_DIRECTORY_SETTING, self._file_picker_path(self._project_path.parent)
        )
        self._window = ui.Window(f"TestHomeWidgetInvalidDepsFlow_{id(self)}", height=800, width=1200)
        with self._window.frame:
            self._widget = HomePageWidget("")
            self._widget.show(True)
        await ui_test.human_delay(human_delay_speed=20)

    async def tearDown(self):
        self._widget.destroy()
        self._window.destroy()
        await self._destroy_test_windows()
        context = omni.usd.get_context()
        if context.can_close_stage():
            await context.close_stage_async()
        await ui_test.human_delay(human_delay_speed=10)
        self._temp_dir.cleanup()

    async def test_open_project_with_invalid_deps_cancel_keeps_wizard_closed(self):
        # Start from the Home page and use the real Open button so the complete file-picker flow is exercised.
        open_button = await self._wait_for_widget(f"{self._window.title}//Frame/**/Button[*].text=='Open'")
        self.assertIsNotNone(open_button)

        await open_button.click()

        # Select the centralized fixture project with a non-empty invalid deps directory.
        await self._select_project_in_open_file_picker(self._project_path)

        # The invalid deps confirmation must appear before any Project Wizard window opens.
        dialog = await self._wait_for_visible_window(_INVALID_DEPS_DIALOG_TITLE)
        self.assertIsNotNone(dialog)
        dialog_message = self._prompt_message_text(_INVALID_DEPS_DIALOG_TITLE)
        self.assertIn('"deps"', dialog_message)
        self.assertIn("not a valid symlink", dialog_message)
        self.assertIn("deleted", dialog_message)
        self.assertIn("all contents will be lost", dialog_message)
        self.assertNotIn(str(self._project_path.parent / constants.REMIX_DEPENDENCIES_FOLDER), dialog_message)
        self.assertIsNotNone(await self._wait_for_prompt_button(_INVALID_DEPS_DIALOG_TITLE, "Rebuild"))
        self.assertIsNotNone(await self._wait_for_prompt_button(_INVALID_DEPS_DIALOG_TITLE, "Reveal in Explorer"))
        cancel_button = await self._wait_for_prompt_button(_INVALID_DEPS_DIALOG_TITLE, "Cancel")
        self.assertIsNotNone(cancel_button)
        self.assertFalse(self._is_window_visible(_PROJECT_WIZARD_TITLE))

        # Cancel must abort the open flow completely instead of continuing into repair.
        await cancel_button.click()
        await ui_test.human_delay(human_delay_speed=20)
        dialog.destroy()
        self.assertFalse(self._is_window_visible(_PROJECT_WIZARD_TITLE))

    async def test_open_project_with_invalid_deps_rebuild_opens_wizard(self):
        # Start from the Home page and select the broken project through the same UI path a user takes.
        open_button = await self._wait_for_widget(f"{self._window.title}//Frame/**/Button[*].text=='Open'")
        self.assertIsNotNone(open_button)

        await open_button.click()
        await self._select_project_in_open_file_picker(self._project_path)

        # The confirmation dialog gates repair, and the wizard must still be closed before Rebuild is clicked.
        dialog = await self._wait_for_visible_window(_INVALID_DEPS_DIALOG_TITLE)
        self.assertIsNotNone(dialog)
        self.assertFalse(self._is_window_visible(_PROJECT_WIZARD_TITLE))

        # Rebuild confirms that deps may be replaced and should continue into the Project Wizard.
        rebuild_button = await self._wait_for_prompt_button(_INVALID_DEPS_DIALOG_TITLE, "Rebuild")
        self.assertIsNotNone(rebuild_button)
        await rebuild_button.click()
        dialog.destroy()
        await ui_test.human_delay(human_delay_speed=50)
        self.assertIsNotNone(await self._wait_for_visible_window(_PROJECT_WIZARD_TITLE))

    async def test_open_project_with_empty_invalid_deps_opens_wizard_without_prompt(self):
        # Convert the fixture's invalid deps directory into an empty directory, which can be safely rebuilt later.
        deps_directory = self._project_path.parent / constants.REMIX_DEPENDENCIES_FOLDER
        shutil.rmtree(deps_directory)
        deps_directory.mkdir()

        # Use the real Home Open button and file picker so this follows the same open path as a user.
        open_button = await self._wait_for_widget(f"{self._window.title}//Frame/**/Button[*].text=='Open'")
        self.assertIsNotNone(open_button)

        await open_button.click()
        await self._select_project_in_open_file_picker(self._project_path)

        # Empty invalid deps does not need a prompt before repair, so the wizard opens directly. The actual deps
        # replacement is owned by create_folder_symlinks() when the wizard has the RTX Remix path needed to rebuild it.
        self.assertIsNotNone(await self._wait_for_visible_window(_PROJECT_WIZARD_TITLE))
        self.assertFalse(self._is_window_visible(_INVALID_DEPS_DIALOG_TITLE))
        self.assertTrue(deps_directory.exists())

    @staticmethod
    def _copy_centralized_project_fixture_with_invalid_deps(root_path: Path) -> Path:
        project_root = root_path / "project_example"
        shutil.copytree(_get_test_data("usd/project_example"), project_root)
        deps_directory = project_root / constants.REMIX_DEPENDENCIES_FOLDER
        shutil.rmtree(deps_directory, ignore_errors=True)
        deps_directory.mkdir()
        (deps_directory / "existing.txt").write_text("keep", encoding="utf-8")
        return project_root / "combined.usda"

    async def _select_project_in_open_file_picker(self, project_path: Path):
        directory_field = await self._wait_for_widget(
            f"{_OPEN_PROJECT_PICKER_TITLE}//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
        )
        file_name_field = await self._wait_for_widget(
            f"{_OPEN_PROJECT_PICKER_TITLE}//Frame/**/StringField[*].style_type_name_override=='Field'"
        )
        open_button = await self._wait_for_widget(f"{_OPEN_PROJECT_PICKER_TITLE}//Frame/**/Button[*].text=='Open'")
        self.assertIsNotNone(directory_field)
        self.assertIsNotNone(file_name_field)
        self.assertIsNotNone(open_button)

        await self._select_file_picker_directory(directory_field, project_path.parent)
        await file_name_field.input(project_path.name, end_key=KeyboardInput.ENTER)
        for _ in range(300):
            if open_button.widget.enabled and file_name_field.model.get_value_as_string() == project_path.name:
                break
            await omni.kit.app.get_app().next_update_async()
        self.assertTrue(open_button.widget.enabled)
        await open_button.click()
        await ui_test.human_delay(human_delay_speed=20)

    async def _select_file_picker_directory(self, directory_field, directory: Path):
        expected_directory = self._file_picker_path(directory)
        if await self._wait_for_file_picker_directory(directory_field, expected_directory):
            return

        await directory_field.input(expected_directory, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(human_delay_speed=20)
        self.assertTrue(
            await self._wait_for_file_picker_directory(directory_field, expected_directory),
            f"File picker did not navigate to {expected_directory}. Current path: "
            f"{self._normalize_file_picker_path(directory_field)}",
        )

    async def _wait_for_file_picker_directory(self, directory_field, expected_directory: str) -> bool:
        for _ in range(300):
            if self._normalize_file_picker_path(directory_field) == expected_directory:
                return True
            await omni.kit.app.get_app().next_update_async()
        return False

    @staticmethod
    def _normalize_file_picker_path(directory_field) -> str:
        field_value = ""
        if directory_field.model._field is not None:
            field_value = directory_field.model._field.model.get_value_as_string()
        return (field_value or directory_field.model._path or "").replace("\\", "/").rstrip("/")

    @staticmethod
    def _file_picker_path(path: Path) -> str:
        return os.path.abspath(path).replace("\\", "/").rstrip("/")

    @staticmethod
    async def _wait_for_visible_window(title: str, timeout_steps: int = 50):
        for _ in range(timeout_steps):
            window = TestHomeWidgetInvalidDepsFlow._find_visible_window(title)
            if window:
                return window
            await ui_test.human_delay()
        return None

    @staticmethod
    async def _wait_for_widget(query: str, timeout_steps: int = 50):
        for _ in range(timeout_steps):
            widget = ui_test.find(query)
            if widget:
                return widget
            await ui_test.human_delay()
        return None

    @staticmethod
    async def _wait_for_prompt_button(window_title: str, text: str, timeout_steps: int = 50):
        return await TestHomeWidgetInvalidDepsFlow._wait_for_widget(
            f"{window_title}//Frame/**/Button[*].text=='{text}'", timeout_steps=timeout_steps
        )

    @staticmethod
    def _prompt_message_text(window_title: str) -> str:
        return "\n".join(
            label.widget.text for label in ui_test.find_all(f"{window_title}//Frame/**/Label[*]") if label.widget.text
        )

    @staticmethod
    def _is_window_visible(title: str) -> bool:
        return bool(TestHomeWidgetInvalidDepsFlow._find_visible_window(title))

    @staticmethod
    def _find_visible_window(title: str) -> ui.Window | None:
        for window in ui.Workspace.get_windows():
            if window.title == title and window.visible:
                return window
        return None

    @staticmethod
    async def _destroy_test_windows():
        _destroy_file_picker()
        for prompt in list(PromptManager._prompts):
            if prompt._title in {_INVALID_DEPS_DIALOG_TITLE, _OPEN_PROJECT_PICKER_TITLE, _PROJECT_WIZARD_TITLE}:
                prompt.destroy()
        for window in list(ui.Workspace.get_windows()):
            if window.title in {_INVALID_DEPS_DIALOG_TITLE, _OPEN_PROJECT_PICKER_TITLE, _PROJECT_WIZARD_TITLE}:
                window.visible = False
        await ui_test.human_delay(human_delay_speed=10)
