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

import omni.ui as ui
import omni.usd
from carb.input import KeyboardInput
from lightspeed.common.constants import LayoutFiles as _LayoutFiles, WindowNames as _WindowNames
from lightspeed.trex.contexts.extension import get_instance as get_context_manager
from lightspeed.trex.contexts.setup import Contexts
from lightspeed.trex.utils.widget.quicklayout import load_layout as _load_layout
from lightspeed.trex.viewports.shared.widget import get_instance as _get_viewport_instance
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage
from omni.kit.ui_test.query import WidgetRef
from pxr import Sdf, Usd, UsdGeom


class TestHotkeys(AsyncTestCase):
    async def setUp(self):
        trex_context_manager = get_context_manager()
        trex_context_manager.set_current_context(Contexts.TEXTURE_CRAFT)
        await open_stage(_get_test_data("usd/project_example/combined.usda"))

    async def test_unselect_all_with_esc(self):
        # Setup
        usd_context = omni.usd.get_context()

        # Select an object and ensure it is selected
        expected_value = ["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"]
        usd_context.get_selection().set_selected_prim_paths(expected_value, False)
        self.assertListEqual(usd_context.get_selection().get_selected_prim_paths(), expected_value)

        # Use the ESC hotkey to unselect everything
        await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
        await ui_test.human_delay(human_delay_speed=10)

        # Ensure that nothing is selected
        self.assertListEqual(usd_context.get_selection().get_selected_prim_paths(), [])

    async def test_delete_key_with_focused_viewport_removes_selected_replacement_prim(self):
        """Delete the selected replacement prim through the focused Remix viewport."""
        trex_context_manager = get_context_manager()
        original_context = trex_context_manager.get_current_context()
        replacement_prim_path = "/RootNode/meshes/test_viewport_delete_hotkey"

        trex_context_manager.set_current_context(Contexts.STAGE_CRAFT)
        usd_context = omni.usd.get_context(Contexts.STAGE_CRAFT.value)
        stage = usd_context.get_stage()
        original_edit_target = stage.GetEditTarget()
        replacement_layer = None
        viewport_window = None
        viewport_was_visible = None

        try:
            viewport = _get_viewport_instance(Contexts.STAGE_CRAFT.value)
            self.assertIsNotNone(viewport)
            viewport_path = f"{_WindowNames.VIEWPORT.value}//Frame"
            viewport_window = next(
                (
                    window
                    for window in ui.Workspace.get_windows()
                    if window.title == _WindowNames.VIEWPORT.value
                    and WidgetRef(viewport.viewport_frame(), viewport_path, window=window).realpath is not None
                ),
                None,
            )
            self.assertIsNotNone(viewport_window)
            viewport_was_visible = viewport_window.visible

            # A user opens Stage Craft and works in its existing viewport rather than an isolated test viewport.
            _load_layout(_get_quicklayout_config(_LayoutFiles.WORKSPACE_PAGE))
            replacement_layer = Sdf.Layer.FindRelativeToLayer(stage.GetRootLayer(), "./replacements.usda")
            self.assertIsNotNone(replacement_layer)
            stage.SetEditTarget(Usd.EditTarget(replacement_layer))
            replacement_prim = UsdGeom.Xform.Define(stage, replacement_prim_path).GetPrim()
            self.assertTrue(replacement_prim.IsValid())

            usd_context.get_selection().set_selected_prim_paths([replacement_prim_path], False)
            self.assertListEqual(usd_context.get_selection().get_selected_prim_paths(), [replacement_prim_path])

            viewport_window.visible = True
            viewport_root_ref = WidgetRef(viewport.viewport_frame(), viewport_path, window=viewport_window)
            for _ in range(60):
                viewports = [
                    viewport_ref
                    for viewport_ref in viewport_root_ref.find_all("**/.identifier == 'viewport'")
                    if viewport_ref.widget.visible
                ]
                if viewport_window.visible and viewports:
                    viewport_ref = viewports[0]
                    break
                await ui_test.wait_n_updates(1)
            else:
                self.fail("The Stage Craft viewport was not visible")

            # Focus the app-owned viewport so Delete travels through its delegate and the global Stage Manager event.
            await viewport_ref.click()
            await ui_test.wait_n_updates(1)
            await ui_test.human_delay(human_delay_speed=10)
            # The focus click can clear selection when it lands on empty viewport space; restoring it does not move focus.
            usd_context.get_selection().set_selected_prim_paths([replacement_prim_path], False)
            self.assertListEqual(
                usd_context.get_selection().get_selected_prim_paths(),
                [replacement_prim_path],
            )
            await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
            await ui_test.human_delay(human_delay_speed=10)

            for _ in range(60):
                if not stage.GetPrimAtPath(replacement_prim_path).IsValid():
                    break
                await ui_test.wait_n_updates(1)
            self.assertFalse(stage.GetPrimAtPath(replacement_prim_path).IsValid())
        finally:
            usd_context.get_selection().clear_selected_prim_paths()
            if replacement_layer is not None:
                stage.SetEditTarget(Usd.EditTarget(replacement_layer))
                if stage.GetPrimAtPath(replacement_prim_path).IsValid():
                    stage.RemovePrim(replacement_prim_path)
            stage.SetEditTarget(original_edit_target)
            trex_context_manager.set_current_context(original_context)
            if viewport_window is not None:
                viewport_window.visible = viewport_was_visible
