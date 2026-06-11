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

import shutil
import tempfile
from pathlib import Path

import omni.ui as ui
import omni.usd
from lightspeed.common.constants import REMIX_DEPENDENCIES_FOLDER as _REMIX_DEPENDENCIES_FOLDER
from lightspeed.common.constants import REMIX_FOLDER as _REMIX_FOLDER
from lightspeed.trex.contexts.extension import get_instance as _get_context_manager
from lightspeed.trex.contexts.setup import Contexts as _Contexts
from omni.flux.utils.common.symlink import create_folder_symlinks as _create_folder_symlinks
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.widget.prompt import PromptManager
from pxr import Sdf

_CAPTURE_NAME = "capture.usda"
_INVALID_DEPS_DIALOG_TITLE = "Invalid Project Dependencies"
_PROJECT_WIZARD_TITLE = "RTX Remix Project Wizard"


class TestCaptureRepairOnOpen(AsyncTestCase):
    async def setUp(self):
        await self._destroy_test_windows()
        self._temp_dir = tempfile.TemporaryDirectory(dir=Path.cwd())
        self._context_name = _Contexts.STAGE_CRAFT.value
        _get_context_manager().set_current_context(_Contexts.STAGE_CRAFT)
        self._usd_context = omni.usd.get_context(self._context_name)

    async def tearDown(self):
        await self._close_open_stage()
        await self._destroy_test_windows()
        self._usd_context = None
        self._temp_dir.cleanup()

    async def test_missing_capture_with_valid_deps_shows_capture_picker(self):
        project_path = self._copy_project_without_capture_layer()
        deps_path = project_path.parent / _REMIX_DEPENDENCIES_FOLDER
        remix_path = project_path.parent / _REMIX_FOLDER

        # Make the centralized fixture look like a real repaired project before opening it in Stagecraft.
        shutil.move(deps_path, remix_path)
        _create_folder_symlinks([(deps_path, remix_path)], create_junction=True)

        # Opening the stage directly exercises Setup._check_capture_on_open from the real Stagecraft stage event.
        await self._open_stagecraft_project(project_path)

        # The project has valid deps but no capture layer, so Stagecraft should go straight to the capture picker.
        self.assertFalse(self._is_window_visible(_INVALID_DEPS_DIALOG_TITLE))
        self.assertIsNotNone(await self._wait_for_visible_window(_PROJECT_WIZARD_TITLE))
        self.assertIsNotNone(await self._wait_for_widget(self._capture_tree_query(), timeout_steps=120))

        # The capture tree should be populated from the real deps/rtx-remix capture directory.
        capture_label = await self._wait_for_capture_label(_CAPTURE_NAME)
        self.assertIsNotNone(capture_label)

    async def test_missing_capture_with_invalid_deps_prompts_before_repair_wizard(self):
        project_path = self._copy_project_without_capture_layer()

        # The fixture's copied deps directory is a non-empty regular folder, so replacing it needs confirmation.
        await self._open_stagecraft_project(project_path)

        # The invalid-deps prompt must gate the repair wizard instead of letting the wizard appear first.
        dialog = await self._wait_for_visible_window(_INVALID_DEPS_DIALOG_TITLE)
        self.assertIsNotNone(dialog)
        self.assertFalse(self._is_window_visible(_PROJECT_WIZARD_TITLE))
        self.assertIsNotNone(await self._wait_for_prompt_button("Reveal in Explorer"))

        # Rebuild acknowledges that deps can be replaced and then opens the capture-repair wizard.
        rebuild_button = await self._wait_for_prompt_button("Rebuild")
        self.assertIsNotNone(rebuild_button)
        await rebuild_button.click()
        self.assertIsNotNone(await self._wait_for_visible_window(_PROJECT_WIZARD_TITLE, timeout_steps=120))

    async def test_missing_capture_with_empty_invalid_deps_opens_wizard_without_prompt(self):
        project_path = self._copy_project_without_capture_layer()
        deps_path = project_path.parent / _REMIX_DEPENDENCIES_FOLDER
        shutil.rmtree(deps_path)
        deps_path.mkdir()

        # Empty invalid deps has no user data to protect, so Stagecraft can continue to post-open repair.
        await self._open_stagecraft_project(project_path)

        # The wizard opens for capture repair without a destructive-action confirmation. The actual deps replacement
        # is owned by create_folder_symlinks() when the wizard has the RTX Remix path needed to rebuild it.
        self.assertIsNotNone(await self._wait_for_visible_window(_PROJECT_WIZARD_TITLE, timeout_steps=120))
        self.assertFalse(self._is_window_visible(_INVALID_DEPS_DIALOG_TITLE))
        self.assertTrue(deps_path.exists())

    def _copy_project_without_capture_layer(self) -> Path:
        project_root = Path(self._temp_dir.name) / "project_example"
        shutil.copytree(_get_test_data("usd/project_example"), project_root)
        project_path = project_root / "combined.usda"

        project_layer = Sdf.Layer.FindOrOpen(str(project_path))
        self.assertIsNotNone(project_layer)
        # Keep the centralized workfile metadata, but remove content sublayers from the temp copy so this E2E only
        # exercises missing-capture repair instead of loading unrelated material-heavy fixture content.
        project_layer.subLayerPaths = []
        project_layer.Save()
        return project_path

    async def _open_stagecraft_project(self, project_path: Path):
        await self._usd_context.open_stage_async(str(project_path))
        expected_path = project_path.resolve()
        for _ in range(120):
            stage = self._usd_context.get_stage()
            if stage:
                root_layer = stage.GetRootLayer()
                if root_layer and Path(root_layer.realPath).resolve() == expected_path:
                    return
            await ui_test.wait_n_updates(1)
        self.fail(f"Stagecraft did not open {expected_path}")

    async def _wait_for_capture_label(self, capture_name: str):
        for _ in range(120):
            for label in ui_test.find_all(f"{_PROJECT_WIZARD_TITLE}//Frame/**/Label[*].identifier=='item_title'"):
                if label.widget.visible and label.widget.text == capture_name:
                    return label
            await ui_test.wait_n_updates(2)
        return None

    async def _close_open_stage(self):
        if self._usd_context is not None and self._usd_context.can_close_stage():
            self._usd_context.get_selection().clear_selected_prim_paths()
            await ui_test.wait_n_updates(5)
            omni.usd.release_all_hydra_engines(self._usd_context)
            await ui_test.wait_n_updates(5)
            await self._usd_context.close_stage_async()
            await ui_test.wait_n_updates(5)

    @staticmethod
    def _capture_tree_query() -> str:
        return f"{_PROJECT_WIZARD_TITLE}//Frame/**/TreeView[*].identifier=='CaptureTree'"

    @staticmethod
    async def _wait_for_visible_window(title: str, timeout_steps: int = 80):
        for _ in range(timeout_steps):
            window = TestCaptureRepairOnOpen._find_visible_window(title)
            if window:
                return window
            await ui_test.wait_n_updates(2)
        return None

    @staticmethod
    async def _wait_for_widget(query: str, timeout_steps: int = 80):
        for _ in range(timeout_steps):
            widget = ui_test.find(query)
            if widget:
                return widget
            await ui_test.wait_n_updates(2)
        return None

    @staticmethod
    async def _wait_for_prompt_button(text: str, timeout_steps: int = 80):
        return await TestCaptureRepairOnOpen._wait_for_widget(
            f"{_INVALID_DEPS_DIALOG_TITLE}//Frame/**/Button[*].text=='{text}'", timeout_steps=timeout_steps
        )

    @staticmethod
    def _is_window_visible(title: str) -> bool:
        return bool(TestCaptureRepairOnOpen._find_visible_window(title))

    @staticmethod
    def _find_visible_window(title: str) -> ui.Window | None:
        for window in ui.Workspace.get_windows():
            if window.title == title and window.visible:
                return window
        return None

    @staticmethod
    async def _destroy_test_windows():
        for prompt in list(PromptManager._prompts):
            if prompt._title in {_INVALID_DEPS_DIALOG_TITLE, _PROJECT_WIZARD_TITLE}:
                prompt.destroy()
        for window in list(ui.Workspace.get_windows()):
            if window.title in {_INVALID_DEPS_DIALOG_TITLE, _PROJECT_WIZARD_TITLE}:
                window.visible = False
        await ui_test.wait_n_updates(5)
