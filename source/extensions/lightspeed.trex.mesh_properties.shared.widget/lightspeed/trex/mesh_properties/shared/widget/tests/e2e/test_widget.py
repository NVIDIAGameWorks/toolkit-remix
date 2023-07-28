"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb.input
import omni.ui as ui
import omni.usd
from carb.input import KeyboardInput
from lightspeed.common import constants as _constants
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.mesh_properties.shared.widget import SetupUI as _MeshPropertiesWidget
from lightspeed.trex.selection_tree.shared.widget import SetupUI as _SelectionTreeWidget
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, open_stage, wait_stage_loading


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

    async def test_select_one_prim_mesh(self):
        # setup
        _window, _selection_wid, _mesh_property_wid = await self.__setup_widget()  # Keep in memory during test

        # select
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)

        # the frame None is visible
        frame_none = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        frame_mesh_prim = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")
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
        frame_none = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        frame_mesh_prim = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")
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
        frame_none = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_none'")
        frame_mesh_ref = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        frame_mesh_prim = ui_test.find(f"{_window.title}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")
        self.assertFalse(frame_none.widget.visible)
        self.assertTrue(frame_mesh_ref.widget.visible)
        self.assertFalse(frame_mesh_prim.widget.visible)

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

        asset_path = _get_test_data("usd/ingested_assets/output/good/cube.usda")

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
        asset_path = _get_test_data("usd/ingested_assets/output/good/cube.usda")
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
            _get_test_data("usd/ingested_assets/output/hash_different/cube.usda")
        )

    async def test_replace_mesh_ref_using_string_field_bad_ingested_failed_asset_cancel(self):
        await self.__replace_mesh_ref_using_string_field_bad_ingested_asset_cancel(
            _get_test_data("usd/ingested_assets/output/ingestion_failed/cube.usda")
        )

    async def test_replace_mesh_ref_using_string_field_bad_ingested_no_metadata_asset_cancel(self):
        await self.__replace_mesh_ref_using_string_field_bad_ingested_asset_cancel(
            _get_test_data("usd/ingested_assets/output/no_metadata/cube.usda")
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
            _get_test_data("usd/ingested_assets/output/hash_different/cube.usda")
        )

    async def test_replace_mesh_ref_using_string_field_bad_ingested_failed_asset_ignore(self):
        await self.__replace_mesh_ref_using_string_field_bad_ingested_asset_ignore(
            _get_test_data("usd/ingested_assets/output/ingestion_failed/cube.usda")
        )

    async def test_replace_mesh_ref_using_string_field_bad_ingested_no_metadata_asset_ignore(self):
        await self.__replace_mesh_ref_using_string_field_bad_ingested_asset_ignore(
            _get_test_data("usd/ingested_assets/output/no_metadata/cube.usda")
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
