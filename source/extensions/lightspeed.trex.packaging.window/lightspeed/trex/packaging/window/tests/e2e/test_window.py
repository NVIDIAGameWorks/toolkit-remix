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

import omni.kit.app
import omni.ui as ui
import omni.usd
from lightspeed.trex.packaging.window.window import PackagingErrorWindow
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows
from pxr import Sdf


class TestPackagingErrorWindowE2E(AsyncTestCase):
    _ERROR_WINDOW_TITLE = "Mod Packaging Errors"
    _INCOMPLETE_DIALOG_TITLE = "Packaging Repair Incomplete"

    async def setUp(self):
        await arrange_windows()
        self._window = None
        self._actions_applied = []
        await self._close_context()

    async def tearDown(self):
        if self._window:
            self._window.destroy()
            self._window = None
        await self._close_context()
        await self._destroy_prompt_windows()

    async def test_retry_with_failed_repairs_should_show_incomplete_dialog_and_keep_error_window_open(self):
        # Open a temporary copy of the centralized packaging project fixture.
        async with open_test_project("packaging/projects/MainProject/main_project.usda") as project_url:
            project_root = Path(project_url.path).parent
            mod_layer_path = project_root / "mod.usda"
            broken_refs_layer_path = project_root / "broken_refs" / "broken_refs_textures.usda"
            self._link_broken_refs_layer(mod_layer_path, "broken_refs/broken_refs_textures.usda")
            await self._reopen_project(project_url.path)

            # Open the real packaging error window against a texture-property repair that cannot be removed.
            missing_texture_path = (broken_refs_layer_path.parent / "missing_texture.dds").as_posix()
            missing_texture_attr = (
                "/RootNode/PackagingTest/missing_texture_property/Looks/Mat/Shader.inputs:diffuse_texture"
            )
            self._window = PackagingErrorWindow(
                [(broken_refs_layer_path.as_posix(), missing_texture_attr, missing_texture_path)],
            )
            actions_applied_sub = self._window.subscribe_actions_applied(self._actions_applied.append)

            # Drive the real UI: choose Remove All, then Retry Packaging.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Remove All")
            await self._click_button(self._ERROR_WINDOW_TITLE, "Retry Packaging")

            # The failed repair must surface through the real dialog and must not emit the retry event.
            incomplete_dialog_button = await self._wait_for_visible_widget(
                f"{self._INCOMPLETE_DIALOG_TITLE}//Frame/**/Button[*].text=='Okay'"
            )
            self.assertIsNotNone(incomplete_dialog_button)
            self.assertEqual([], self._actions_applied)
            self.assertTrue(self._is_window_visible(self._ERROR_WINDOW_TITLE))
            self.assertTrue(self._is_window_visible(self._INCOMPLETE_DIALOG_TITLE))
            self.assertIsNotNone(actions_applied_sub)
            self._window.destroy()
            self._window = None

    async def _click_button(self, window_title: str, button_text: str):
        button = await self._wait_for_visible_widget(f"{window_title}//Frame/**/Button[*].text=='{button_text}'")
        self.assertIsNotNone(button)
        await button.click()
        await omni.kit.app.get_app().next_update_async()

    async def _wait_for_visible_widget(self, selector: str, max_frames: int = 240):
        for _ in range(max_frames):
            widget = self._find_visible_widget(selector)
            if widget is not None:
                return widget
            await omni.kit.app.get_app().next_update_async()
        return None

    def _find_visible_widget(self, selector: str):
        for widget in ui_test.find_all(selector) or []:
            if self._is_visible_widget(widget):
                return widget
        widget = ui_test.find(selector)
        if widget is not None and self._is_visible_widget(widget):
            return widget
        return None

    @staticmethod
    def _is_visible_widget(widget_ref) -> bool:
        widget = widget_ref.widget
        if widget is not None and not widget.visible:
            return False
        window = widget_ref.window
        return window is None or window.visible

    @staticmethod
    def _is_window_visible(title: str) -> bool:
        return any(window.title == title and window.visible for window in ui.Workspace.get_windows())

    @staticmethod
    def _link_broken_refs_layer(mod_layer_path: Path, broken_refs_layer_name: str):
        mod_layer = Sdf.Layer.FindOrOpen(str(mod_layer_path))
        if not mod_layer:
            raise RuntimeError(f"Unable to open fixture mod layer: {mod_layer_path}")
        broken_refs_sublayer = f"./{broken_refs_layer_name}"
        if broken_refs_sublayer not in mod_layer.subLayerPaths:
            mod_layer.subLayerPaths.append(broken_refs_sublayer)
            mod_layer.Save()

    async def _destroy_prompt_windows(self):
        for window in list(ui.Workspace.get_windows()):
            if window.title in {self._ERROR_WINDOW_TITLE, self._INCOMPLETE_DIALOG_TITLE, "Applying Packaging Repairs"}:
                window.visible = False
        await omni.kit.app.get_app().next_update_async()

    async def _reopen_project(self, project_path: str):
        await self._close_context()
        success, _ = await omni.usd.get_context().open_stage_async(project_path)
        self.assertTrue(success)

    async def _close_context(self):
        context = omni.usd.get_context()
        if context and context.get_stage():
            await context.close_stage_async()
