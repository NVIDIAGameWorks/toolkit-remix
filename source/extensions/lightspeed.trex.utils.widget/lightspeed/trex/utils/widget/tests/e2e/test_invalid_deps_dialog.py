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

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import omni.kit.app
import omni.ui as ui
from lightspeed.trex.utils.widget import show_invalid_deps_rebuild_dialog
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.widget.prompt import PromptManager

_INVALID_DEPS_DIALOG_TITLE = "Invalid Project Dependencies"


class TestInvalidDepsDialog(AsyncTestCase):
    async def setUp(self):
        await self._destroy_test_windows()
        self._rebuild_requested = False

    async def tearDown(self):
        await self._destroy_test_windows()

    async def test_dialog_shows_destructive_copy_and_runs_reveal_action(self):
        with TemporaryDirectory() as temp_dir:
            # Render the real prompt for a project deps directory.
            deps_directory = Path(temp_dir) / "deps"
            deps_directory.mkdir()
            with patch("lightspeed.trex.utils.widget.invalid_deps_dialog.open_file_using_os_default") as reveal_mock:
                show_invalid_deps_rebuild_dialog(deps_directory, self._mark_rebuild_requested)

                # Read the visible prompt instead of inspecting constructor arguments.
                dialog = await self._wait_for_visible_window(_INVALID_DEPS_DIALOG_TITLE)
                reveal_button = await self._wait_for_prompt_button("Reveal in Explorer")
                rebuild_button = await self._wait_for_prompt_button("Rebuild")
                cancel_button = await self._wait_for_prompt_button("Cancel")

                # Verify the destructive copy is explicit and the full deps path stays out of the message.
                self.assertIsNotNone(dialog)
                dialog_message = self._prompt_message_text(_INVALID_DEPS_DIALOG_TITLE)
                self.assertIn('"deps"', dialog_message)
                self.assertIn("not a valid symlink", dialog_message)
                self.assertIn("deleted", dialog_message)
                self.assertIn("all contents will be lost", dialog_message)
                self.assertNotIn(str(deps_directory), dialog_message)
                self.assertIsNotNone(reveal_button)
                self.assertIsNotNone(rebuild_button)
                self.assertIsNotNone(cancel_button)

                # Reveal should open the deps directory for inspection without rebuilding.
                await reveal_button.click()
                reveal_mock.assert_called_once_with(str(deps_directory), highlight=True)
                self.assertFalse(self._rebuild_requested)

    async def test_dialog_runs_rebuild_action_after_next_frame(self):
        with TemporaryDirectory() as temp_dir:
            # Render a fresh prompt so the rebuild action is tested independently from Reveal closing behavior.
            deps_directory = Path(temp_dir) / "deps"
            deps_directory.mkdir()
            show_invalid_deps_rebuild_dialog(deps_directory, self._mark_rebuild_requested)
            rebuild_button = await self._wait_for_prompt_button("Rebuild")
            self.assertIsNotNone(rebuild_button)

            # Rebuild waits one frame before running the handler so the next wizard can center correctly.
            self.assertFalse(self._rebuild_requested)
            if rebuild_button is not None:
                await rebuild_button.click()

            self.assertTrue(await self._wait_for_rebuild_requested())

    def _mark_rebuild_requested(self):
        self._rebuild_requested = True

    async def _wait_for_rebuild_requested(self) -> bool:
        for _ in range(80):
            if self._rebuild_requested:
                return True
            await omni.kit.app.get_app().next_update_async()
        return False

    @staticmethod
    async def _wait_for_visible_window(title: str, timeout_steps: int = 50):
        for _ in range(timeout_steps):
            window = TestInvalidDepsDialog._find_visible_window(title)
            if window:
                return window
            await ui_test.human_delay()
        return None

    @staticmethod
    async def _wait_for_prompt_button(text: str, timeout_steps: int = 50):
        for _ in range(timeout_steps):
            widget = ui_test.find(f"{_INVALID_DEPS_DIALOG_TITLE}//Frame/**/Button[*].text=='{text}'")
            if widget:
                return widget
            await ui_test.human_delay()
        return None

    @staticmethod
    def _prompt_message_text(window_title: str) -> str:
        return "\n".join(
            label.widget.text for label in ui_test.find_all(f"{window_title}//Frame/**/Label[*]") if label.widget.text
        )

    @staticmethod
    def _find_visible_window(title: str) -> ui.Window | None:
        for window in ui.Workspace.get_windows():
            if window.title == title and window.visible:
                return window
        return None

    @staticmethod
    async def _destroy_test_windows():
        for prompt in list(PromptManager._prompts):
            if prompt._title == _INVALID_DEPS_DIALOG_TITLE:
                prompt.destroy()
        for window in list(ui.Workspace.get_windows()):
            if window.title == _INVALID_DEPS_DIALOG_TITLE:
                window.destroy()
        await ui_test.human_delay(human_delay_speed=10)
