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
from unittest.mock import patch

import omni.kit.commands
import omni.ui as ui
import omni.usd as usd
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardInput
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.contexts import get_instance as _get_context_manager
from lightspeed.trex.contexts.setup import Contexts
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
from pxr import Sdf, Usd


_MESH_TAB_SELECTION_PATHS = {
    "/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh",
    "/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube",
    "/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube_01",
    "/RootNode/instances/inst_BAC90CAA733B0859_1/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube",
    "/RootNode/instances/inst_BAC90CAA733B0859_1/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube_01",
    "/RootNode/instances/inst_BAC90CAA733B0859_2/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube",
    "/RootNode/instances/inst_BAC90CAA733B0859_2/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube_01",
    "/RootNode/instances/inst_CED45075A077A49A_0/mesh",
    "/RootNode/instances/inst_FEE1DEADF00D0001_0/mesh",
    "/RootNode/instances/inst_FEE1DEADF00D0001_0/reference_override/Cube_01",
    "/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh",
    "/RootNode/meshes/mesh_BAC90CAA733B0859",
    "/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube",
    "/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube_01",
    "/RootNode/meshes/mesh_CED45075A077A49A/mesh",
    "/RootNode/meshes/mesh_FEE1DEADF00D0001/mesh",
    "/RootNode/meshes/mesh_FEE1DEADF00D0001/reference_override/Cube_01",
}
_LIGHT_PRIM_PATHS = {
    "/RootNode/lights/light_0FBF0D906770A019",
    "/RootNode/lights/light_9907D0B07D040077",
    "/RootNode/lights/light_EDF9B59568FD1142",
    "/RootNode/instances/inst_CED45075A077A49A_0/ref_e58b2a90258740278bd55cd166bf7ba3/Klab_A/PrimaryLights/TankA",
    "/RootNode/instances/inst_CED45075A077A49A_0/ref_e58b2a90258740278bd55cd166bf7ba3/Klab_A/PrimaryLights/TankB",
    "/RootNode/instances/inst_FEE1DEADF00D0001_0/TransferWorkflowLight",
    "/RootNode/meshes/mesh_CED45075A077A49A/ref_e58b2a90258740278bd55cd166bf7ba3/Klab_A/PrimaryLights/TankA",
    "/RootNode/meshes/mesh_CED45075A077A49A/ref_e58b2a90258740278bd55cd166bf7ba3/Klab_A/PrimaryLights/TankB",
    "/RootNode/meshes/mesh_FEE1DEADF00D0001/TransferWorkflowLight",
}
_LIGHT_FILTER_SELECTION_PATHS = _LIGHT_PRIM_PATHS | {
    "/RootNode/instances",
    "/RootNode/instances/inst_CED45075A077A49A_0",
    "/RootNode/instances/inst_CED45075A077A49A_0/ref_e58b2a90258740278bd55cd166bf7ba3",
    "/RootNode/instances/inst_CED45075A077A49A_0/ref_e58b2a90258740278bd55cd166bf7ba3/Klab_A",
    "/RootNode/instances/inst_CED45075A077A49A_0/ref_e58b2a90258740278bd55cd166bf7ba3/Klab_A/PrimaryLights",
    "/RootNode/instances/inst_FEE1DEADF00D0001_0",
    "/RootNode/lights",
    "/RootNode/meshes",
    "/RootNode/meshes/mesh_CED45075A077A49A",
    "/RootNode/meshes/mesh_CED45075A077A49A/ref_e58b2a90258740278bd55cd166bf7ba3",
    "/RootNode/meshes/mesh_CED45075A077A49A/ref_e58b2a90258740278bd55cd166bf7ba3/Klab_A",
    "/RootNode/meshes/mesh_CED45075A077A49A/ref_e58b2a90258740278bd55cd166bf7ba3/Klab_A/PrimaryLights",
    "/RootNode/meshes/mesh_FEE1DEADF00D0001",
}
_TARGET_MESH_PATH = "/RootNode/meshes/mesh_FEE1DEADF00D0001/mesh"
_TARGET_MESH_INSTANCE_PATH = "/RootNode/instances/inst_FEE1DEADF00D0001_0/mesh"


class TestStageManagerPropertiesInteraction(AsyncTestCase):
    async def setUp(self):
        # Open the full Stage Craft workspace so the test exercises the real Stage Manager and Properties panes.
        context_manager = _get_context_manager()
        previous_context = context_manager.get_current_context()
        self.addCleanup(context_manager.set_current_context, previous_context)
        context_manager.set_current_context(Contexts.STAGE_CRAFT)
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

    async def _click_stage_manager_tab(self, display_name: str):
        tab_selector = f"{_WindowNames.STAGE_MANAGER}//Frame/**/Label[*].name=='PropertiesWidgetLabel'"
        for _ in range(40):
            tabs = [
                tab for tab in ui_test.find_all(tab_selector) if tab.widget.visible and tab.widget.text == display_name
            ]
            if tabs:
                tab = tabs[0]
                await ui_test.emulate_mouse_move(tab.position + (tab.size / 2))
                await ui_test.emulate_mouse_click()
                await ui_test.human_delay()
                return
            await ui_test.human_delay()
        self.fail(f"Stage Manager tab '{display_name}' was not visible")

    async def _select_stage_manager_tab(self, display_name: str, interaction_name: str):
        await self._click_stage_manager_tab(display_name)
        core = _get_stage_manager_core_instance()
        self.assertIsNotNone(core)

        for _ in range(80):
            interaction = core.get_active_interaction()
            if interaction and interaction.name == interaction_name:
                return interaction
            await ui_test.wait_n_updates(2)
        self.fail(f"Stage Manager did not activate {interaction_name}")
        return None

    async def _press_ctrl_a_outside_stage_manager(self):
        """Move from the Stage Manager tree to Properties before pressing Ctrl+A."""
        frame_selector = f"{_WindowNames.STAGE_MANAGER}//Frame/**/ScrollingFrame[*].name=='TreePanelBackground'"
        frames = [frame for frame in ui_test.find_all(frame_selector) if frame.widget.visible]
        self.assertTrue(frames)
        await frames[-1].click()
        await ui_test.human_delay()
        properties_window = ui.Workspace.get_window(_WindowNames.PROPERTIES.value)
        self.assertIsNotNone(properties_window)
        self.assertTrue(properties_window.visible)
        await ui_test.emulate_mouse_move(
            Vec2(
                properties_window.position_x + properties_window.width / 2,
                properties_window.position_y + properties_window.height / 2,
            )
        )
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay()

    @staticmethod
    def _find_tagged_items(interaction, prim_path: str, tag_name: str):
        def matches_tag(item):
            original_item = item.original_tree_item
            parent_item = item.parent.original_tree_item if item.parent else None
            return (
                original_item.data
                and original_item.data.IsValid()
                and str(original_item.data.GetPath()) == prim_path
                and parent_item
                and parent_item.display_name == tag_name
            )

        return interaction.tree.model.find_items(matches_tag)

    async def _set_stage_manager_search(self, value: str):
        """Enter a Stage Manager search value.

        Args:
            value: Search value to enter.
        """
        search_selector = f"{_WindowNames.STAGE_MANAGER}//Frame/**/StringField[*].identifier=='search_field'"
        for _ in range(80):
            search_fields = [field for field in ui_test.find_all(search_selector) if field.widget.visible]
            if search_fields:
                break
            await ui_test.wait_n_updates(1)
        else:
            self.fail("Stage Manager search field was not visible")

        search_field = search_fields[0]
        if value:
            await search_field.input(
                value,
                human_delay_speed=0,
                end_key=KeyboardInput.ENTER,
                clear_before_input=True,
            )
        else:
            await search_field.click()
            await ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.emulate_keyboard_press(KeyboardInput.BACKSPACE)
            await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
        search_field.widget.model.end_edit()
        await ui_test.human_delay()

    async def _set_stage_manager_light_filter(self, interaction, active: bool):
        """Set the Light Prims filter through the Additional Filters popup.

        Args:
            interaction: Active Stage Manager interaction plugin.
            active: Whether the Light Prims filter should be enabled.
        """
        light_filter = next(
            filter_ for filter_ in interaction.additional_filters if filter_.name == "LightPrimsFilterPlugin"
        )
        icon_selector = f"{_WindowNames.STAGE_MANAGER}//Frame/**/Image[*]"
        for _ in range(120):
            icons = [
                icon
                for icon in ui_test.find_all(icon_selector)
                if icon.widget.visible and icon.widget.tooltip == "Additional Filters"
            ]
            if icons:
                await icons[-1].click()
                break
            await ui_test.wait_n_updates(1)
        else:
            self.fail("Additional Filters button was not visible")

        for _ in range(120):
            if light_filter._checkbox and light_filter._checkbox.visible:
                break
            await ui_test.wait_n_updates(1)
        else:
            self.fail("Light Prims filter checkbox was not visible")

        if light_filter.filter_active != active:
            checkbox_position = Vec2(
                light_filter._checkbox.screen_position_x + 1,
                light_filter._checkbox.screen_position_y + 1,
            )
            await ui_test.emulate_mouse_move(checkbox_position)
            await ui_test.emulate_mouse_click()
        for _ in range(120):
            if light_filter.filter_active == active:
                await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
                await ui_test.wait_n_updates(2)
                return
            await ui_test.wait_n_updates(1)
        self.fail(f"Light Prims filter did not become {'active' if active else 'inactive'}")

    async def _input_stage_manager_search(self, value: str, target_path: str, expected_visible: bool = True):
        """Enter a search and wait for its observable result."""
        await self._set_stage_manager_search(value)

        row_selector = f"{_WindowNames.STAGE_MANAGER}//Frame/**/Label[*].identifier=='nickname_field'"
        frame_selector = f"{_WindowNames.STAGE_MANAGER}//Frame/**/ScrollingFrame[*].name=='TreePanelBackground'"
        overview_selector = f"{_WindowNames.STAGE_MANAGER}//Frame/**/Label[*]"
        for _ in range(120):
            if not expected_visible:
                overview_labels = [label for label in ui_test.find_all(overview_selector) if label.widget.visible]
                if any(label.widget.text == "0 prim available" for label in overview_labels):
                    return None
                await ui_test.human_delay()
                continue

            rows = [
                row
                for row in ui_test.find_all(row_selector)
                if row.widget.visible and row.widget.tooltip == target_path
            ]
            frames = [frame for frame in ui_test.find_all(frame_selector) if frame.widget.visible]
            for row in rows:
                row_center = row.position + (row.size / 2)
                if any(
                    frame.position.x <= row_center.x <= frame.position.x + frame.size.x
                    and frame.position.y <= row_center.y <= frame.position.y + frame.size.y
                    for frame in frames
                ):
                    return row
            await ui_test.human_delay()
        expected_result = "frame" if expected_visible else "show zero prims"
        raise AssertionError(f"Stage Manager did not {expected_result} for {target_path}")

    async def _wait_for_usd_selection(
        self, expected_paths: list[str] | set[str], settle_frames: int = 10, timeout_frames: int = 120
    ):
        """Wait for the USD selection to contain the expected paths.

        Args:
            expected_paths: USD prim paths expected in the selection.
            settle_frames: Consecutive matching frames required before returning.
            timeout_frames: Maximum frames to wait.
        """
        expected_paths = set(expected_paths)
        usd_context = usd.get_context()
        stable_frames = 0
        last_paths = []
        for _ in range(timeout_frames):
            last_paths = usd_context.get_selection().get_selected_prim_paths()
            if set(last_paths) == expected_paths:
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
            last_selection = []
            for item in interaction.tree.model.selection:
                original_item = item.original_tree_item
                if original_item.data and original_item.data.IsValid():
                    last_selection.append(str(original_item.data.GetPath()))
            if expected_path in last_selection:
                return
            await ui_test.wait_n_updates(1)
        self.fail(f"Stage Manager did not select {expected_path}; got {last_selection}")

    async def _wait_for_stage_manager_model_selection_paths(
        self, interaction, expected_paths: list[str], settle_frames: int = 1, timeout_frames: int = 120
    ):
        """Wait until the Stage Manager model selection remains at the expected paths.

        Args:
            interaction: Active Stage Manager interaction to inspect.
            expected_paths: Ordered prim paths expected in the model selection.
            settle_frames: Consecutive matching frames required before returning.
            timeout_frames: Maximum frames to wait before failing.
        """
        stable_frames = 0
        last_selection = []
        for _ in range(timeout_frames):
            last_selection = []
            for item in interaction.tree.model.selection:
                original_item = item.original_tree_item
                if original_item.data and original_item.data.IsValid():
                    last_selection.append(str(original_item.data.GetPath()))
            if last_selection == expected_paths:
                stable_frames += 1
                if stable_frames >= settle_frames:
                    return
            else:
                stable_frames = 0
            await ui_test.wait_n_updates(1)
        self.fail(f"Stage Manager selection did not settle on {expected_paths}; got {last_selection}")

    async def _find_focus_action_icon(self, prim_path: str):
        """Find the enabled Focus action icon aligned with a prim row.

        Args:
            prim_path: USD path identifying the Stage Manager row.

        Returns:
            The Focus action icon for the requested row.
        """
        row_selector = f"{_WindowNames.STAGE_MANAGER}//Frame/**/Label[*].identifier=='nickname_field'"
        focus_selector = f"{_WindowNames.STAGE_MANAGER}//Frame/**/Image[*].identifier=='focus_in_viewport_widget_image'"
        for _ in range(120):
            rows = [
                row for row in ui_test.find_all(row_selector) if row.widget.visible and row.widget.tooltip == prim_path
            ]
            focus_icons = [
                icon for icon in ui_test.find_all(focus_selector) if icon.widget.visible and icon.widget.enabled
            ]
            if rows:
                row_center_y = rows[0].position.y + (rows[0].size.y / 2)
                aligned_icons = [
                    icon for icon in focus_icons if icon.position.y <= row_center_y <= icon.position.y + icon.size.y
                ]
                if aligned_icons:
                    return min(
                        aligned_icons,
                        key=lambda icon: abs((icon.position.y + (icon.size.y / 2)) - row_center_y),
                    )
            await ui_test.human_delay()
        self.fail(f"Stage Manager did not expose an enabled Focus icon for {prim_path}")
        return None

    async def _wait_for_stage_manager_selectable_paths(self, interaction, expected_paths, timeout_frames: int = 120):
        """Wait for the Stage Manager model to expose exactly the expected selectable paths.

        Args:
            interaction: Active Stage Manager interaction plugin.
            expected_paths: Prim paths expected from the model's selectable iterator.
            timeout_frames: Maximum frames to wait.
        """
        expected_paths = set(expected_paths)
        last_paths = []
        for _ in range(timeout_frames):
            last_paths = [item.original_tree_item.path for item in interaction.tree.model.iter_selectable_items()]
            if set(last_paths) == expected_paths:
                return
            await ui_test.wait_n_updates(1)
        self.fail(f"Stage Manager selectable paths did not settle on {expected_paths}; got {last_paths}")

    async def _wait_for_stage_manager_selectable_path(self, interaction, expected_path: str, timeout_frames: int = 120):
        """Wait for the Stage Manager model to expose a selectable path.

        Args:
            interaction: Active Stage Manager interaction plugin.
            expected_path: Prim path expected from the model's selectable iterator.
            timeout_frames: Maximum frames to wait.
        """
        last_paths = []
        for _ in range(timeout_frames):
            last_paths = [item.original_tree_item.path for item in interaction.tree.model.iter_selectable_items()]
            if expected_path in last_paths:
                return
            await ui_test.wait_n_updates(1)
        self.fail(f"Stage Manager selectable paths did not include {expected_path}; got {last_paths}")

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

    async def test_related_tabs_frame_without_highlighting_related_prims(self):
        """Keep exact USD selection without highlighting related rows across related tabs."""
        parent_path = "/RootNode/meshes/mesh_0AB745B8BEE1F16B"
        related_mesh_path = "/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"
        related_material_path = "/RootNode/Looks/mat_BC868CE5A075ABB1"
        related_tabs = (
            ("Meshes", "RemixAllMeshesInteractionPlugin", related_mesh_path),
            ("Materials", "RemixAllMaterialsInteractionPlugin", related_material_path),
            ("Categories", "RemixAllCategoriesInteractionPlugin", related_mesh_path),
        )
        usd_context = usd.get_context()
        stage = usd_context.get_stage()
        related_mesh = stage.GetPrimAtPath(related_mesh_path)
        self.assertTrue(related_mesh.IsValid())

        with Usd.EditContext(stage, stage.GetSessionLayer()):
            omni.kit.commands.execute(
                "CreateUsdAttribute",
                prim=related_mesh,
                attr_name="remix_category:world_ui",
                attr_value=True,
                attr_type=Sdf.ValueTypeNames.Bool,
            )

        prims_interaction = await self._select_stage_manager_tab("Prims", "RemixAllPrimsInteractionPlugin")
        usd_context.get_selection().clear_selected_prim_paths()
        await ui_test.human_delay()
        usd_context.get_selection().set_selected_prim_paths([parent_path], False)
        await self._wait_for_usd_selection([parent_path])
        await self._wait_for_stage_manager_model_selection(prims_interaction, parent_path)

        for display_name, interaction_name, related_path in related_tabs:
            # Switching views must preserve the user's exact USD selection without highlighting its relations.
            interaction = await self._select_stage_manager_tab(display_name, interaction_name)
            self.assertEqual([parent_path], usd_context.get_selection().get_selected_prim_paths())

            # Tab activation can precede tree publication, so wait for the known related row before checking selection.
            for _ in range(120):
                related_items = interaction.tree.model.find_items(
                    lambda item, expected_path=related_path: (
                        item.original_tree_item.data is not None and str(item.original_tree_item.path) == expected_path
                    )
                )
                if related_items:
                    break
                await ui_test.wait_n_updates(1)
            else:
                self.fail(f"{display_name} did not publish a related data-backed item")

            self.assertEqual([parent_path], usd_context.get_selection().get_selected_prim_paths())
            await self._wait_for_stage_manager_model_selection_paths(interaction, [], settle_frames=5)
            self.assertEqual([parent_path], usd_context.get_selection().get_selected_prim_paths())
            self.assertTrue(related_items)

    async def test_focus_action_with_multiple_selected_prims_preserves_stage_manager_and_usd_selection(self):
        """Verify a selected row action preserves Stage Manager and USD multiselection."""
        selected_paths = [
            "/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh",
            "/RootNode/meshes/mesh_CED45075A077A49A/mesh",
        ]
        usd_context = usd.get_context()

        def get_stage_manager_selection_paths():
            """Return selected Stage Manager prim paths in model order."""
            return [
                str(item.original_tree_item.data.GetPath())
                for item in interaction.tree.model.selection
                if item.original_tree_item.data and item.original_tree_item.data.IsValid()
            ]

        interaction = await self._select_stage_manager_tab("Meshes", "RemixAllMeshesInteractionPlugin")
        usd_context.get_selection().clear_selected_prim_paths()
        await ui_test.human_delay()
        usd_context.get_selection().set_selected_prim_paths(selected_paths, False)
        await self._wait_for_usd_selection(selected_paths)

        for _ in range(120):
            stage_manager_selection_before_focus = get_stage_manager_selection_paths()
            if len(stage_manager_selection_before_focus) == len(selected_paths) and set(
                stage_manager_selection_before_focus
            ) == set(selected_paths):
                break
            await ui_test.wait_n_updates(1)
        else:
            self.fail(
                f"Stage Manager selection did not settle on {selected_paths}; "
                f"got {stage_manager_selection_before_focus}"
            )

        usd_selection_before_focus = list(usd_context.get_selection().get_selected_prim_paths())

        # Use the first selected mesh row and its aligned Focus action icon.
        focus_icon = await self._find_focus_action_icon(selected_paths[0])

        # Focus requests framing without changing either selection model.
        with patch(
            "lightspeed.trex.stage_manager.plugin.widget.usd.focus_in_viewport._frame_paths_in_viewport"
        ) as mock_frame_paths_in_viewport:
            await focus_icon.click()
            await ui_test.human_delay()

        mock_frame_paths_in_viewport.assert_called_once()
        await self._wait_for_usd_selection(usd_selection_before_focus)
        await self._wait_for_stage_manager_model_selection_paths(interaction, stage_manager_selection_before_focus)
        self.assertEqual(usd_selection_before_focus, usd_context.get_selection().get_selected_prim_paths())
        self.assertEqual(stage_manager_selection_before_focus, get_stage_manager_selection_paths())

    async def test_focus_action_on_unselected_prim_selects_row_before_release(self):
        """Verify an unselected row action selects its row before release."""
        selected_path = "/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"
        clicked_path = "/RootNode/meshes/mesh_CED45075A077A49A/mesh"
        usd_context = usd.get_context()

        interaction = await self._select_stage_manager_tab("Meshes", "RemixAllMeshesInteractionPlugin")
        usd_context.get_selection().clear_selected_prim_paths()
        await ui_test.human_delay()
        usd_context.get_selection().set_selected_prim_paths([selected_path], False)
        await self._wait_for_usd_selection([selected_path])
        await self._wait_for_stage_manager_model_selection_paths(interaction, [selected_path])

        focus_icon = await self._find_focus_action_icon(clicked_path)
        release_time_usd_selections = []

        # Clicking an unselected row's action selects that row before the action is released.
        with patch(
            "lightspeed.trex.stage_manager.plugin.widget.usd.focus_in_viewport._frame_paths_in_viewport"
        ) as mock_frame_paths_in_viewport:
            mock_frame_paths_in_viewport.side_effect = lambda *_: release_time_usd_selections.append(
                list(usd_context.get_selection().get_selected_prim_paths())
            )
            await focus_icon.click()
            await ui_test.human_delay()

        mock_frame_paths_in_viewport.assert_called_once()
        self.assertEqual([[clicked_path]], release_time_usd_selections)
        await self._wait_for_usd_selection([clicked_path])
        await self._wait_for_stage_manager_model_selection_paths(interaction, [clicked_path])
        self.assertEqual([clicked_path], usd_context.get_selection().get_selected_prim_paths())

    async def test_search_filter_frames_selected_mesh(self):
        target_path = "/RootNode/meshes/mesh_FEE1DEADF00D0001/mesh"
        await self._click_stage_manager_tab("Meshes")

        row = await self._input_stage_manager_search(target_path, target_path)
        await row.click()
        await ui_test.human_delay()
        await self._wait_for_usd_selection([target_path])

        await self._input_stage_manager_search("definitelynomatchingprimname", target_path, expected_visible=False)
        await self._wait_for_usd_selection([target_path])

        await self._input_stage_manager_search("mesh", target_path)
        await self._wait_for_usd_selection([target_path])

        await self._input_stage_manager_search("", target_path)
        await self._wait_for_usd_selection([target_path])

    async def test_ctrl_a_with_mouse_outside_stage_manager_selects_all_mesh_tab_prims(self):
        """Select the active tab's published items after the pointer leaves its frame."""
        await self._select_stage_manager_tab("Meshes", "RemixAllMeshesInteractionPlugin")

        await self._input_stage_manager_search("", _TARGET_MESH_PATH)
        await self._press_ctrl_a_outside_stage_manager()

        await self._wait_for_usd_selection(_MESH_TAB_SELECTION_PATHS)

    async def test_select_all_with_ctrl_a_with_light_filter_selects_retained_prims(self):
        interaction = await self._select_stage_manager_tab("Prims", "RemixAllPrimsInteractionPlugin")
        await self._set_stage_manager_search("")
        await self._wait_for_stage_manager_selectable_path(interaction, _TARGET_MESH_PATH)
        unfiltered_paths = {item.original_tree_item.path for item in interaction.tree.model.iter_selectable_items()}
        self.assertTrue(unfiltered_paths)
        await self._set_stage_manager_light_filter(interaction, True)

        try:
            await self._wait_for_stage_manager_selectable_paths(interaction, _LIGHT_FILTER_SELECTION_PATHS)
            await self._press_ctrl_a_outside_stage_manager()
            await self._wait_for_usd_selection(_LIGHT_FILTER_SELECTION_PATHS)
        finally:
            await self._set_stage_manager_light_filter(interaction, False)
            await self._wait_for_stage_manager_selectable_paths(interaction, unfiltered_paths)

    async def test_select_all_with_ctrl_a_with_empty_search_result_clears_selection(self):
        await self._select_stage_manager_tab("Meshes", "RemixAllMeshesInteractionPlugin")
        usd.get_context().get_selection().set_selected_prim_paths([_TARGET_MESH_INSTANCE_PATH], False)
        await self._wait_for_usd_selection([_TARGET_MESH_INSTANCE_PATH])

        await self._input_stage_manager_search(
            "definitelynomatchingprimname", _TARGET_MESH_PATH, expected_visible=False
        )
        try:
            await self._press_ctrl_a_outside_stage_manager()
            await self._wait_for_usd_selection([])
        finally:
            await self._input_stage_manager_search("", _TARGET_MESH_PATH)

    async def test_ctrl_a_in_search_field_selects_text_without_changing_prim_selection(self):
        await self._select_stage_manager_tab("Meshes", "RemixAllMeshesInteractionPlugin")
        await self._input_stage_manager_search("mesh", _TARGET_MESH_PATH)

        search_selector = f"{_WindowNames.STAGE_MANAGER}//Frame/**/StringField[*].identifier=='search_field'"
        search_fields = [field for field in ui_test.find_all(search_selector) if field.widget.visible]
        self.assertEqual(1, len(search_fields))
        usd.get_context().get_selection().set_selected_prim_paths([_TARGET_MESH_INSTANCE_PATH], False)
        await self._wait_for_usd_selection([_TARGET_MESH_INSTANCE_PATH], settle_frames=5)

        await search_fields[0].click()
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
        await ui_test.human_delay()
        self.assertEqual("", search_fields[0].widget.model.get_value_as_string())
        await self._wait_for_usd_selection([_TARGET_MESH_INSTANCE_PATH], settle_frames=5)
        await self._input_stage_manager_search("", _TARGET_MESH_INSTANCE_PATH)

    async def test_switching_tabs_after_ctrl_a_preserves_mesh_selection(self):
        await self._select_stage_manager_tab("Meshes", "RemixAllMeshesInteractionPlugin")

        await self._input_stage_manager_search("", _TARGET_MESH_PATH)
        await self._press_ctrl_a_outside_stage_manager()
        await self._wait_for_usd_selection(_MESH_TAB_SELECTION_PATHS)

        await self._select_stage_manager_tab("Lights", "RemixAllLightsInteractionPlugin")
        await self._wait_for_usd_selection(_MESH_TAB_SELECTION_PATHS)

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

        def has_valid_prim(item):
            original_item = item.original_tree_item
            return original_item.data and original_item.data.IsValid()

        stage_manager_paths_before = set()
        for item in interaction.tree.model.find_items(has_valid_prim):
            original_item = item.original_tree_item
            stage_manager_paths_before.add(str(original_item.data.GetPath()))

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
        stage_manager_paths_after = set()
        for item in interaction.tree.model.find_items(has_valid_prim):
            original_item = item.original_tree_item
            stage_manager_paths_after.add(str(original_item.data.GetPath()))
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
