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

import gc

import omni.ui as ui
import omni.usd as usd
from carb.input import KeyboardInput
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.properties_pane.widget import AssetReplacementsPane as _AssetReplacementsPane
from lightspeed.trex.utils.widget.quicklayout import load_layout
from omni.flux.custom_tags.core import CustomTagsCore as _CustomTagsCore
from omni.flux.stage_manager.core import get_instance as _get_stage_manager_core_instance
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage
from omni.kit.ui_test.query import WidgetRef
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

    async def _select_stage_manager_tab(self, display_name: str, interaction_name: str):
        core = _get_stage_manager_core_instance()
        self.assertIsNotNone(core)

        tab_selector = f"{_WindowNames.STAGE_MANAGER}//Frame/**/Label[*].name=='PropertiesWidgetLabel'"
        for _ in range(40):
            tabs = [
                tab for tab in ui_test.find_all(tab_selector) if tab.widget.visible and tab.widget.text == display_name
            ]
            if tabs:
                tab = tabs[0]
                await ui_test.emulate_mouse_move(tab.position + (tab.size / 2))
                await ui_test.emulate_mouse_click()
                break
            await ui_test.human_delay()
        else:
            self.fail(f"Stage Manager tab '{display_name}' was not visible")

        for _ in range(80):
            interaction = core.get_active_interaction()
            if interaction and interaction.name == interaction_name:
                return interaction
            await ui_test.wait_n_updates(2)
        self.fail(f"Stage Manager did not activate {interaction_name}")
        return None

    @staticmethod
    def _find_tagged_items(interaction, prim_path: str, tag_name: str):
        return interaction.tree.model.find_items(
            lambda item: (
                item.data
                and item.data.IsValid()
                and str(item.data.GetPath()) == prim_path
                and item.parent
                and item.parent.display_name == tag_name
            )
        )

    async def _wait_for_usd_selection(
        self, expected_paths: list[str], settle_frames: int = 10, timeout_frames: int = 120
    ):
        usd_context = usd.get_context()
        stable_frames = 0
        last_paths = []
        for _ in range(timeout_frames):
            last_paths = usd_context.get_selection().get_selected_prim_paths()
            if last_paths == expected_paths:
                stable_frames += 1
                if stable_frames >= settle_frames:
                    return
            else:
                stable_frames = 0
            await ui_test.wait_n_updates(1)
        self.fail(f"USD selection did not settle on {expected_paths}; got {last_paths}")

    async def _wait_for_stage_manager_model_selection(self, interaction, expected_path: str, timeout_frames: int = 120):
        last_selection = []
        for _ in range(timeout_frames):
            last_selection = [
                str(item.data.GetPath())
                for item in interaction.tree.model.selection
                if item.data and item.data.IsValid()
            ]
            if expected_path in last_selection:
                return
            await ui_test.wait_n_updates(1)
        self.fail(f"Stage Manager did not select {expected_path}; got {last_selection}")

    async def _wait_for_stage_manager_model_selection_paths(
        self, interaction, expected_paths: list[str], timeout_frames: int = 120
    ):
        last_selection = []
        for _ in range(timeout_frames):
            last_selection = [
                str(item.data.GetPath())
                for item in interaction.tree.model.selection
                if item.data and item.data.IsValid()
            ]
            if last_selection == expected_paths:
                return
            await ui_test.wait_n_updates(1)
        self.fail(f"Stage Manager selection did not settle on {expected_paths}; got {last_selection}")

    def _get_properties_pane(self):
        for obj in gc.get_objects():
            if isinstance(obj, _AssetReplacementsPane) and obj.window_visible and not obj.destroyed:
                return obj
        return None

    async def _find_visible_property_add_buttons(self, minimum_count: int):
        button_selector = "**/Label[*].identifier=='item_add_button'"
        for _ in range(120):
            properties_pane = self._get_properties_pane()
            tree_view = (
                properties_pane.selection_tree_widget._tree_view
                if properties_pane is not None and properties_pane.selection_tree_widget is not None
                else None
            )
            tree_view_ref = (
                WidgetRef(tree_view, f"{_WindowNames.PROPERTIES.value}//LiveSelectionTreeView")
                if tree_view is not None
                else None
            )
            buttons = (
                [button for button in tree_view_ref.find_all(button_selector) if button.widget.visible]
                if tree_view_ref is not None
                else []
            )
            if len(buttons) >= minimum_count:
                return buttons
            await ui_test.wait_n_updates(1)
        self.fail(f"Properties pane did not expose {minimum_count} add buttons")
        return []

    async def _click_light_creator_button(self, button_name: str):
        selector = f"Light creator//Frame/**/Button[*].name=='{button_name}'"
        for _ in range(80):
            button = ui_test.find(selector)
            if button is not None and button.widget.visible:
                await button.click()
                return
            await ui_test.wait_n_updates(1)
        self.fail(f"Light creator did not expose {button_name}")

    async def test_created_stage_light_selection_survives_stage_manager_mesh_refresh(self):
        mesh_path = "/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"
        created_light_path = "/RootNode/instances/inst_0AB745B8BEE1F16B_0/DiskLight"
        usd_context = usd.get_context()

        _LayerManagerCore().set_edit_target_layer_of_type(_LayerType.replacement)

        ui.Workspace.show_window(_WindowNames.PROPERTIES.value, True)
        ui.Workspace.show_window(_WindowNames.STAGE_MANAGER.value, True)
        properties_window = ui.Workspace.get_window(_WindowNames.PROPERTIES.value)
        self.assertIsNotNone(properties_window)
        properties_window.focus()

        interaction = await self._select_stage_manager_tab("Meshes", "RemixAllMeshesInteractionPlugin")

        usd_context.get_selection().clear_selected_prim_paths()
        await ui_test.wait_n_updates(10)
        usd_context.get_selection().set_selected_prim_paths([mesh_path], False)
        await self._wait_for_usd_selection([mesh_path])
        await self._wait_for_stage_manager_model_selection(interaction, mesh_path)

        add_buttons = await self._find_visible_property_add_buttons(2)
        await add_buttons[1].click()
        await self._click_light_creator_button("LightDisk")

        await self._wait_for_usd_selection([created_light_path], settle_frames=5)
        await ui_test.wait_n_updates(120)

        self.assertEqual([created_light_path], usd_context.get_selection().get_selected_prim_paths())

    async def test_unselect_all_with_esc_clears_stage_manager_selection(self):
        mesh_path = "/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"
        usd_context = usd.get_context()

        ui.Workspace.show_window(_WindowNames.STAGE_MANAGER.value, True)
        interaction = await self._select_stage_manager_tab("Meshes", "RemixAllMeshesInteractionPlugin")

        usd_context.get_selection().clear_selected_prim_paths()
        await ui_test.wait_n_updates(10)
        usd_context.get_selection().set_selected_prim_paths([mesh_path], False)
        await self._wait_for_usd_selection([mesh_path])
        await self._wait_for_stage_manager_model_selection(interaction, mesh_path)

        await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)

        await self._wait_for_usd_selection([], settle_frames=5)
        await self._wait_for_stage_manager_model_selection_paths(interaction, [])

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
        selection_before_property_edit = usd_context.get_selection().get_selected_prim_paths()
        self.assertTrue(selection_before_property_edit)
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

        # The material property changed, but the active selection and Stage Manager item set should remain stable.
        await self._wait_for_usd_selection(selection_before_property_edit, settle_frames=5)
        await ui_test.wait_n_updates(5)
        stage_manager_paths_after = {
            str(item.data.GetPath())
            for item in interaction.tree.model.find_items(lambda item: item.data and item.data.IsValid())
        }
        self.assertEqual(stage_manager_paths_before, stage_manager_paths_after)

    async def test_custom_tag_assignment_updates_active_stage_manager_tab(self):
        selection_prim_path = (
            "/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube"
        )
        usd_context = usd.get_context()
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath(selection_prim_path)
        self.assertTrue(prim.IsValid())

        # Create a real tag before opening the tag-grouped view, so the active tree starts without the prim assigned.
        tags_core = _CustomTagsCore()
        tag_path = tags_core.get_unique_tag_path("Codex_Refresh_Tag", existing_tag_paths=tags_core.get_all_tags())
        tag_name = tags_core.get_tag_name(tag_path)
        self.assertIsNotNone(tag_name)
        tags_core.create_tag(tag_name, use_undo_group=False)
        await ui_test.wait_n_updates(10)

        # Switch to the real Stage Manager Custom Tags tab and wait for its initial tree build.
        interaction = await self._select_stage_manager_tab("Custom Tags", "RemixAllTagsInteractionPlugin")
        for _ in range(80):
            if not self._find_tagged_items(interaction, selection_prim_path, tag_name):
                break
            await ui_test.wait_n_updates(2)
        else:
            self.fail(f"{selection_prim_path} already had tag {tag_name}")

        # Assign the tag through the same USD collection command path used by the tag editing UI.
        tags_core.add_tag_to_prim(selection_prim_path, tag_path)

        # The active Custom Tags tab must rebuild its context items, not only dirty existing widgets.
        for _ in range(120):
            if self._find_tagged_items(interaction, selection_prim_path, tag_name):
                break
            await ui_test.wait_n_updates(2)
        else:
            self.fail(f"Stage Manager did not refresh {tag_name} membership for {selection_prim_path}")
