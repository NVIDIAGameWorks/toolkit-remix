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

from __future__ import annotations

import omni.ui as ui
import omni.usd as usd
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.utils.widget.quicklayout import load_layout
from omni.flux.stage_manager.core import get_instance as _get_stage_manager_core_instance
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage
from omni.kit.ui_test import Vec2


class TestStageManagerPropertiesInteraction(AsyncTestCase):
    async def setUp(self):
        # Open the full Stage Craft workspace so the test exercises the real Stage Manager and Properties panes.
        await open_stage(_get_test_data("usd/project_example/combined.usda"))
        load_layout(_get_quicklayout_config(_LayoutFiles.WORKSPACE_PAGE))
        await ui_test.human_delay(10)

        stage_manager_window = ui.Workspace.get_window(_WindowNames.STAGE_MANAGER)
        self.assertIsNotNone(stage_manager_window)
        self.assertTrue(stage_manager_window.visible)
        await ui_test.human_delay(20)

    async def tearDown(self):
        for window_name in (_WindowNames.STAGE_MANAGER, _WindowNames.PROPERTIES.value):
            window = ui.Workspace.get_window(window_name)
            if window:
                window.visible = False
        await ui_test.human_delay(2)

        usd_context = usd.get_context()
        if usd_context.can_close_stage():
            await usd_context.close_stage_async()
            await ui_test.human_delay(2)

    async def test_material_properties_update_stage_manager_should_not_refresh(self):
        selection_prim_path = (
            "/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube"
        )
        editor_prim_path = (
            "/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube_01"
        )
        editor_prim_label = "Cube_01"
        usd_context = usd.get_context()

        # Bring up the Properties pane, then select the same instance a user would select in the stage.
        ui.Workspace.show_window(_WindowNames.PROPERTIES.value, True)
        properties_window = ui.Workspace.get_window(_WindowNames.PROPERTIES.value)
        self.assertIsNotNone(properties_window)
        properties_window.focus()

        usd_context.get_selection().clear_selected_prim_paths()
        await ui_test.wait_n_updates(10)
        usd_context.get_selection().set_selected_prim_paths([selection_prim_path], False)
        await ui_test.wait_n_updates(20)
        await ui_test.human_delay(human_delay_speed=5)

        checkbox_selector = (
            f"{_WindowNames.PROPERTIES.value}//Frame/**/CheckBox[*].identifier=='{editor_prim_path}.doubleSided'"
        )
        # Walk the visible Properties tree until the target mesh editor is open and its material checkbox is exposed.
        for _ in range(80):
            visible_checkboxes = [widget for widget in ui_test.find_all(checkbox_selector) if widget.widget.visible]
            if visible_checkboxes:
                break

            item_prims = [
                widget
                for widget in ui_test.find_all(
                    f"{_WindowNames.PROPERTIES.value}//Frame/**/Label[*].identifier=='item_prim'"
                )
                if widget.widget.visible
            ]
            if len(item_prims) >= 2:
                self.assertEqual(editor_prim_label, item_prims[-1].widget.text)
                await item_prims[-1].click()
                await ui_test.human_delay(human_delay_speed=5)
            else:
                expand_buttons = [
                    widget
                    for widget in ui_test.find_all(
                        f"{_WindowNames.PROPERTIES.value}//Frame/**/Image[*].identifier=='Expand'"
                    )
                    if widget.widget.visible
                ]
                if expand_buttons:
                    await expand_buttons[0].click()
                    await ui_test.human_delay(human_delay_speed=5)
            await ui_test.human_delay(human_delay_speed=5)
        else:
            self.fail(f"Properties pane did not expose {editor_prim_path}.doubleSided")

        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath(editor_prim_path)
        original_value = prim.GetAttribute("doubleSided").Get()
        core = _get_stage_manager_core_instance()
        self.assertIsNotNone(core)
        interaction = core.get_active_interaction()
        self.assertIsNotNone(interaction)
        stage_manager_paths_before = {
            str(item.data.GetPath())
            for item in interaction.tree.model.find_items(lambda item: item.data and item.data.IsValid())
        }

        # Click the real checkbox. This authors USD through the Properties UI and should not rebuild Stage Manager.
        visible_checkboxes = [widget for widget in ui_test.find_all(checkbox_selector) if widget.widget.visible]
        self.assertTrue(visible_checkboxes)
        checkbox = visible_checkboxes[0]

        await ui_test.emulate_mouse_move(checkbox.position + Vec2(3, 3))
        await ui_test.human_delay()
        await ui_test.emulate_mouse_click()
        await ui_test.human_delay()

        for _ in range(40):
            if prim.GetAttribute("doubleSided").Get() != original_value:
                break
            await ui_test.wait_n_updates(2)
        else:
            self.fail("Properties pane checkbox did not change the USD value")

        # The material property changed, but the Stage Manager item set should remain stable.
        await ui_test.wait_n_updates(5)
        stage_manager_paths_after = {
            str(item.data.GetPath())
            for item in interaction.tree.model.find_items(lambda item: item.data and item.data.IsValid())
        }
        self.assertEqual(stage_manager_paths_before, stage_manager_paths_after)
