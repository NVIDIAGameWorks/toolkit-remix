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

from enum import Enum
from unittest.mock import patch

import carb
import carb.input
import omni.client
import omni.ui as ui
import omni.usd
from carb.input import KeyboardInput
from lightspeed.common import constants as _constants
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.contexts import get_instance as _trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _Contexts
from lightspeed.trex.material_properties.shared.widget import SetupUI as _MaterialPropertiesWidget
from lightspeed.trex.selection_tree.shared.widget import SetupUI as _SelectionTreeWidget
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, open_stage, wait_stage_loading


class TestComponents(Enum):
    """
    Simple Enum used to find the components of interest during tests
    """

    CANCEL_BUTTON = 1
    PREVIOUS_BUTTON = 2
    NEXT_BUTTON = 3
    OPEN_OPTION = 4
    CREATE_OPTION = 5
    EDIT_OPTION = 6
    REMASTER_OPTION = 7
    PROJECT_STRING_FIELD = 8
    REMIX_STRING_FIELD = 9
    PROJECT_FILE_ICON = 0
    REMIX_FILE_ICON = 11
    CAPTURE_TREE = 12
    AVAILABLE_MODS_TREE = 13
    SELECTED_MODS_TREE = 14
    FILE_PICKER_DIRECTORY = 15
    FILE_PICKER_FILENAME = 16
    FILE_PICKER_OPEN = 17
    FILE_PICKER_CANCEL = 18


class TestSelectionTreeWidget(AsyncTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__sub_tree_selection_changed = []

    # Before running each test
    async def setUp(self):
        await arrange_windows()
        await open_stage(_get_test_data("usd/project_example/combined.usda"))
        # be sure that the replacement layer is the target layer
        layer_manager = _LayerManagerCore()
        layer_manager.set_edit_target_layer(_LayerType.replacement)

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    async def __setup_widget(self):
        window = ui.Window("TestSelectionTreeUI", height=800, width=400)
        with window.frame:
            with ui.VStack():
                selection_wid = _SelectionTreeWidget("")
                selection_wid.show(True)
                mesh_property_wid = _MaterialPropertiesWidget("")
                mesh_property_wid.show(True)

        def _on_tree_selection_changed(items):
            items = selection_wid.get_selection()
            mesh_property_wid.refresh(items)

        self.__sub_tree_selection_changed.append(
            selection_wid.subscribe_tree_selection_changed(_on_tree_selection_changed)
        )

        await ui_test.human_delay(human_delay_speed=1)

        return window, selection_wid, mesh_property_wid

    async def __find_file_picker_buttons(self, window_title):
        components = {
            TestComponents.FILE_PICKER_DIRECTORY: ui_test.find(
                f"{window_title}//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
            ),
            TestComponents.FILE_PICKER_FILENAME: ui_test.find(
                f"{window_title}//Frame/**/StringField[*].style_type_name_override=='Field'"
            ),
            TestComponents.FILE_PICKER_OPEN: ui_test.find(f"{window_title}//Frame/**/Button[*].text=='Choose'"),
            TestComponents.FILE_PICKER_CANCEL: (
                ui_test.find_all(f"{window_title}//Frame/**/Button[*].text=='Cancel'")[0]
                if ui_test.find_all(f"{window_title}//Frame/**/Button[*].text=='Cancel'")
                else None
            ),
        }

        for component, button in components.items():
            self.assertIsNotNone(button, msg=f"Unexpectedly None: {component}")

        return components

    async def __destroy(self, window, selection_wid, mesh_property_wid):
        mesh_property_wid.destroy()
        selection_wid.destroy()
        window.destroy()

    async def test_select_one_prim_mesh(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)

        await ui_test.human_delay(human_delay_speed=3)

        # the frame material is visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        for frame_none in none_frames:
            self.assertFalse(frame_none.widget.visible)
        self.assertTrue(frame_material.widget.visible)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_select_instance_mesh_prim(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)

        # the frame material is visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        for frame_none in none_frames:
            self.assertFalse(frame_none.widget.visible)
        self.assertTrue(frame_material.widget.visible)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_select_nothing(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths([], False)

        await ui_test.human_delay(human_delay_speed=3)

        # the frame material is not visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_material = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_material_widget'")
        for frame_none in none_frames:
            self.assertTrue(frame_none.widget.visible)
        self.assertFalse(frame_material.widget.visible)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_override_texture_ingested_texture(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)

        await ui_test.human_delay(human_delay_speed=10)

        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        property_branches = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_branch'")
        self.assertFalse(texture_file_fields)  # because we didnt expend
        self.assertTrue(property_branches)

        # we expend
        await property_branches[1].click()
        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        await ui_test.human_delay(1)
        self.assertTrue(texture_file_fields)

        # we add a new texture
        asset_path = _get_test_data("usd/project_example/sources/textures/ingested/16px_Diffuse.dds")
        await texture_file_fields[0].click()
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)
        with patch.object(carb, "log_error"):
            await texture_file_fields[0].input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(3)

        # no ingestion window warning
        ignore_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )
        cancel_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNone(ignore_ingestion_button)
        self.assertIsNone(cancel_ingestion_button)

        # text should be the asset path
        self.assertEquals(asset_path, texture_file_fields[0].widget.model.get_value_as_string())

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_override_texture_not_ingested_texture_cancel(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)

        await ui_test.human_delay(human_delay_speed=10)

        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        property_branches = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_branch'")
        self.assertFalse(texture_file_fields)  # because we didnt expend
        self.assertTrue(property_branches)

        # we expend
        await property_branches[1].click()
        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        await ui_test.human_delay(1)
        self.assertTrue(texture_file_fields)

        # we add a new texture
        original_text = texture_file_fields[0].widget.model.get_value_as_string()
        asset_path = _get_test_data("usd/project_example/sources/textures/not_ingested/16px_Diffuse.dds")
        await texture_file_fields[0].click()
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)
        with patch.object(carb, "log_error"):
            await texture_file_fields[0].input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(3)

        # no ingestion window warning
        ignore_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )
        cancel_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNotNone(ignore_ingestion_button)
        self.assertIsNotNone(cancel_ingestion_button)

        await cancel_ingestion_button.click()
        await ui_test.human_delay()

        # text should go back like before
        self.assertEquals(original_text, texture_file_fields[0].widget.model.get_value_as_string())

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_override_texture_not_ingested_texture_ignore(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)

        await ui_test.human_delay(human_delay_speed=10)

        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        property_branches = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_branch'")
        self.assertFalse(texture_file_fields)  # because we didnt expend
        self.assertTrue(property_branches)

        # we expend
        await property_branches[1].click()
        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        await ui_test.human_delay(1)
        self.assertTrue(texture_file_fields)

        # we add a new texture
        asset_path = _get_test_data("usd/project_example/sources/textures/not_ingested/16px_Diffuse.dds")
        await texture_file_fields[0].click()
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)
        with patch.object(carb, "log_error"):
            await texture_file_fields[0].input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(3)

        # no ingestion window warning
        ignore_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )
        cancel_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNotNone(ignore_ingestion_button)
        self.assertIsNotNone(cancel_ingestion_button)

        await ignore_ingestion_button.click()
        await ui_test.human_delay(20)

        # text should be the asset path
        self.assertEquals(asset_path, texture_file_fields[0].widget.model.get_value_as_string())

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_drop_texture(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test
        _mesh_property_wid.set_external_drag_and_drop(window_name=_window.title)

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)

        await ui_test.human_delay(human_delay_speed=10)
        property_branches = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_branch'")

        # we expand
        await property_branches[2].click()
        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )

        context_inst = _trex_contexts_instance()
        context_inst.set_current_context(_Contexts.STAGE_CRAFT)

        asset_path = _get_test_data("usd/project_example/sources/textures/ingested/16px_metallic.m.rtex.dds")
        omni.appwindow.get_default_app_window().get_window_drop_event_stream().push(0, 0, {"paths": [asset_path]})
        await ui_test.human_delay(20)

        action_button = ui_test.find_all("Texture Assignment//Frame/**/Button[*].name=='AssignButton'")
        await action_button[0].click()
        await ui_test.human_delay(3)

        # no ingestion window warning
        ignore_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )
        cancel_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNone(ignore_ingestion_button)
        self.assertIsNone(cancel_ingestion_button)

        # text should be the asset path
        rel_path = omni.client.normalize_url(omni.usd.make_path_relative_to_current_edit_target(asset_path)).replace(
            "\\", "/"
        )
        self.assertEquals(rel_path, texture_file_fields[0].widget.model.get_value_as_string())

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_texture_set_assignment(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)
        asset_path = _get_test_data("usd/project_example/sources/textures/ingested/16px_metallic.m.rtex.dds")

        await ui_test.human_delay(human_delay_speed=10)
        property_branches = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_branch'")

        # we expand
        await property_branches[2].click()

        assign_button = ui_test.find_all(f"{_window.title}//Frame/**/Button[*].name=='AssignTextureSetButton'")

        # Check that the texture in a similar texture set is also assigned
        await assign_button[0].click()
        await ui_test.human_delay(3)

        picker_buttons = await self.__find_file_picker_buttons("Select Texture Set")
        await ui_test.human_delay(50)
        await picker_buttons[TestComponents.FILE_PICKER_DIRECTORY].input(asset_path, end_key=KeyboardInput.ENTER)
        await picker_buttons[TestComponents.FILE_PICKER_OPEN].click()
        await ui_test.human_delay(10)

        action_button = ui_test.find_all("Texture Assignment//Frame/**/Button[*].name=='AssignButton'")
        await action_button[0].click()
        await ui_test.human_delay(3)

        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )

        rel_path = omni.client.normalize_url(omni.usd.make_path_relative_to_current_edit_target(asset_path)).replace(
            "\\", "/"
        )
        self.assertEquals(rel_path, texture_file_fields[0].widget.model.get_value_as_string())

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)
