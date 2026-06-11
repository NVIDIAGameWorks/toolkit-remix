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

import carb.settings
import omni.kit.app
import omni.ui as ui
from carb.input import KeyboardInput
from lightspeed.common import constants
from lightspeed.trex.project_wizard.core import ProjectWizardKeys as _ProjectWizardKeys
from lightspeed.trex.project_wizard.open_project_page.widget import WizardOpenProjectPage
from omni.flux.utils.widget.file_pickers import LAST_SELECTED_DIRECTORY_SETTING as _LAST_SELECTED_DIRECTORY_SETTING
from omni.flux.utils.widget.file_pickers import destroy_file_picker as _destroy_file_picker
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.widget.prompt import PromptManager

_INVALID_DEPS_DIALOG_TITLE = "Invalid Project Dependencies"
_OPEN_PROJECT_PICKER_TITLE = "Open an RTX Remix project"


class TestWizardOpenProjectPage(AsyncTestCase):
    async def setUp(self):
        await self._destroy_test_windows()
        self._temp_dir = tempfile.TemporaryDirectory(dir=Path.cwd())
        self._project_path = self._copy_centralized_project_fixture(Path(self._temp_dir.name))
        carb.settings.get_settings().set(
            _LAST_SELECTED_DIRECTORY_SETTING, self._file_picker_path(self._project_path.parent)
        )
        self._page = WizardOpenProjectPage("")
        self._requested_next = False
        self._page.set_request_next_fn(self._mark_requested_next)

    async def tearDown(self):
        self._page.destroy()
        await self._destroy_test_windows()
        self._temp_dir.cleanup()

    async def test_open_project_with_invalid_deps_prompts_before_advancing(self):
        # Start the real open-project page so it opens the same file picker as the wizard.
        self._make_deps_directory_invalid_with_contents()
        self._page.create_ui()
        await ui_test.human_delay(human_delay_speed=20)

        # Pick the centralized fixture project through the visible file picker.
        await self._select_project_in_open_file_picker(self._project_path)

        # Non-empty invalid deps must stop on the confirmation dialog before the wizard page advances.
        dialog = await self._wait_for_visible_window(_INVALID_DEPS_DIALOG_TITLE)
        self.assertIsNotNone(dialog)
        dialog_message = self._prompt_message_text(_INVALID_DEPS_DIALOG_TITLE)
        self.assertIn('"deps"', dialog_message)
        self.assertIn("not a valid symlink", dialog_message)
        self.assertIn("deleted", dialog_message)
        self.assertIn("all contents will be lost", dialog_message)
        self.assertNotIn(str(self._project_path.parent / constants.REMIX_DEPENDENCIES_FOLDER), dialog_message)
        self.assertIsNotNone(await self._wait_for_prompt_button("Reveal in Explorer"))
        rebuild_button = await self._wait_for_prompt_button("Rebuild")
        self.assertIsNotNone(rebuild_button)
        self.assertFalse(self._requested_next)
        self.assertNotIn("project_path", self._page._setup_page.__dict__)

        # Rebuild confirms the destructive repair and lets the page advance on the next frame.
        await rebuild_button.click()
        dialog.destroy()
        self.assertTrue(await self._wait_for_requested_next())
        self.assertEqual(str(self._project_path), self._page._setup_page.project_path)
        self.assertEqual(self._project_path, self._page.payload[_ProjectWizardKeys.PROJECT_FILE.value])

    async def test_open_project_with_empty_invalid_deps_advances_without_prompting(self):
        # Empty invalid deps has no user data to protect, so no confirmation is needed before repair.
        deps_directory = self._project_path.parent / constants.REMIX_DEPENDENCIES_FOLDER
        shutil.rmtree(deps_directory, ignore_errors=True)
        deps_directory.mkdir()

        # Use the real page and file picker to prove the wizard-entry path advances directly.
        self._page.create_ui()
        await ui_test.human_delay(human_delay_speed=20)
        await self._select_project_in_open_file_picker(self._project_path)

        # The page moves to setup without showing the destructive-action confirmation.
        self.assertTrue(await self._wait_for_requested_next())
        self.assertFalse(self._is_window_visible(_INVALID_DEPS_DIALOG_TITLE))
        self.assertTrue(deps_directory.exists())
        self.assertEqual(str(self._project_path), self._page._setup_page.project_path)

    def _mark_requested_next(self):
        self._requested_next = True

    def _make_deps_directory_invalid_with_contents(self):
        deps_directory = self._project_path.parent / constants.REMIX_DEPENDENCIES_FOLDER
        shutil.rmtree(deps_directory, ignore_errors=True)
        deps_directory.mkdir()
        (deps_directory / "existing.txt").write_text("keep", encoding="utf-8")

    @staticmethod
    def _copy_centralized_project_fixture(root_path: Path) -> Path:
        project_root = root_path / "project_example"
        shutil.copytree(_get_test_data("usd/project_example"), project_root)
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

    async def _wait_for_requested_next(self) -> bool:
        for _ in range(80):
            if self._requested_next:
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
            window = TestWizardOpenProjectPage._find_visible_window(title)
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
    async def _wait_for_prompt_button(text: str, timeout_steps: int = 50):
        return await TestWizardOpenProjectPage._wait_for_widget(
            f"{_INVALID_DEPS_DIALOG_TITLE}//Frame/**/Button[*].text=='{text}'", timeout_steps=timeout_steps
        )

    @staticmethod
    def _prompt_message_text(window_title: str) -> str:
        return "\n".join(
            label.widget.text for label in ui_test.find_all(f"{window_title}//Frame/**/Label[*]") if label.widget.text
        )

    @staticmethod
    def _is_window_visible(title: str) -> bool:
        return bool(TestWizardOpenProjectPage._find_visible_window(title))

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
            if prompt._title in {_INVALID_DEPS_DIALOG_TITLE, _OPEN_PROJECT_PICKER_TITLE}:
                prompt.destroy()
        for window in list(ui.Workspace.get_windows()):
            if window.title in {_INVALID_DEPS_DIALOG_TITLE, _OPEN_PROJECT_PICKER_TITLE}:
                window.visible = False
        await ui_test.human_delay(human_delay_speed=10)
