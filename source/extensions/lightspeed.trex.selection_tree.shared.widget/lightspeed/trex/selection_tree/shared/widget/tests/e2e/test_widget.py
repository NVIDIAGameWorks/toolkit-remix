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
import omni.kit.undo
import omni.ui as ui
import omni.usd
from carb.input import KeyboardInput
from lightspeed.common import constants as _constants
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.selection_tree.shared.widget import SetupUI as _SetupUI
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, open_stage, wait_stage_loading


class TestSelectionTreeWidget(AsyncTestCase):
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

    async def __setup_widget(self, height=800):
        window = ui.Window("TestSelectionTreeUI", height=height, width=400)
        _SetupUI.DEFAULT_TREE_FRAME_HEIGHT = height - 100
        with window.frame:
            wid = _SetupUI("")
            wid.show(True)

        await ui_test.human_delay(human_delay_speed=1)

        return window, wid

    async def __destroy(self, window, wid):
        wid.destroy()
        window.destroy()

    async def test_select_one_prim_mesh(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")

        self.assertFalse(item_prims)

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)

        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_mesh'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")
        item_instance_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")

        self.assertEqual(len(item_prims), 2)  # the ref item + the prim item
        self.assertEqual(len(item_meshes), 1)
        self.assertEqual(len(item_file_meshes), 2)
        self.assertEqual(len(item_instance_groups), 1)
        self.assertEqual(len(item_instance_meshes), 0)  # we didn't expand the instance group

        await self.__destroy(_window, _wid)

    async def test_select_one_prim_light(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")

        self.assertFalse(item_prims)

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/lights/light_9907D0B07D040077"], False)

        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_mesh'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")
        item_instance_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")

        self.assertEqual(len(item_prims), 0)  # the ref item
        self.assertEqual(len(item_meshes), 1)
        self.assertEqual(len(item_file_meshes), 1)  # add ref + add light
        self.assertEqual(len(item_instance_groups), 1)
        self.assertEqual(len(item_instance_meshes), 1)  # for light, instance are selected by default

        await self.__destroy(_window, _wid)

    async def test_select_one_prim_instance(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")

        self.assertFalse(item_prims)

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)

        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_mesh'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")
        item_instance_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")

        self.assertEqual(len(item_prims), 2)  # the ref item + the prim item
        self.assertEqual(len(item_meshes), 1)
        self.assertEqual(len(item_file_meshes), 2)
        self.assertEqual(len(item_instance_groups), 1)
        self.assertEqual(len(item_instance_meshes), 1)  # because we selected the instance, the instance is shown

        await self.__destroy(_window, _wid)

    async def test_select_one_prim_instance_mesh_light(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")

        self.assertFalse(item_prims)

        usd_context.get_selection().set_selected_prim_paths(
            [
                "/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh",
                "/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh",
                "/RootNode/lights/light_9907D0B07D040077",
            ],
            False,
        )

        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_mesh'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")
        item_instance_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")

        self.assertEqual(len(item_prims), 2)  # the ref item + the prim item
        self.assertEqual(len(item_meshes), 2)
        self.assertEqual(len(item_file_meshes), 3)
        self.assertEqual(len(item_instance_groups), 2)
        self.assertEqual(len(item_instance_meshes), 2)

        await self.__destroy(_window, _wid)

    async def test_select_two_prim(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")

        self.assertFalse(item_prims)

        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh", "/RootNode/meshes/mesh_CED45075A077A49A/mesh"], False
        )

        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_mesh'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")
        item_instance_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")

        self.assertEqual(len(item_prims), 4)  # the ref item + the prim item
        self.assertEqual(len(item_meshes), 2)
        self.assertEqual(len(item_file_meshes), 4)
        self.assertEqual(len(item_instance_groups), 2)
        self.assertEqual(len(item_instance_meshes), 0)  # we didn't expand the instance group

        await self.__destroy(_window, _wid)

    async def test_select_two_prim_expand_one_inst_group(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh", "/RootNode/meshes/mesh_CED45075A077A49A/mesh"], False
        )

        await ui_test.human_delay(human_delay_speed=3)
        item_instance_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")
        branch_instance_meshes = ui_test.find_all(
            f"{_window.title}//Frame/**/Image[*].identifier=='branch_instance_group'"
        )

        self.assertEqual(len(item_instance_meshes), 0)  # we didn't expand the instance group

        await branch_instance_meshes[0].click()
        await ui_test.human_delay(human_delay_speed=1)
        item_instance_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")
        self.assertEqual(len(item_instance_meshes), 1)

        await self.__destroy(_window, _wid)

    async def test_delete_one_ref_from_selected_mesh(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)

        delete_ref_image = ui_test.find(f"{_window.title}//Frame/**/Image[*].name=='TrashCan'")

        # delete
        await delete_ref_image.click()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")
        item_instance_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")
        self.assertEqual(len(item_prims), 0)

        self.assertEqual(len(item_file_meshes), 2)
        self.assertEqual(len(item_instance_groups), 1)
        self.assertEqual(len(item_instance_meshes), 0)

        await self.__destroy(_window, _wid)

    async def test_duplicate_one_ref_from_selected_mesh(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)  # ref item + prim

        duplicate_ref_image = ui_test.find(f"{_window.title}//Frame/**/Image[*].name=='Duplicate'")

        # delete
        await duplicate_ref_image.click()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")
        item_instance_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")
        self.assertEqual(len(item_prims), 3)  # 2 ref items + 1 prim

        self.assertEqual(len(item_file_meshes), 2)
        self.assertEqual(len(item_instance_groups), 1)
        self.assertEqual(len(item_instance_meshes), 0)

        expand_icon = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='Expand'")
        self.assertEqual(len(expand_icon), 4)
        # expand
        await expand_icon[2].click()
        await ui_test.human_delay(human_delay_speed=3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 4)  # 2 ref items + 2 prims

        # undo
        omni.kit.undo.undo()
        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)  # ref item + 1 prim

        # redo
        omni.kit.undo.redo()
        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 3)  # 2 ref items + 1 prim

        await self.__destroy(_window, _wid)

    async def test_delete_one_ref_from_selected_instance(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)
        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)

        delete_ref_image = ui_test.find(f"{_window.title}//Frame/**/Image[*].name=='TrashCan'")

        # delete
        await delete_ref_image.click()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")
        item_instance_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")
        self.assertEqual(len(item_prims), 0)

        self.assertEqual(len(item_file_meshes), 2)
        self.assertEqual(len(item_instance_groups), 1)
        self.assertEqual(len(item_instance_meshes), 1)

        await self.__destroy(_window, _wid)

    async def test_append_and_delete_one_ref(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)

        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        self.assertEqual(len(item_file_meshes), 2)

        item_instances = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")
        self.assertEqual(len(item_instances), 0)

        await item_file_meshes[0].click()

        window_name = "Select a reference file"

        # The file picker window should now be opened (0 < len(widgets))
        self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))

        select_button = ui_test.find(f"{window_name}//Frame/**/Button[*].text=='Select'")
        dir_path_field = ui_test.find(f"{window_name}//Frame/**/StringField[*].identifier=='filepicker_directory_path'")

        self.assertIsNotNone(select_button)
        self.assertIsNotNone(dir_path_field)

        # It takes a while for the tree to update
        await ui_test.human_delay(50)
        asset_path = _get_test_data("usd/ingested_assets/output/good/cube.usda")
        await dir_path_field.input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(50)

        await select_button.click()
        await ui_test.human_delay()

        ignore_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )

        cancel_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNone(ignore_ingestion_button)
        self.assertIsNone(cancel_ingestion_button)

        delete_ref_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].name=='TrashCan'")

        # delete
        await delete_ref_images[1].click()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")

        self.assertEqual(len(item_prims), 2)
        self.assertEqual(len(item_file_meshes), 2)
        self.assertEqual(len(item_instance_groups), 1)

        await self.__destroy(_window, _wid)

    async def test_append_undo_redo(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)

        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        self.assertEqual(len(item_file_meshes), 2)

        item_instances = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")
        self.assertEqual(len(item_instances), 1)

        tree_view = ui_test.find(f"{_window.title}//Frame/**/TreeView[*].identifier=='LiveSelectionTreeView'")

        # test what items are selected. First prim + instance + instance group should be selected
        all_items = tree_view.widget.model.get_all_items()
        self.assertEqual(tree_view.widget.selection, [all_items[2], all_items[6], all_items[5]])

        await item_file_meshes[0].click()
        await ui_test.human_delay(human_delay_speed=10)

        window_name = "Select a reference file"

        # The file picker window should now be opened (0 < len(widgets))
        self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))

        select_button = ui_test.find(f"{window_name}//Frame/**/Button[*].text=='Select'")
        dir_path_field = ui_test.find(f"{window_name}//Frame/**/StringField[*].identifier=='filepicker_directory_path'")

        self.assertIsNotNone(select_button)
        self.assertIsNotNone(dir_path_field)

        # It takes a while for the tree to update
        await ui_test.human_delay(1)
        asset_path = _get_test_data("usd/ingested_assets/output/good/cube.usda")
        await dir_path_field.input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(1)

        await select_button.click()
        await ui_test.human_delay()

        # test what items are selected
        all_items = tree_view.widget.model.get_all_items()
        self.assertEqual(tree_view.widget.selection, [all_items[4], all_items[11], all_items[10]])
        current_selection = usd_context.get_selection().get_selected_prim_paths()
        self.assertTrue(
            current_selection[0].startswith("/RootNode/instances/inst_0AB745B8BEE1F16B_0/ref_")
            and current_selection[0].endswith("/Toto")
        )

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")

        self.assertEqual(len(item_prims), 6)
        self.assertEqual(len(item_file_meshes), 2)
        self.assertEqual(len(item_instance_groups), 1)

        # undo
        omni.kit.undo.undo()
        await ui_test.human_delay(human_delay_speed=3)

        all_items = tree_view.widget.model.get_all_items()
        self.assertEqual(tree_view.widget.selection, [all_items[2], all_items[6], all_items[5]])
        current_selection = usd_context.get_selection().get_selected_prim_paths()
        self.assertEqual(current_selection, ["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"])

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")

        self.assertEqual(len(item_prims), 2)
        self.assertEqual(len(item_file_meshes), 2)
        self.assertEqual(len(item_instance_groups), 1)

        # redo
        omni.kit.undo.redo()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")

        self.assertEqual(len(item_prims), 6)
        self.assertEqual(len(item_file_meshes), 2)
        self.assertEqual(len(item_instance_groups), 1)

        # test what items are selected
        all_items = tree_view.widget.model.get_all_items()
        self.assertEqual(tree_view.widget.selection, [all_items[4], all_items[11], all_items[10]])
        current_selection = usd_context.get_selection().get_selected_prim_paths()
        self.assertTrue(
            current_selection[0].startswith("/RootNode/instances/inst_0AB745B8BEE1F16B_0/ref_")
            and current_selection[0].endswith("/Toto")
        )

        await self.__destroy(_window, _wid)

    async def test_append_and_delete_two_stage_lights_on_mesh(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=3)
        tree_view = ui_test.find(f"{_window.title}//Frame/**/TreeView[*].identifier=='LiveSelectionTreeView'")
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)

        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        self.assertEqual(len(item_file_meshes), 2)

        await item_file_meshes[1].click()

        window_name = "Light creator"

        # The file picker window should now be opened (0 < len(widgets))
        self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))

        light_disk_button = ui_test.find(f"{window_name}//Frame/**/Button[*].name=='LightDisk'")
        light_distant_button = ui_test.find(f"{window_name}//Frame/**/Button[*].name=='LightDistant'")

        self.assertIsNotNone(light_disk_button)
        self.assertIsNotNone(light_distant_button)

        # create the light
        await light_disk_button.click()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")

        self.assertEqual(len(item_prims), 2)
        self.assertEqual(item_prims[1].widget.text, "DiskLight")
        self.assertEqual(len(item_file_meshes), 2)
        self.assertEqual(len(item_instance_groups), 2)  # instance group + live light group

        # test what items are selected
        all_items = tree_view.widget.model.get_all_items()
        self.assertEqual(tree_view.widget.selection, [all_items[5], all_items[8]])
        current_selection = usd_context.get_selection().get_selected_prim_paths()
        self.assertEqual(current_selection, ["/RootNode/instances/inst_0AB745B8BEE1F16B_0/DiskLight"])

        # we add another light
        await item_file_meshes[1].click()
        light_distant_button = ui_test.find(f"{window_name}//Frame/**/Button[*].name=='LightDistant'")
        # create the light
        await light_distant_button.click()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")
        self.assertEqual(len(item_prims), 3)
        self.assertEqual(len(item_instance_groups), 2)  # instance group + live light group

        # test what items are selected
        all_items = tree_view.widget.model.get_all_items()
        self.assertEqual(tree_view.widget.selection, [all_items[6], all_items[9]])
        current_selection = usd_context.get_selection().get_selected_prim_paths()
        self.assertEqual(current_selection, ["/RootNode/instances/inst_0AB745B8BEE1F16B_0/DistantLight"])

        # undo
        omni.kit.undo.undo()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")

        self.assertEqual(len(item_prims), 2)
        self.assertEqual(item_prims[1].widget.text, "DiskLight")
        self.assertEqual(len(item_file_meshes), 2)
        self.assertEqual(len(item_instance_groups), 2)  # instance group + live light group

        # test what items are selected
        all_items = tree_view.widget.model.get_all_items()
        self.assertEqual(tree_view.widget.selection, [all_items[5], all_items[8]])
        current_selection = usd_context.get_selection().get_selected_prim_paths()
        self.assertEqual(current_selection, ["/RootNode/instances/inst_0AB745B8BEE1F16B_0/DiskLight"])

        # redo
        omni.kit.undo.redo()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")
        self.assertEqual(len(item_prims), 3)
        self.assertEqual(len(item_instance_groups), 2)  # instance group + live light group

        # test what items are selected
        all_items = tree_view.widget.model.get_all_items()
        self.assertEqual(tree_view.widget.selection, [all_items[6], all_items[9]])
        current_selection = usd_context.get_selection().get_selected_prim_paths()
        self.assertEqual(current_selection, ["/RootNode/instances/inst_0AB745B8BEE1F16B_0/DistantLight"])

        # now remove 1 light
        delete_ref_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].name=='TrashCan'")
        self.assertEqual(len(delete_ref_images), 3)

        # delete
        await delete_ref_images[1].click()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)

        # undo
        omni.kit.undo.undo()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 3)

        # redo
        omni.kit.undo.redo()
        await ui_test.human_delay(human_delay_speed=3)

        # now remove 1 light
        delete_ref_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].name=='TrashCan'")
        self.assertEqual(len(delete_ref_images), 2)

        # delete
        await delete_ref_images[1].click()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 1)

        await self.__destroy(_window, _wid)

    async def test_select_stage_light_instances_on_mesh(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_1/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )
        await ui_test.human_delay(human_delay_speed=3)
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")

        await item_file_meshes[1].click()

        # add 2 lights
        window_name = "Light creator"
        light_disk_button = ui_test.find(f"{window_name}//Frame/**/Button[*].name=='LightDisk'")
        await light_disk_button.click()
        await ui_test.human_delay(human_delay_speed=3)
        await item_file_meshes[1].click()
        light_distant_button = ui_test.find(f"{window_name}//Frame/**/Button[*].name=='LightDistant'")
        await light_distant_button.click()
        await ui_test.human_delay(human_delay_speed=3)

        item_instance_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")
        self.assertEqual(len(item_instance_meshes), 3)

        await item_instance_meshes[0].click()
        self.assertEqual(
            usd_context.get_selection().get_selected_prim_paths(),
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/DistantLight"],
        )

        await item_instance_meshes[1].click()
        self.assertEqual(
            usd_context.get_selection().get_selected_prim_paths(),
            ["/RootNode/instances/inst_BAC90CAA733B0859_1/DistantLight"],
        )

        await item_instance_meshes[2].click()
        self.assertEqual(
            usd_context.get_selection().get_selected_prim_paths(),
            ["/RootNode/instances/inst_BAC90CAA733B0859_2/DistantLight"],
        )

        await self.__destroy(_window, _wid)

    async def test_duplicate_stage_light_on_mesh(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=3)

        duplicate_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].name=='Duplicate'")
        self.assertEqual(len(duplicate_images), 1)  # ref item

        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        self.assertEqual(len(item_file_meshes), 2)

        await item_file_meshes[1].click()

        window_name = "Light creator"

        # The file picker window should now be opened (0 < len(widgets))
        self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))

        light_disk_button = ui_test.find(f"{window_name}//Frame/**/Button[*].name=='LightDisk'")

        self.assertIsNotNone(light_disk_button)

        # create the light
        await light_disk_button.click()
        await ui_test.human_delay(human_delay_speed=3)

        duplicate_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].name=='Duplicate'")
        self.assertEqual(len(duplicate_images), 2)  # ref item + light

        await duplicate_images[1].click()
        await ui_test.human_delay(human_delay_speed=3)

        duplicate_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].name=='Duplicate'")
        self.assertEqual(len(duplicate_images), 3)  # ref item + light + dup light

        # undo
        omni.kit.undo.undo()
        await ui_test.human_delay(human_delay_speed=3)
        # The undo command clears the selection since it was deleted. Reselect the original light.
        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_0AB745B8BEE1F16B_0/DiskLight"], False
        )
        await ui_test.human_delay(human_delay_speed=3)
        duplicate_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].name=='Duplicate'")
        self.assertEqual(len(duplicate_images), 2)  # ref item + light

        # redo
        omni.kit.undo.redo()
        await ui_test.human_delay(human_delay_speed=3)
        duplicate_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].name=='Duplicate'")
        self.assertEqual(len(duplicate_images), 3)  # ref item + light + dup light

        await self.__destroy(_window, _wid)

    async def test_select_prim_instances_on_mesh(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        usd_context.get_selection().set_selected_prim_paths(
            ["/RootNode/instances/inst_BAC90CAA733B0859_1/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"], False
        )
        await ui_test.human_delay(human_delay_speed=3)

        item_instance_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_mesh'")
        self.assertEqual(len(item_instance_meshes), 3)

        await item_instance_meshes[0].click()
        self.assertEqual(
            usd_context.get_selection().get_selected_prim_paths(),
            ["/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"],
        )

        await item_instance_meshes[1].click()
        self.assertEqual(
            usd_context.get_selection().get_selected_prim_paths(),
            ["/RootNode/instances/inst_BAC90CAA733B0859_1/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"],
        )

        await item_instance_meshes[2].click()
        self.assertEqual(
            usd_context.get_selection().get_selected_prim_paths(),
            ["/RootNode/instances/inst_BAC90CAA733B0859_2/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"],
        )

        await self.__destroy(_window, _wid)

    async def test_append_and_delete_two_stage_lights_on_light(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/lights/light_9907D0B07D040077"], False)
        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")

        self.assertEqual(len(item_prims), 0)

        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        self.assertEqual(len(item_file_meshes), 1)

        await item_file_meshes[0].click()

        window_name = "Light creator"

        # The file picker window should now be opened (0 < len(widgets))
        self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))

        light_disk_button = ui_test.find(f"{window_name}//Frame/**/Button[*].name=='LightDisk'")
        light_distant_button = ui_test.find(f"{window_name}//Frame/**/Button[*].name=='LightDistant'")

        self.assertIsNotNone(light_disk_button)
        self.assertIsNotNone(light_distant_button)

        # create the light
        await light_disk_button.click()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")

        self.assertEqual(len(item_prims), 1)
        self.assertEqual(item_prims[0].widget.text, "DiskLight")
        self.assertEqual(len(item_file_meshes), 1)
        self.assertEqual(len(item_instance_groups), 2)  # instance group + live light group

        # we add another light
        await item_file_meshes[0].click()
        light_distant_button = ui_test.find(f"{window_name}//Frame/**/Button[*].name=='LightDistant'")
        # create the light
        await light_distant_button.click()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        item_instance_groups = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_instance_group'")
        self.assertEqual(len(item_prims), 2)
        self.assertEqual(len(item_instance_groups), 2)  # instance group + live light group

        # now remove 1 light
        delete_ref_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].name=='TrashCan'")
        self.assertEqual(len(delete_ref_images), 2)

        # delete
        await delete_ref_images[0].click()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")

        self.assertEqual(len(item_prims), 1)

        # now remove 1 light
        delete_ref_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].name=='TrashCan'")
        self.assertEqual(len(delete_ref_images), 1)

        # delete
        await delete_ref_images[0].click()
        await ui_test.human_delay(human_delay_speed=3)

        # test
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 0)

        await self.__destroy(_window, _wid)

    async def test_append_no_metadata_ref_ignore_ingest(self):
        await self.__ingest_wrong_asset_ignore_ingestion(
            _get_test_data("usd/ingested_assets/output/no_metadata/cube.usda")
        )

    async def test_append_hash_different_ref_ignore_ingest(self):
        await self.__ingest_wrong_asset_ignore_ingestion(
            _get_test_data("usd/ingested_assets/output/hash_different/cube.usda")
        )

    async def test_append_ingestion_failed_ref_ignore_ingest(self):
        await self.__ingest_wrong_asset_ignore_ingestion(
            _get_test_data("usd/ingested_assets/output/ingestion_failed/cube.usda")
        )

    async def __ingest_wrong_asset_ignore_ingestion(self, asset_path):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)  # we have 2 prims: reference file + the regular mesh

        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        self.assertEqual(len(item_file_meshes), 2)

        await item_file_meshes[0].click()

        window_name = "Select a reference file"

        # The file picker window should now be opened (0 < len(widgets))
        self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))

        select_button = ui_test.find(f"{window_name}//Frame/**/Button[*].text=='Select'")
        dir_path_field = ui_test.find(f"{window_name}//Frame/**/StringField[*].identifier=='filepicker_directory_path'")

        self.assertIsNotNone(select_button)
        self.assertIsNotNone(dir_path_field)

        # It takes a while for the tree to update
        await ui_test.human_delay(50)
        await dir_path_field.input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(50)

        await select_button.click()
        await ui_test.human_delay()

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
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 3)  # we have 3 prims: reference file + the regular mesh + new cube
        await self.__destroy(_window, _wid)

    async def test_append_no_metadata_ref_cancel_ingest(self):
        await self.__ingest_wrong_asset_cancel_ingestion(
            _get_test_data("usd/ingested_assets/output/no_metadata/cube.usda")
        )

    async def test_append_hash_different_ref_cancel_ingest(self):
        await self.__ingest_wrong_asset_cancel_ingestion(
            _get_test_data("usd/ingested_assets/output/hash_different/cube.usda")
        )

    async def test_append_ingestion_failed_ref_cancel_ingest(self):
        await self.__ingest_wrong_asset_cancel_ingestion(
            _get_test_data("usd/ingested_assets/output/ingestion_failed/cube.usda")
        )

    async def __ingest_wrong_asset_cancel_ingestion(self, asset_path):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)  # we have 2 prims: reference file + the regular mesh

        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        self.assertEqual(len(item_file_meshes), 2)

        await item_file_meshes[0].click()

        window_name = "Select a reference file"

        # The file picker window should now be opened (0 < len(widgets))
        self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))

        select_button = ui_test.find(f"{window_name}//Frame/**/Button[*].text=='Select'")
        dir_path_field = ui_test.find(f"{window_name}//Frame/**/StringField[*].identifier=='filepicker_directory_path'")

        self.assertIsNotNone(select_button)
        self.assertIsNotNone(dir_path_field)

        # It takes a while for the tree to update
        await ui_test.human_delay(50)
        await dir_path_field.input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(50)

        await select_button.click()
        await ui_test.human_delay(10)

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
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)  # we still have 2 prims: reference file + the regular mesh
        await self.__destroy(_window, _wid)

    async def test_append_good_ingested_ref(self):
        # setup
        _window, _wid = await self.__setup_widget()  # Keep in memory during test
        usd_context = omni.usd.get_context()

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)  # we have 2 prims: reference file + the regular mesh

        item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")
        self.assertEqual(len(item_file_meshes), 2)

        await item_file_meshes[0].click()

        window_name = "Select a reference file"

        # The file picker window should now be opened (0 < len(widgets))
        self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))

        select_button = ui_test.find(f"{window_name}//Frame/**/Button[*].text=='Select'")
        dir_path_field = ui_test.find(f"{window_name}//Frame/**/StringField[*].identifier=='filepicker_directory_path'")

        self.assertIsNotNone(select_button)
        self.assertIsNotNone(dir_path_field)

        # It takes a while for the tree to update
        await ui_test.human_delay(50)
        asset_path = _get_test_data("usd/ingested_assets/output/good/cube.usda")
        await dir_path_field.input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(50)

        await select_button.click()
        await ui_test.human_delay()

        ignore_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='confirm_button'"
        )

        cancel_ingestion_button = ui_test.find(
            f"{_constants.ASSET_NEED_INGEST_WINDOW_TITLE}//Frame/**/Button[*].name=='cancel_button'"
        )
        self.assertIsNone(ignore_ingestion_button)
        self.assertIsNone(cancel_ingestion_button)

        await ui_test.human_delay(3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        # the new added ref (with 4 sub prims) will be selected.
        self.assertEqual(len(item_prims), 6)

        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)
        await ui_test.human_delay(3)
        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 3)  # we have 3 prims: reference file + the regular mesh + new ref

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

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)  # we have 2 prims: reference file + the regular mesh

        await self.__destroy(_window, _wid)

    async def test_item_centered(self):
        # setup
        _window, _wid = await self.__setup_widget(height=300)  # Keep in memory during test
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)
        await ui_test.human_delay(human_delay_speed=10)

        number_items = 10
        for _ in range(number_items):
            item_file_meshes = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_file_mesh'")

            self.assertGreaterEqual(len(item_file_meshes), 0)
            await item_file_meshes[0].click()

            window_name = "Select a reference file"

            select_button = ui_test.find(f"{window_name}//Frame/**/Button[*].text=='Select'")
            dir_path_field = ui_test.find(
                f"{window_name}//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
            )

            # It takes a while for the tree to update
            await ui_test.human_delay(50)
            asset_path = _get_test_data("usd/ingested_assets/output/good/cube.usda")
            await dir_path_field.input(asset_path, end_key=KeyboardInput.ENTER)
            await ui_test.human_delay(50)

            await select_button.click()
            await ui_test.human_delay()

        stage = usd_context.get_stage()
        parent = stage.GetPrimAtPath("/RootNode/instances/inst_0AB745B8BEE1F16B_0")
        sub_parent = parent.GetAllChildren()[10].GetAllChildren()[0]

        usd_context.get_selection().set_selected_prim_paths([str(sub_parent.GetPath())], False)
        await ui_test.human_delay(10)

        tree_selection_scroll_frame = ui_test.find(
            f"{_window.title}//Frame/**/ScrollingFrame[*].identifier=='TreeSelectionScrollFrame'"
        )
        items = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertIsNotNone(tree_selection_scroll_frame)
        self.assertEqual(len(items), number_items + 5)  # ref has 4 prims + previous original mesh

        # 2 pixels delta. 11 because we select the sub prim of the ref. 10 is the ref
        self.assertTrue(
            tree_selection_scroll_frame.center.y - 2 < items[11].center.y < tree_selection_scroll_frame.center.y + 2
        )

        await self.__destroy(_window, _wid)
