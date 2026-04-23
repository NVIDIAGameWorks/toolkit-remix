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

from unittest.mock import patch

import omni.ui as ui
import omni.usd as usd
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.properties_pane.widget import AssetReplacementsPane as _AssetReplacementsPane
from lightspeed.trex.utils.widget.quicklayout import load_layout
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage
from omni.kit.ui_test import Vec2


class TestStageManagerPropertiesInteraction(AsyncTestCase):
    async def test_material_properties_update_stage_manager_should_not_refresh(self):
        selection_prim_path = (
            "/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube"
        )
        editor_prim_path = (
            "/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube_01"
        )
        editor_prim_label = "Cube_01"
        project_path = _get_test_data("usd/project_example/combined.usda")

        usd_context = usd.get_context()
        if usd_context.can_close_stage():
            await usd_context.close_stage_async()

        await open_stage(project_path)
        load_layout(_get_quicklayout_config(_LayoutFiles.WORKSPACE_PAGE))
        await ui_test.human_delay(10)

        ui.Workspace.show_window(_WindowNames.PROPERTIES.value, True)
        properties_window = ui.Workspace.get_window(_WindowNames.PROPERTIES.value)
        self.assertIsNotNone(properties_window)
        if hasattr(properties_window, "focus"):
            properties_window.focus()

        usd_context.get_selection().clear_selected_prim_paths()
        await ui_test.wait_n_updates(10)
        usd_context.get_selection().set_selected_prim_paths([selection_prim_path], False)
        await ui_test.wait_n_updates(20)
        await ui_test.human_delay(human_delay_speed=5)

        checkbox_selector = (
            f"{_WindowNames.PROPERTIES.value}//Frame/**/CheckBox[*].identifier=='{editor_prim_path}.doubleSided'"
        )
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

        with patch.object(_AssetReplacementsPane, "refresh") as mock:
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

            self.assertEqual(0, mock.call_count)
