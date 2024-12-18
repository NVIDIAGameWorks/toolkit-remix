# noqa PLC0302
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

import shutil
import tempfile

import carb.input
import omni.ui as ui
import omni.usd
from carb.input import KeyboardEventType, KeyboardInput
from lightspeed.common import constants as _constants
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.mesh_properties.shared.widget import SetupUI as _MeshPropertiesWidget
from lightspeed.trex.selection_tree.shared.widget import SetupUI as _SelectionTreeWidget
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.flux.validator.factory import BASE_HASH_KEY
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, open_stage, wait_stage_loading


class ModifierKeyDownScope:
    """
    A context creator to emulate the holding down of modifier keys within a scope. This is a workaround to using
    KeyDownScope which did not directly work with modifiers such as left shift.
    """

    def __init__(self, key: KeyboardInput, human_delay_speed: int = 2):
        self._key = key
        self._human_delay_speed = human_delay_speed

    async def __aenter__(self):
        # The key must be passed as both key and modifier to get the modifier effect to work
        await self.emulate_keyboard(carb.input.KeyboardEventType.KEY_PRESS, self._key, self._key)
        await ui_test.human_delay(self._human_delay_speed)

    async def __aexit__(self, exc_type, exc, tb):
        # No modifier should be passed so the modifier effect does not get stuck
        await self.emulate_keyboard(carb.input.KeyboardEventType.KEY_RELEASE, self._key)
        await ui_test.human_delay(self._human_delay_speed)

    async def emulate_keyboard(self, event_type: KeyboardEventType, key: KeyboardInput, modifier: KeyboardInput = 0):
        keyboard = omni.appwindow.get_default_app_window().get_keyboard()
        carb.input.acquire_input_provider().buffer_keyboard_key_event(keyboard, event_type, key, modifier)


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
                mesh_property_wid = _MeshPropertiesWidget("")
                mesh_property_wid.show(True)

        def _on_tree_selection_changed(items):
            items = selection_wid.get_selection()
            mesh_property_wid.refresh(items)

        self.__sub_tree_selection_changed.append(
            selection_wid.subscribe_tree_selection_changed(_on_tree_selection_changed)
        )

        await ui_test.human_delay(human_delay_speed=1)

        return window, selection_wid, mesh_property_wid

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

        # the frame None is visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        frame_mesh_prim = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")
        for frame_none in none_frames:
            self.assertTrue(frame_none.widget.visible)
        self.assertFalse(frame_mesh_ref.widget.visible)
        self.assertFalse(frame_mesh_prim.widget.visible)

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

        # the frame mesh prim is visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        frame_mesh_prim = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")
        for frame_none in none_frames:
            self.assertFalse(frame_none.widget.visible)
        self.assertFalse(frame_mesh_ref.widget.visible)
        self.assertTrue(frame_mesh_prim.widget.visible)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_select_mesh_ref(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)

        await item_prims[0].click()

        # the frame mesh ref is visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        frame_mesh_prim = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")
        for frame_none in none_frames:
            self.assertFalse(frame_none.widget.visible)
        self.assertTrue(frame_mesh_ref.widget.visible)
        self.assertFalse(frame_mesh_prim.widget.visible)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_select_light(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/lights/light_9907D0B07D040077"], False)

        await ui_test.human_delay(human_delay_speed=3)

        # the properties are visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        frame_mesh_prim = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")
        for frame_none in none_frames:
            self.assertFalse(frame_none.widget.visible)
        self.assertFalse(frame_mesh_ref.widget.visible)
        self.assertTrue(frame_mesh_prim.widget.visible)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_select_light_live_light(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/lights/light_9907D0B07D040077"], False)

        await ui_test.human_delay(human_delay_speed=3)

        # create the light
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        self.assertEqual(len(item_file_meshes), 1)
        await item_file_meshes[0].click()
        window_name = "Light creator"
        # The file picker window should now be opened (0 < len(widgets))
        self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))
        light_disk_button = ui_test.find(f"{window_name}//Frame/**/Button[*].name=='LightDisk'")
        self.assertIsNotNone(light_disk_button)
        await light_disk_button.click()
        await ui_test.human_delay(human_delay_speed=3)

        # the properties are visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        frame_mesh_prim = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")
        for frame_none in none_frames:
            self.assertFalse(frame_none.widget.visible)
        self.assertFalse(frame_mesh_ref.widget.visible)
        self.assertTrue(frame_mesh_prim.widget.visible)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_select_mesh_live_light(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)

        # create the light
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        self.assertEqual(len(item_file_meshes), 2)
        await item_file_meshes[1].click()
        window_name = "Light creator"
        # The file picker window should now be opened (0 < len(widgets))
        self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))
        light_disk_button = ui_test.find(f"{window_name}//Frame/**/Button[*].name=='LightDisk'")
        self.assertIsNotNone(light_disk_button)
        await light_disk_button.click()
        await ui_test.human_delay(human_delay_speed=3)

        # the properties are visible
        none_frames = ui_test.find_all(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        frame_mesh_prim = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")
        for frame_none in none_frames:
            self.assertFalse(frame_none.widget.visible)
        self.assertFalse(frame_mesh_ref.widget.visible)
        self.assertTrue(frame_mesh_prim.widget.visible)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_prim_ref_grayed_out(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)
        await item_prims[0].click()

        # test restore
        restore = ui_test.find(f"{_window.title}//Frame/**/Image[*].identifier=='restore'")
        self.assertIsNotNone(restore)

        await restore.click()
        await ui_test.human_delay()

        window_name = "##restore"
        confirm_button = ui_test.find(f"{window_name}//Frame/**/Button[*].name=='confirm_button'")
        cancel_button = ui_test.find(f"{window_name}//Frame/**/Button[*].name=='cancel_button'")
        self.assertIsNotNone(confirm_button)
        self.assertIsNotNone(cancel_button)

        await confirm_button.click()
        await ui_test.human_delay(3)
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_BAC90CAA733B0859_0/mesh"], False)
        await ui_test.human_delay(3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        await item_prims[0].click()
        await ui_test.human_delay()

        # asset from capture disable ref prim
        mesh_ref_prim_field = ui_test.find(
            f"{_window.title}//Frame/**/StringField[*].identifier=='mesh_ref_prim_field'"
        )
        mesh_ref_default_prim_checkbox = ui_test.find(
            f"{_window.title}//Frame/**/CheckBox[*].identifier=='mesh_ref_default_prim_checkbox'"
        )
        self.assertIsNotNone(mesh_ref_prim_field)
        self.assertIsNotNone(mesh_ref_default_prim_checkbox)
        self.assertFalse(mesh_ref_prim_field.widget.enabled)
        self.assertFalse(mesh_ref_default_prim_checkbox.widget.enabled)

        mesh_ref_field = ui_test.find(f"{_window.title}//Frame/**/StringField[*].identifier=='mesh_ref_field'")
        self.assertIsNotNone(mesh_ref_field)

        # but if we have an invalid path, ref prim UI is enabled
        await mesh_ref_field.click()
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.BACKSPACE)
        await ui_test.human_delay()
        mesh_ref_prim_field = ui_test.find(
            f"{_window.title}//Frame/**/StringField[*].identifier=='mesh_ref_prim_field'"
        )
        mesh_ref_default_prim_checkbox = ui_test.find(
            f"{_window.title}//Frame/**/CheckBox[*].identifier=='mesh_ref_default_prim_checkbox'"
        )
        self.assertTrue(mesh_ref_prim_field.widget.enabled)
        self.assertTrue(mesh_ref_default_prim_checkbox.widget.enabled)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_replace_mesh_ref_using_file_picker(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)
        await item_prims[0].click()

        # test replace a mesh with a new one
        replace_ref_open_folder = ui_test.find(
            f"{_window.title}//Frame/**/Image[*].identifier=='replace_ref_open_folder'"
        )
        self.assertIsNotNone(replace_ref_open_folder)

        await replace_ref_open_folder.click()
        await ui_test.human_delay(1)

        window_name = "Select a reference file"

        # The file picker window should now be opened (0 < len(widgets))
        self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))

        select_button = ui_test.find(f"{window_name}//Frame/**/Button[*].text=='Select'")
        toolbar_field = ui_test.find(f"{window_name}//Frame/**/Rectangle[*].style_type_name_override=='ToolBar.Field'")

        self.assertIsNotNone(select_button)
        self.assertIsNotNone(toolbar_field)

        # It takes a while for the tree to update
        await ui_test.human_delay(10)

        asset_path = _get_test_data("usd/project_example/ingested_assets/output/good/cube.usda")

        # This doesn't work! Because there is a combobox stacked over the input field, on the CI, it will click on
        # the arrow of the combobox and input nothing!
        # dir_path_field = ui_test.find(f"{window_name}//Frame/**/StringField[*].identifier=='filepicker_directory_path'")  # noqa
        # await dir_path_field.input(asset_path, end_key=KeyboardInput.ENTER)

        # work around
        field_position = toolbar_field.position
        await toolbar_field.click(pos=ui_test.Vec2(field_position.x + 1, field_position.y + 1))
        await ui_test.human_delay(1)
        await ui_test.emulate_keyboard_press(KeyboardInput.TAB)
        await ui_test.human_delay(1)
        await ui_test.emulate_char_press(asset_path)
        await ui_test.human_delay(1)
        await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
        await select_button.click()
        await ui_test.human_delay()
        # the new asset give us 4 prims
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 5)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_replace_mesh_ref_using_file_picker_outside_project_dir_cancel(self):
        # Create a temp directory to mimic a location for an external asset
        with tempfile.TemporaryDirectory(dir=_get_test_data("usd/")) as temp_dir:
            shutil.copy(_get_test_data("usd/project_example/ingested_assets/output/good/cube.usda"), temp_dir)
            shutil.copy(_get_test_data("usd/project_example/ingested_assets/output/good/cube.usda.meta"), temp_dir)

            # Setup
            _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

            # Select
            usd_context = omni.usd.get_context()
            usd_context.get_selection().set_selected_prim_paths(
                ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
            )
            await ui_test.human_delay(human_delay_speed=3)

            item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
            self.assertEquals(len(item_prims), 3)
            await item_prims[0].click()

            # Test replace a mesh with a new one
            replace_ref_open_folder = ui_test.find(
                f"{_window.title}//Frame/**/Image[*].identifier=='replace_ref_open_folder'"
            )
            self.assertIsNotNone(replace_ref_open_folder)

            await replace_ref_open_folder.click()
            await ui_test.human_delay(1)

            window_name = "Select a reference file"

            # The file picker window should now be opened (0 < len(widgets))
            self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))

            select_button = ui_test.find(f"{window_name}//Frame/**/Button[*].text=='Select'")
            toolbar_field = ui_test.find(
                f"{window_name}//Frame/**/Rectangle[*].style_type_name_override=='ToolBar.Field'"
            )

            self.assertIsNotNone(select_button)
            self.assertIsNotNone(toolbar_field)

            # It takes a while for the tree to update
            await ui_test.human_delay(10)

            # Select file in filepicker
            asset_path = _get_test_data(f"{temp_dir}/cube.usda")
            field_position = toolbar_field.position
            await toolbar_field.click(pos=ui_test.Vec2(field_position.x + 1, field_position.y + 1))
            await ui_test.human_delay(1)
            await ui_test.emulate_keyboard_press(KeyboardInput.TAB)
            await ui_test.human_delay(1)
            await ui_test.emulate_char_press(asset_path)
            await ui_test.human_delay(1)
            await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
            await select_button.click()
            await ui_test.human_delay()

        # Make sure that the ingestion window did not show
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

        # Cancel import and ensure the external asset was not imported
        await cancel_external_asset_button.click()
        await ui_test.human_delay(5)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_replace_mesh_ref_using_file_picker_outside_project_dir_copy_and_re_ref(self):
        # Create a temp directory to mimic a location for an external asset
        with tempfile.TemporaryDirectory(dir=_get_test_data("usd/")) as temp_dir:
            shutil.copy(_get_test_data("usd/project_example/ingested_assets/output/good/cube.usda"), temp_dir)
            shutil.copy(_get_test_data("usd/project_example/ingested_assets/output/good/cube.usda.meta"), temp_dir)

            # Setup
            _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

            # Select
            usd_context = omni.usd.get_context()
            usd_context.get_selection().set_selected_prim_paths(
                ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
            )
            await ui_test.human_delay(human_delay_speed=3)

            item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
            self.assertEquals(len(item_prims), 3)
            await item_prims[0].click()

            # Test replace a mesh with a new one
            replace_ref_open_folder = ui_test.find(
                f"{_window.title}//Frame/**/Image[*].identifier=='replace_ref_open_folder'"
            )
            self.assertIsNotNone(replace_ref_open_folder)

            await replace_ref_open_folder.click()
            await ui_test.human_delay(1)

            window_name = "Select a reference file"

            # The file picker window should now be opened (0 < len(widgets))
            self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))

            select_button = ui_test.find(f"{window_name}//Frame/**/Button[*].text=='Select'")
            toolbar_field = ui_test.find(
                f"{window_name}//Frame/**/Rectangle[*].style_type_name_override=='ToolBar.Field'"
            )

            self.assertIsNotNone(select_button)
            self.assertIsNotNone(toolbar_field)

            # It takes a while for the tree to update
            await ui_test.human_delay(10)

            # Select file in filepicker
            asset_path = _get_test_data(f"{temp_dir}/cube.usda")
            field_position = toolbar_field.position
            await toolbar_field.click(pos=ui_test.Vec2(field_position.x + 1, field_position.y + 1))
            await ui_test.human_delay(1)
            await ui_test.emulate_keyboard_press(KeyboardInput.TAB)
            await ui_test.human_delay(1)
            await ui_test.emulate_char_press(asset_path)
            await ui_test.human_delay(1)
            await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
            await select_button.click()
            await ui_test.human_delay()

            # Make sure that the ingestion window did not show
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

            # Make sure that new ref exists
            item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
            self.assertEqual(len(item_prims), 5)

            # Check that the reference is from a new internal copy and not the original external asset
            item_ref = item_prims[0].widget
            self.assertEqual(item_ref.text, "cube.usda")
            self.assertEqual(item_ref.tooltip, "./assets/ingested/cube.usda")

            # Make sure the metadata matches
            self.assertTrue(_path_utils.hash_match_metadata(file_path=asset_path, key=BASE_HASH_KEY))

            # Delete the newly created project_example/assets/ingested subdirectory and its contents
            shutil.rmtree(_get_test_data(f"usd/project_example/{_constants.REMIX_INGESTED_ASSETS_FOLDER}"))

            await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_replace_mesh_ref_using_file_picker_outside_project_dir_no_metadata_cancel(self):
        # Create a temp directory to mimic a location for an external asset
        with tempfile.TemporaryDirectory(dir=_get_test_data("usd/")) as temp_dir:
            shutil.copy(_get_test_data("usd/project_example/ingested_assets/output/good/cube.usda"), temp_dir)

            # Setup
            _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

            # Select
            usd_context = omni.usd.get_context()
            usd_context.get_selection().set_selected_prim_paths(
                ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
            )
            await ui_test.human_delay(human_delay_speed=3)

            item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
            self.assertEquals(len(item_prims), 3)
            await item_prims[0].click()

            # Test replace a mesh with a new one
            replace_ref_open_folder = ui_test.find(
                f"{_window.title}//Frame/**/Image[*].identifier=='replace_ref_open_folder'"
            )
            self.assertIsNotNone(replace_ref_open_folder)

            await replace_ref_open_folder.click()
            await ui_test.human_delay(1)

            window_name = "Select a reference file"

            # The file picker window should now be opened (0 < len(widgets))
            self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))

            select_button = ui_test.find(f"{window_name}//Frame/**/Button[*].text=='Select'")
            toolbar_field = ui_test.find(
                f"{window_name}//Frame/**/Rectangle[*].style_type_name_override=='ToolBar.Field'"
            )

            self.assertIsNotNone(select_button)
            self.assertIsNotNone(toolbar_field)

            # It takes a while for the tree to update
            await ui_test.human_delay(10)

            # Select file in filepicker
            asset_path = _get_test_data(f"{temp_dir}/cube.usda")
            field_position = toolbar_field.position
            await toolbar_field.click(pos=ui_test.Vec2(field_position.x + 1, field_position.y + 1))
            await ui_test.human_delay(1)
            await ui_test.emulate_keyboard_press(KeyboardInput.TAB)
            await ui_test.human_delay(1)
            await ui_test.emulate_char_press(asset_path)
            await ui_test.human_delay(1)
            await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
            await select_button.click()
            await ui_test.human_delay()

        # Make sure that the ingestion popup appeared - there should be no "ok" button
        ignore_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )
        cancel_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNone(ignore_ingestion_button)
        self.assertIsNotNone(cancel_ingestion_button)

        # Cancel import and ensure the external asset was not imported
        await cancel_ingestion_button.click()
        await ui_test.human_delay(5)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_replace_mesh_ref_using_string_field_empty_path(self):
        await self.__replace_mesh_ref_using_string_field_wrong_path("")

    async def test_replace_mesh_ref_using_string_field_wrong_path(self):
        await self.__replace_mesh_ref_using_string_field_wrong_path("wrong/path")
        await self.__replace_mesh_ref_using_string_field_wrong_path("wrong    path")
        await self.__replace_mesh_ref_using_string_field_wrong_path("111111")

    async def __replace_mesh_ref_using_string_field_wrong_path(self, asset_path):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)
        await item_prims[0].click()

        # test replace a mesh with a new one
        await ui_test.human_delay()
        mesh_ref_field = ui_test.find(f"{_window.title}//Frame/**/StringField[*].identifier=='mesh_ref_field'")
        self.assertIsNotNone(mesh_ref_field)

        original_text = mesh_ref_field.widget.model.get_value_as_string()
        await mesh_ref_field.click()
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)
        await mesh_ref_field.input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(human_delay_speed=3)
        ignore_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )
        cancel_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNone(ignore_ingestion_button)
        self.assertIsNone(cancel_ingestion_button)

        # text should go back like before
        self.assertEquals(original_text, mesh_ref_field.widget.model.get_value_as_string())

        # nothing changed
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )
        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_replace_mesh_ref_using_string_field_good_ingested_asset(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)
        await item_prims[0].click()

        # test replace a mesh with a new one
        await ui_test.human_delay()
        mesh_ref_field = ui_test.find(f"{_window.title}//Frame/**/StringField[*].identifier=='mesh_ref_field'")
        self.assertIsNotNone(mesh_ref_field)

        original_text = mesh_ref_field.widget.model.get_value_as_string()
        await mesh_ref_field.click()
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)
        asset_path = _get_test_data("usd/project_example/ingested_assets/output/good/cube.usda")
        await mesh_ref_field.input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(human_delay_speed=3)

        ignore_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )
        cancel_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNone(ignore_ingestion_button)
        self.assertIsNone(cancel_ingestion_button)

        # text should not go back like before
        self.assertNotEquals(original_text, mesh_ref_field.widget.model.get_value_as_string())

        # the ref was replaced. We should have the new ref
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Toto"], False
        )
        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 5)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_replace_mesh_ref_using_string_field_bad_ingested_hash_different_asset_cancel(self):
        await self.__replace_mesh_ref_using_string_field_bad_ingested_asset_cancel(
            _get_test_data("usd/project_example/ingested_assets/output/hash_different/cube.usda")
        )

    async def test_replace_mesh_ref_using_string_field_bad_ingested_failed_asset_cancel(self):
        await self.__replace_mesh_ref_using_string_field_bad_ingested_asset_cancel(
            _get_test_data("usd/project_example/ingested_assets/output/ingestion_failed/cube.usda")
        )

    async def test_replace_mesh_ref_using_string_field_bad_ingested_no_metadata_asset_cancel(self):
        await self.__replace_mesh_ref_using_string_field_bad_ingested_asset_cancel(
            _get_test_data("usd/project_example/ingested_assets/output/no_metadata/cube.usda")
        )

    async def __replace_mesh_ref_using_string_field_bad_ingested_asset_cancel(self, asset_path):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)
        await item_prims[0].click()

        # test replace a mesh with a new one
        await ui_test.human_delay()
        mesh_ref_field = ui_test.find(f"{_window.title}//Frame/**/StringField[*].identifier=='mesh_ref_field'")
        self.assertIsNotNone(mesh_ref_field)

        original_text = mesh_ref_field.widget.model.get_value_as_string()
        await mesh_ref_field.click()
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)
        await mesh_ref_field.input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(human_delay_speed=3)

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
        self.assertEquals(original_text, mesh_ref_field.widget.model.get_value_as_string())

        # nothing changed
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )
        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_replace_mesh_ref_using_string_field_bad_ingested_hash_different_asset_ignore(self):
        await self.__replace_mesh_ref_using_string_field_bad_ingested_asset_ignore(
            _get_test_data("usd/project_example/ingested_assets/output/hash_different/cube.usda")
        )

    async def test_replace_mesh_ref_using_string_field_bad_ingested_failed_asset_ignore(self):
        await self.__replace_mesh_ref_using_string_field_bad_ingested_asset_ignore(
            _get_test_data("usd/project_example/ingested_assets/output/ingestion_failed/cube.usda")
        )

    async def test_replace_mesh_ref_using_string_field_bad_ingested_no_metadata_asset_ignore(self):
        await self.__replace_mesh_ref_using_string_field_bad_ingested_asset_ignore(
            _get_test_data("usd/project_example/ingested_assets/output/no_metadata/cube.usda")
        )

    async def __replace_mesh_ref_using_string_field_bad_ingested_asset_ignore(self, asset_path):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)
        await item_prims[0].click()

        # test replace a mesh with a new one
        await ui_test.human_delay()
        mesh_ref_field = ui_test.find(f"{_window.title}//Frame/**/StringField[*].identifier=='mesh_ref_field'")
        self.assertIsNotNone(mesh_ref_field)

        original_text = mesh_ref_field.widget.model.get_value_as_string()
        await mesh_ref_field.click()
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)
        await mesh_ref_field.input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(human_delay_speed=3)

        ignore_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )

        cancel_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNotNone(ignore_ingestion_button)
        self.assertIsNotNone(cancel_ingestion_button)

        await ignore_ingestion_button.click()
        await ui_test.human_delay()

        # text should go back like before
        self.assertNotEquals(original_text, mesh_ref_field.widget.model.get_value_as_string())

        # the ref was replaced. We should have the new ref
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Toto"], False
        )
        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 5)
        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_replace_mesh_ref_using_string_field_asset_outside_project_dir_cancel(self):
        # Setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # Select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)
        await item_prims[0].click()

        # Make sure the mesh reference field exists
        await ui_test.human_delay()
        mesh_ref_field = ui_test.find(f"{_window.title}//Frame/**/StringField[*].identifier=='mesh_ref_field'")
        self.assertIsNotNone(mesh_ref_field)

        original_text = mesh_ref_field.widget.model.get_value_as_string()
        await mesh_ref_field.click()
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)

        # Create a temp directory to mimic a location for an external asset
        with tempfile.TemporaryDirectory(dir=_get_test_data("usd/")) as temp_dir:
            shutil.copy(_get_test_data("usd/project_example/ingested_assets/output/good/cube.usda"), temp_dir)
            shutil.copy(_get_test_data("usd/project_example/ingested_assets/output/good/cube.usda.meta"), temp_dir)

            # Attempt replacing the reference with the path of an external asset
            await ui_test.human_delay(50)
            asset_path = _get_test_data(f"{temp_dir}/cube.usda")
            await mesh_ref_field.input(asset_path, end_key=KeyboardInput.ENTER)
            await ui_test.human_delay(human_delay_speed=3)

        # Make sure that the ingestion window did not show
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

        # Cancel import and ensure the external asset was not imported
        await cancel_external_asset_button.click()
        await ui_test.human_delay(5)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)

        # The text should revert back to what it was originally
        self.assertEquals(original_text, mesh_ref_field.widget.model.get_value_as_string())

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_replace_mesh_ref_using_string_field_asset_outside_project_dir_copy_and_re_ref(self):
        # Setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # Select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)
        await item_prims[0].click()

        # Make sure the mesh reference field exists
        await ui_test.human_delay()
        mesh_ref_field = ui_test.find(f"{_window.title}//Frame/**/StringField[*].identifier=='mesh_ref_field'")
        self.assertIsNotNone(mesh_ref_field)

        original_text = mesh_ref_field.widget.model.get_value_as_string()
        await mesh_ref_field.click()
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)

        # Create a temp directory to mimic a location for an external asset
        with tempfile.TemporaryDirectory(dir=_get_test_data("usd/")) as temp_dir:
            shutil.copy(_get_test_data("usd/project_example/ingested_assets/output/good/cube.usda"), temp_dir)
            shutil.copy(_get_test_data("usd/project_example/ingested_assets/output/good/cube.usda.meta"), temp_dir)

            # Attempt replacing the reference with the path of an external asset
            await ui_test.human_delay(50)
            asset_path = _get_test_data(f"{temp_dir}/cube.usda")
            await mesh_ref_field.input(asset_path, end_key=KeyboardInput.ENTER)
            await ui_test.human_delay(human_delay_speed=3)

            # Make sure that the ingestion window did not show
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

            # Make sure that new ref exists
            item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
            self.assertEqual(len(item_prims), 5)

            # Check that the reference is from a new internal copy and not the original external asset
            item_ref = item_prims[0].widget
            self.assertEqual(item_ref.text, "cube.usda")
            self.assertEqual(item_ref.tooltip, "./assets/ingested/cube.usda")

            # Make sure the metadata matches
            self.assertTrue(_path_utils.hash_match_metadata(file_path=asset_path, key=BASE_HASH_KEY))

            # The text should not revert back to what it was originally
            self.assertNotEquals(original_text, mesh_ref_field.widget.model.get_value_as_string())

            # Delete the newly created project_example/assets/ingested subdirectory and its contents
            shutil.rmtree(_get_test_data(f"usd/project_example/{_constants.REMIX_INGESTED_ASSETS_FOLDER}"))

            await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_replace_mesh_ref_using_string_field_asset_outside_project_dir_no_metadata(self):
        # Setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # Select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)
        await item_prims[0].click()

        # Make sure the mesh reference field exists
        await ui_test.human_delay()
        mesh_ref_field = ui_test.find(f"{_window.title}//Frame/**/StringField[*].identifier=='mesh_ref_field'")
        self.assertIsNotNone(mesh_ref_field)

        original_text = mesh_ref_field.widget.model.get_value_as_string()
        await mesh_ref_field.click()
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)

        # Create a temp directory to mimic a location for an external asset
        with tempfile.TemporaryDirectory(dir=_get_test_data("usd/")) as temp_dir:
            shutil.copy(_get_test_data("usd/project_example/ingested_assets/output/good/cube.usda"), temp_dir)

            # Attempt replacing the reference with the path of an external asset
            await ui_test.human_delay(50)
            asset_path = _get_test_data(f"{temp_dir}/cube.usda")
            await mesh_ref_field.input(asset_path, end_key=KeyboardInput.ENTER)
            await ui_test.human_delay(human_delay_speed=3)

        # Make sure the ingestion window showed and that there is no ignore button
        ignore_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )
        cancel_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNone(ignore_ingestion_button)
        self.assertIsNotNone(cancel_ingestion_button)

        await cancel_ingestion_button.click()
        await ui_test.human_delay()

        # The text should revert back to what it was originally (nothing should have happened)
        self.assertEquals(original_text, mesh_ref_field.widget.model.get_value_as_string())

        # There should still be the same amount of prims
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEquals(len(item_prims), 3)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_assign_single_remix_category(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)

        category_button = ui_test.find(f"{_window.title}//Frame/**/Image[*].name=='Categories'")
        await category_button.click()
        await ui_test.human_delay(3)

        # Set a random remix category for us to assign
        box = ui_test.find("Add Remix Categories to Prim//Frame/**/CheckBox[*].name=='remix_category:world_ui'")
        await ui_test.emulate_mouse_move_and_click(box.position)
        await ui_test.human_delay(3)

        # Assign the category
        assign_button = ui_test.find(
            "Add Remix Categories to Prim//Frame/**/Button[*].identifier=='AssignCategoryButton'"
        )
        await assign_button.click()
        await ui_test.human_delay(3)

        # Check that the category got assigned on the prim
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath(
            "/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"
        )
        attrs = prim.GetAttributes()
        test_attr = [attr for attr in attrs if attr.GetName() == "remix_category:world_ui"]

        self.assertEqual(len(test_attr), 1)

        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_assign_multiple_remix_category(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        await ui_test.human_delay(human_delay_speed=3)

        category_button = ui_test.find(f"{_window.title}//Frame/**/Image[*].name=='Categories'")
        await category_button.click()
        await ui_test.human_delay(3)

        # Set a random remix category for us to assign
        box = ui_test.find("Add Remix Categories to Prim//Frame/**/CheckBox[*].name=='remix_category:world_ui'")
        await ui_test.emulate_mouse_move_and_click(box.position)
        await ui_test.human_delay(3)
        box2 = ui_test.find("Add Remix Categories to Prim//Frame/**/CheckBox[*].name=='remix_category:decal_Static'")
        await ui_test.emulate_mouse_move_and_click(box2.position)
        await ui_test.human_delay(3)

        # Assign the category
        assign_button = ui_test.find(
            "Add Remix Categories to Prim//Frame/**/Button[*].identifier=='AssignCategoryButton'"
        )
        await assign_button.click()

        await ui_test.human_delay(3)

        # Check that the category got assigned on the prim
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath(
            "/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"
        )
        attrs = prim.GetAttributes()
        test_attr = [
            attr for attr in attrs if attr.GetName() in ("remix_category:world_ui", "remix_category:decal_Static")
        ]

        self.assertEqual(len(test_attr), 2)
        await self.__destroy(_window, _selection_wid, _mesh_property_wid)

    async def test_remix_categories_button_visibility(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        category_button = ui_test.find(f"{_window.title}//Frame/**/ScrollingFrame[*].name=='CategoriesFrame'")
        await ui_test.human_delay(50)
        self.assertTrue(category_button.widget.visible)

        items = ui_test.find_all(f"{_window.title}//Frame/**/ScrollingFrame[*].name=='TreePanelBackground'")

        await items[1].click()
        await ui_test.human_delay(60)

        category_button = ui_test.find(f"{_window.title}//Frame/**/ScrollingFrame[*].name=='CategoriesFrame'")
        self.assertFalse(category_button.widget.visible)

    async def test_remix_categories_button_visibility_multi_select(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )

        category_button = ui_test.find(f"{_window.title}//Frame/**/ScrollingFrame[*].name=='CategoriesFrame'")
        await ui_test.human_delay(50)
        self.assertTrue(category_button.widget.visible)

        prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")

        for prim in prims:
            async with ModifierKeyDownScope(key=KeyboardInput.LEFT_SHIFT):
                await prim.click()
                await ui_test.human_delay(3)

        category_button = ui_test.find(f"{_window.title}//Frame/**/ScrollingFrame[*].name=='CategoriesFrame'")
        self.assertFalse(category_button.widget.visible)
