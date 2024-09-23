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

import os
import shutil
import tempfile
from enum import Enum

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
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.flux.validator.factory import BASE_HASH_KEY
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, open_stage, wait_stage_loading
from pxr import Sdf, Usd

MATERIAL_HASH = "BC868CE5A075ABB1"
MATERIAL_ROOT_PATH = "/RootNode/Looks/"
RELATIVE_SOURCE_TEXTURE_PATH = "project_example/sources/textures/"
RELATIVE_CAPTURE_TEXTURE_PATH = "project_example/.deps/captures/materials/textures/"
METAL_WALL_ASSET_PARTIAL_BASENAME = "T_MetalPanelWall_HeavyRust_"


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

        # destroy prompt dialogs to avoid unwanted references
        for other_window in ui.Workspace.get_windows():
            if other_window.title in {
                _constants.ASSET_NEED_INGEST_WINDOW_TITLE,
                _constants.ASSET_OUTSIDE_OF_PROJ_DIR_TITLE,
            }:
                prompt_dialog_window = ui_test.find(other_window.title)
                if prompt_dialog_window:
                    prompt_dialog_window.widget.destroy()

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
        asset_path_posix = OmniUrl(asset_path).path
        self.assertEquals(asset_path_posix, texture_file_fields[0].widget.model.get_value_as_string())

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
        asset_path_posix = OmniUrl(asset_path).path
        self.assertEquals(asset_path_posix, texture_file_fields[0].widget.model.get_value_as_string())

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_override_texture_ingested_texture_outside_project_dir_cancel(self):
        # Setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # Select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)

        await ui_test.human_delay(human_delay_speed=10)

        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        property_branches = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_branch'")
        self.assertFalse(texture_file_fields)
        self.assertTrue(property_branches)

        # We expand
        await property_branches[1].click()
        await ui_test.human_delay(human_delay_speed=10)
        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        await ui_test.human_delay(1)
        self.assertTrue(texture_file_fields)

        # Create a temp directory to mimic a location for an external asset
        with tempfile.TemporaryDirectory(dir=_get_test_data("usd/")) as temp_dir:
            shutil.copy(_get_test_data("usd/project_example/sources/textures/ingested/16px_Diffuse.dds"), temp_dir)
            shutil.copy(_get_test_data("usd/project_example/sources/textures/ingested/16px_Diffuse.dds.meta"), temp_dir)
            await ui_test.human_delay(50)

            # We add a new texture
            original_text = texture_file_fields[0].widget.model.get_value_as_string()
            asset_path = _get_test_data(f"{temp_dir}/16px_Diffuse.dds")
            await texture_file_fields[0].click()
            await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)
            await texture_file_fields[0].input(asset_path, end_key=KeyboardInput.ENTER)
            await ui_test.human_delay(3)

        # Ensure there is no ingestion window warning
        ignore_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )
        cancel_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNone(ignore_ingestion_button)
        self.assertIsNone(cancel_ingestion_button)

        # Make sure the "Copy Asset" and "Cancel" buttons exist
        copy_external_asset_button = ui_test.find(
            f"{_constants.ASSET_OUTSIDE_OF_PROJ_DIR_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )
        cancel_external_asset_button = ui_test.find(
            f"{_constants.ASSET_OUTSIDE_OF_PROJ_DIR_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNotNone(copy_external_asset_button)
        self.assertIsNotNone(cancel_external_asset_button)

        # Cancel import
        await cancel_external_asset_button.click()
        await ui_test.human_delay(5)

        # Text field should revert to the original path
        self.assertEquals(original_text, texture_file_fields[0].widget.model.get_value_as_string())

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_override_texture_ingested_texture_outside_project_dir_copy_and_re_ref(self):
        # Setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # Select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)

        await ui_test.human_delay(human_delay_speed=10)

        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        property_branches = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_branch'")
        self.assertFalse(texture_file_fields)
        self.assertTrue(property_branches)

        # We expand
        await property_branches[1].click()
        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        await ui_test.human_delay(1)
        self.assertTrue(texture_file_fields)

        # Create a temp directory to mimic a location for an external asset
        with tempfile.TemporaryDirectory(dir=_get_test_data("usd/")) as temp_dir:
            shutil.copy(_get_test_data("usd/project_example/sources/textures/ingested/16px_Diffuse.dds"), temp_dir)
            shutil.copy(_get_test_data("usd/project_example/sources/textures/ingested/16px_Diffuse.dds.meta"), temp_dir)
            await ui_test.human_delay(50)

            # We add a new texture
            asset_path = _get_test_data(f"{temp_dir}/16px_Diffuse.dds")
            await texture_file_fields[0].click()
            await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)
            await texture_file_fields[0].input(asset_path, end_key=KeyboardInput.ENTER)
            await ui_test.human_delay(3)

            # Ensure there is no ingestion window warning
            ignore_ingestion_button = ui_test.find(
                f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
            )
            cancel_ingestion_button = ui_test.find(
                f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
            )
            self.assertIsNone(ignore_ingestion_button)
            self.assertIsNone(cancel_ingestion_button)

            # Make sure the "Copy Asset" and "Cancel" buttons exist
            copy_external_asset_button = ui_test.find(
                f"{_constants.ASSET_OUTSIDE_OF_PROJ_DIR_TITLE}//Frame/**/Button[*].name=='confirm_button'"
            )
            cancel_external_asset_button = ui_test.find(
                f"{_constants.ASSET_OUTSIDE_OF_PROJ_DIR_TITLE}//Frame/**/Button[*].name=='cancel_button'"
            )
            self.assertIsNotNone(copy_external_asset_button)
            self.assertIsNotNone(cancel_external_asset_button)

            # Copy the asset
            await copy_external_asset_button.click()
            await ui_test.human_delay(50)

            # The original (external) asset path should not equal the field text
            self.assertNotEquals(asset_path, texture_file_fields[0].widget.model.get_value_as_string())

            # Make sure the metadata matches
            self.assertTrue(_path_utils.hash_match_metadata(file_path=asset_path, key=BASE_HASH_KEY))

        # Delete the newly created project_example/assets/ingested subdirectory and its contents
        shutil.rmtree(_get_test_data(f"usd/project_example/{str(_constants.REMIX_INGESTED_ASSETS_FOLDER)}"))

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_override_texture_not_ingested_texture_outside_project_dir_no_metadata_cancel(self):
        # Setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # Select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)

        await ui_test.human_delay(human_delay_speed=10)

        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        property_branches = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_branch'")
        self.assertFalse(texture_file_fields)
        self.assertTrue(property_branches)

        # We expand
        await property_branches[1].click()
        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        await ui_test.human_delay(1)
        self.assertTrue(texture_file_fields)

        # Create a temp directory to mimic a location for an external asset
        with tempfile.TemporaryDirectory(dir=_get_test_data("usd/")) as temp_dir:
            shutil.copy(_get_test_data("usd/project_example/sources/textures/ingested/16px_Diffuse.dds"), temp_dir)
            await ui_test.human_delay(50)

            # We add a new texture
            original_text = texture_file_fields[0].widget.model.get_value_as_string()
            asset_path = _get_test_data(f"{temp_dir}/16px_Diffuse.dds")
            await texture_file_fields[0].click()
            await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)
            await texture_file_fields[0].input(asset_path, end_key=KeyboardInput.ENTER)
            await ui_test.human_delay(3)

        # Make sure the ingestion window appears
        ignore_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )
        cancel_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNone(ignore_ingestion_button)
        self.assertIsNotNone(cancel_ingestion_button)

        # Make sure the copy asset popup buttons do not exist
        copy_external_asset_button = ui_test.find(
            f"{_constants.ASSET_OUTSIDE_OF_PROJ_DIR_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )
        cancel_external_asset_button = ui_test.find(
            f"{_constants.ASSET_OUTSIDE_OF_PROJ_DIR_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNone(copy_external_asset_button)
        self.assertIsNone(cancel_external_asset_button)

        # Cancel import
        await cancel_ingestion_button.click()
        await ui_test.human_delay(5)

        # Text should go back like before
        self.assertEquals(original_text, texture_file_fields[0].widget.model.get_value_as_string())

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

    async def test_copy_from_material_label_copy_menu(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)

        # ensure the material label exists
        material_name_label = ui_test.find(f"{_window}//Frame/**/Label[*].identifier=='material_label'")
        self.assertIsNotNone(material_name_label)

        # test path copy
        await material_name_label.click(right_click=True)
        await ui_test.human_delay(5)
        await omni.kit.ui_test.menu.select_context_menu("Copy Material Path")
        await ui_test.human_delay(5)
        copied_text = omni.kit.clipboard.paste()
        await ui_test.human_delay(10)
        self.assertEqual(copied_text, f"{MATERIAL_ROOT_PATH}mat_{MATERIAL_HASH}")

        # test hash copy
        await material_name_label.click(right_click=True)
        await ui_test.human_delay(5)
        await omni.kit.ui_test.menu.select_context_menu("Copy Material Hash")
        await ui_test.human_delay(5)
        copied_text = omni.kit.clipboard.paste()
        await ui_test.human_delay(10)
        self.assertEqual(copied_text, MATERIAL_HASH)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_copy_from_texture_string_field_copy_menu(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)

        # expand the property branches
        property_branches = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_branch'")
        for index in range(1, 4):
            await property_branches[index].click()
            await ui_test.human_delay(7)

        # ensure the string fields exists
        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        self.assertEqual(len(texture_file_fields), 4)

        # test diffuse material full file path copy
        await texture_file_fields[0].click(right_click=True)
        await ui_test.human_delay(5)
        await omni.kit.ui_test.menu.select_context_menu("Copy Full File Path")
        await ui_test.human_delay(5)
        copied_text = omni.kit.clipboard.paste()
        await ui_test.human_delay(10)

        full_path = os.path.abspath(copied_text)
        start_index = full_path.find("project_example")
        relative_path = full_path[start_index:].replace(os.sep, "/")
        self.assertEqual(relative_path, f"{RELATIVE_CAPTURE_TEXTURE_PATH}{MATERIAL_HASH}.dds")

        # test diffuse material hash copy
        await texture_file_fields[0].click(right_click=True)
        await ui_test.human_delay(5)
        await omni.kit.ui_test.menu.select_context_menu("Copy File Path Hash")
        await ui_test.human_delay(5)
        copied_text = omni.kit.clipboard.paste()
        await ui_test.human_delay(10)
        self.assertEqual(copied_text, MATERIAL_HASH)

        # test maps
        for index, texture_type in enumerate(("metallic", "roughness", "normal"), start=1):
            # test full file path copy
            await texture_file_fields[index].click(right_click=True)
            await ui_test.human_delay(5)
            await omni.kit.ui_test.menu.select_context_menu("Copy Full File Path")
            await ui_test.human_delay(5)
            copied_text = omni.kit.clipboard.paste()
            await ui_test.human_delay(10)

            full_path = os.path.abspath(copied_text)
            start_index = full_path.find("project_example")
            relative_path = full_path[start_index:].replace(os.sep, "/")
            self.assertEqual(
                relative_path, f"{RELATIVE_SOURCE_TEXTURE_PATH}{METAL_WALL_ASSET_PARTIAL_BASENAME}{texture_type}.png"
            )

            # ensure material hash copy is disabled
            await texture_file_fields[index].click(right_click=True)
            await ui_test.human_delay(5)
            context_menu = await omni.kit.ui_test.menu.get_context_menu()
            await ui_test.human_delay(5)
            self.assertFalse("Copy File Path Hash" in context_menu.get("_"))

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_texture_string_field_tooltips_set_and_update(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)

        # expand the property branches
        property_branches = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_branch'")
        for index in range(1, 4):
            await property_branches[index].click()
            await ui_test.human_delay(7)

        # ensure the string fields exists
        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        self.assertEqual(len(texture_file_fields), 4)

        # test diffuse material tooltip in comparison to the asset path
        string_field_mouse_offset = ui_test.Vec2(10, 0)
        await ui_test.emulate_mouse_move(texture_file_fields[0].position + string_field_mouse_offset)
        await ui_test.human_delay(5)
        asset_path = _get_test_data(f"usd/{RELATIVE_CAPTURE_TEXTURE_PATH}{MATERIAL_HASH}.dds")
        self.assertEqual(texture_file_fields[0].widget.tooltip.lower(), asset_path.lower())

        # check that each of the string fields have tooltips after mouse hovered - tooltip is set upon initial hover
        for index, texture_type in enumerate(("metallic", "roughness", "normal"), start=1):
            # move cursor directly over the string field
            await ui_test.emulate_mouse_move(texture_file_fields[index].position + string_field_mouse_offset)
            await ui_test.human_delay(5)

            # ensure that the tooltips are accurate with the asset path
            asset_path = _get_test_data(
                f"usd/{RELATIVE_SOURCE_TEXTURE_PATH}{METAL_WALL_ASSET_PARTIAL_BASENAME}{texture_type}.png"
            )
            self.assertEqual(texture_file_fields[index].widget.tooltip.lower(), asset_path.lower())

        # change the metallic texture to roughness asset
        roughness_texture_asset_path = _get_test_data(
            f"usd/{RELATIVE_SOURCE_TEXTURE_PATH}{METAL_WALL_ASSET_PARTIAL_BASENAME}roughness.png"
        )
        await texture_file_fields[1].input(roughness_texture_asset_path, end_key=KeyboardInput.ENTER)
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
        await ui_test.human_delay(10)

        # move mouse off
        await ui_test.emulate_mouse_move(texture_file_fields[1].position - string_field_mouse_offset)
        await ui_test.human_delay(5)

        # check that the tooltip got updated
        await ui_test.emulate_mouse_move(texture_file_fields[1].position + string_field_mouse_offset)
        await ui_test.human_delay(5)
        self.assertEqual(texture_file_fields[1].widget.tooltip.lower(), roughness_texture_asset_path.lower())

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_texture_string_field_tooltips_with_different_layer_and_edit_target(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)

        # expand the property branches
        property_branches = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='property_branch'")
        for index in range(1, 4):
            await property_branches[index].click()
            await ui_test.human_delay(7)

        # ensure the string fields exists
        texture_file_fields = ui_test.find_all(
            f"{_window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
        )
        self.assertEqual(len(texture_file_fields), 4)

        # test diffuse material tooltip
        string_field_mouse_offset = ui_test.Vec2(10, 0)
        await ui_test.emulate_mouse_move(texture_file_fields[0].position + string_field_mouse_offset)
        await ui_test.human_delay(5)
        asset_path = _get_test_data(f"usd/{RELATIVE_CAPTURE_TEXTURE_PATH}{MATERIAL_HASH}.dds")
        self.assertEqual(texture_file_fields[0].widget.tooltip.lower(), asset_path.lower())

        # change edit target to the root layer
        stage = usd_context.get_stage()
        root_layer = stage.GetRootLayer()
        stage.SetEditTarget(root_layer)

        # test diffuse material tooltip with a different edit target (root layer)
        await ui_test.emulate_mouse_move(texture_file_fields[0].position + string_field_mouse_offset)
        await ui_test.human_delay(5)
        asset_path = _get_test_data(f"usd/{RELATIVE_CAPTURE_TEXTURE_PATH}{MATERIAL_HASH}.dds")
        self.assertEqual(texture_file_fields[0].widget.tooltip.lower(), asset_path.lower())

        # move mouse off
        await ui_test.emulate_mouse_move(texture_file_fields[0].position - string_field_mouse_offset)
        await ui_test.human_delay(5)

        # find a less powerful sublayer and set it as the edit target
        sublayer = None
        for sublayer_path in root_layer.subLayerPaths:
            if "/captures/capture.usda" in sublayer_path:
                sublayer = Sdf.Layer.FindOrOpenRelativeToLayer(root_layer, sublayer_path)
                break

        self.assertIsNotNone(sublayer)
        stage.SetEditTarget(Usd.EditTarget(sublayer))

        # test diffuse material tooltip with a different edit target (sublayer)
        await ui_test.emulate_mouse_move(texture_file_fields[0].position + string_field_mouse_offset)
        await ui_test.human_delay(5)
        asset_path = _get_test_data(f"usd/{RELATIVE_CAPTURE_TEXTURE_PATH}{MATERIAL_HASH}.dds")
        self.assertEqual(texture_file_fields[0].widget.tooltip.lower(), asset_path.lower())

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)
