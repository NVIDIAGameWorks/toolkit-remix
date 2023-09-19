"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
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

    async def __setup_widget(self):
        window = ui.Window("TestSelectionTreeUI", height=800, width=400)
        _SetupUI.DEFAULT_TREE_FRAME_HEIGHT = 700
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

    async def test_delete_one_ref(self):
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
        self.assertEqual(len(item_prims), 0)
        self.assertEqual(len(item_file_meshes), 2)
        self.assertEqual(len(item_instance_groups), 1)

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
        await ui_test.human_delay(1)
        await dir_path_field.input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(1)

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
        await ui_test.human_delay(1)
        await dir_path_field.input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(1)

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
        await ui_test.human_delay(1)
        asset_path = _get_test_data("usd/ingested_assets/output/good/cube.usda")
        await dir_path_field.input(asset_path, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(1)

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
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/instances/inst_0AB745B8BEE1F16B_0/mesh"], False)
        await ui_test.human_delay(3)

        item_prims = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertEqual(len(item_prims), 2)  # we have 2 prims: reference file + the regular mesh

        await self.__destroy(_window, _wid)
