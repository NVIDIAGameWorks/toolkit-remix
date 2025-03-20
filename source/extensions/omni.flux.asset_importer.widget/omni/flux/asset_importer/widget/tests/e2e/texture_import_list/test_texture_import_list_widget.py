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

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
from unittest.mock import Mock, PropertyMock, patch

import omni.kit
import omni.kit.test
import omni.usd
from carb.input import KEYBOARD_MODIFIER_FLAG_SHIFT, KeyboardEventType, KeyboardInput
from omni import ui
from omni.flux.asset_importer.widget.texture_import_list import (
    TextureImportListDelegate,
    TextureImportListModel,
    TextureImportListWidget,
    TextureTypes,
)
from omni.flux.utils.common.omni_url import OmniUrl
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows


class DropEvent:
    payload = {}


class TestTextureImportListWidget(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()
        self.temp_dir = TemporaryDirectory()
        self.window = None

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.temp_dir.cleanup()
        self.stage = None
        self.temp_dir = None
        if self.window:
            self.window.destroy()
        self.window = None

    async def __setup_widget(
        self, model: Optional[TextureImportListModel] = None, delegate: Optional[TextureImportListDelegate] = None
    ):
        await arrange_windows(topleft_window="Stage")

        self.window = ui.Window("TestTextureImportListWindow", height=400, width=800)
        with self.window.frame:
            self.texture_import_list_widget = TextureImportListWidget(model=model, delegate=delegate)

        await ui_test.human_delay()

        return self.window

    async def __setup_input_files(self, model):
        base_path = Path(self.temp_dir.name)
        items = [
            (base_path / "albedo.png", TextureTypes.DIFFUSE),
            (base_path / "metallic.png", TextureTypes.METALLIC),
            (base_path / "normal_gl.png", TextureTypes.NORMAL_OGL),
        ]

        for item_path, _ in items:
            item_path.touch()

        url_items = [(OmniUrl(item_path), item_type) for item_path, item_type in items]

        model.refresh(url_items)

        return url_items

    async def test_tree_should_show_all_items_and_action_buttons(self):
        # Setup the test
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        items = await self.__setup_input_files(model)
        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Start the test
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        add_item = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='add_file'")
        remove_item = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='remove_file'")
        scan_folder = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='scan_folder'")

        # Make sure everything is rendered correctly
        self.assertEqual(len(items), len(file_item_labels))
        self.assertEqual(len(items), len(file_item_types))
        self.assertIsNotNone(add_item)
        self.assertIsNotNone(remove_item)
        self.assertIsNotNone(scan_folder)

    async def test_tree_change_type_should_trigger_event(self):
        # Setup the test
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        callback_mock = Mock()
        _ = model.subscribe_texture_type_changed(callback_mock)

        items = await self.__setup_input_files(model)
        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Start the test
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")

        # Make sure we have the required items
        self.assertEqual(len(items), len(file_item_labels))
        self.assertEqual(len(items), len(file_item_types))

        for file_item_label in file_item_labels:
            self.assertEqual(file_item_label.widget.style_type_name_override, "PropertiesPaneSectionTreeItem")

        # TODO Feature OM-93179: There is currently no way to select ComboBox items in automated UI tests.
        # file_type_model = file_item_types[0].model.get_item_value_model(None, 0)
        # file_type_model.set_value(0)

        # self.assertEqual(1, callback_mock.call_count)

    async def test_wrong_file_should_be_red(self):
        # Arrange
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        with (
            patch("omni.flux.asset_importer.widget.common.items.ImportItem.is_valid") as mock_exist,
            patch(
                "omni.flux.asset_importer.widget.listener.FileListener.WAIT_TIME", new_callable=PropertyMock
            ) as mock_wait_time,
        ):
            mock_wait_time.return_value = 0.1
            mock_exist.return_value = (False, "")

            # Act
            items = await self.__setup_input_files(model)
            window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

            # Asset
            file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
            file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")

            self.assertEqual(len(items), len(file_item_labels))
            self.assertEqual(len(items), len(file_item_types))

            for file_item_label in file_item_labels:
                self.assertEqual(file_item_label.widget.style_type_name_override, "PropertiesPaneSectionTreeItemError")

    async def test_add_should_open_file_picker_and_add_item(self):
        # Setup the test
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        new_item = Path(self.temp_dir.name) / "roughness.png"
        new_item.touch()

        items = await self.__setup_input_files(model)
        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Start the test
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        add_item = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='add_file'")

        # Make sure we have the required items
        self.assertEqual(len(items), len(file_item_labels))
        self.assertEqual(len(items), len(file_item_types))
        self.assertIsNotNone(add_item)

        await add_item.click()
        await ui_test.human_delay()
        await omni.kit.app.get_app().next_update_async()

        # File Picker
        window_name = "Select a texture to import"
        import_button = ui_test.find(f"{window_name}//Frame/**/Button[*].text=='Import'")
        dir_path_field = ui_test.find(f"{window_name}//Frame/**/StringField[*].identifier=='filepicker_directory_path'")
        file_name_field = ui_test.find(f"{window_name}//Frame/**/StringField[*].style_type_name_override=='Field'")

        self.assertIsNotNone(import_button)
        self.assertIsNotNone(dir_path_field)
        self.assertIsNotNone(file_name_field)

        # It takes a while for the tree to update
        await ui_test.human_delay(50)
        await dir_path_field.input(str(new_item.parent.resolve()), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(50)

        await file_name_field.input(str(new_item.name), end_key=KeyboardInput.DOWN)
        await ui_test.human_delay()

        # Make sure we are selecting the right file
        self.assertEqual(
            str(new_item.parent.resolve()), dir_path_field.model._field.model.get_value_as_string()  # noqa PLW0212
        )
        self.assertEqual(str(new_item.name), file_name_field.model.get_value_as_string())

        await import_button.click()

        await ui_test.human_delay()

        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")

        # A new file path should be added
        self.assertEqual(len(items) + 1, len(file_item_labels))
        self.assertEqual(len(items) + 1, len(file_item_types))
        self.assertEqual(new_item.resolve().name, Path(file_item_labels[-1].widget.text).as_posix())

    async def test_remove_should_validate_selection_and_remove_items_if_valid(self):
        # Setup the test
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        items = await self.__setup_input_files(model)
        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Start the test
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        remove_item = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='remove_file'")

        # Make sure everything is rendered correctly
        self.assertEqual(len(items), len(file_item_labels))
        self.assertEqual(len(items), len(file_item_types))
        self.assertIsNotNone(remove_item)

        await remove_item.click()

        # Should remove nothing
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        self.assertEqual(len(items), len(file_item_labels))
        self.assertEqual(len(items), len(file_item_types))

        await file_item_labels[0].click()
        await ui_test.human_delay()

        await remove_item.click()

        # Should remove the first item
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        self.assertEqual(len(items) - 1, len(file_item_labels))
        self.assertEqual(len(items) - 1, len(file_item_types))

        await file_item_labels[0].click()
        await ui_test.human_delay()

        await remove_item.click()

        # Should remove the second item
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        self.assertEqual(len(items) - 2, len(file_item_labels))
        self.assertEqual(len(items) - 2, len(file_item_types))

        await file_item_labels[0].click()
        await ui_test.human_delay()

        await remove_item.click()

        # Should do nothing as the validation should not allow 0 items to be left
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        self.assertEqual(1, len(file_item_labels))
        self.assertEqual(1, len(file_item_types))

    async def test_scan_folder(self):
        # Setup the test
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Start the test
        scan_folder_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='scan_folder'")

        # Make sure everything is rendered correctly
        self.assertIsNotNone(scan_folder_button)

        await scan_folder_button.click()
        await ui_test.human_delay()

        scan_dialog_title = "Scan Directory for Input Files"
        select_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Image[*].identifier=='select_scan_folder'")
        choose_scanned_files_button = ui_test.find(
            f"{scan_dialog_title}//Frame/**/Button[*].identifier=='choose_scanned_files'"
        )
        # The 'Select' button should be disabled on creation
        self.assertFalse(choose_scanned_files_button.widget.enabled)

        scan_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='scan_folder_button'")
        input_folder_field = ui_test.find(
            f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='input_folder_field'"
        )
        search_field = ui_test.find(f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='scan_search_field'")

        await select_button.click()
        await ui_test.human_delay(50)
        file_browser_path = ui_test.find(
            "Select Directory to Scan//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
        )
        choose_file_button = ui_test.find("Select Directory to Scan//Frame/**/Button[*].text=='Select'")
        base_path = Path(self.temp_dir.name)
        normal = base_path / "normal_gl.png"
        normal.touch()
        albedo = base_path / "albedo.png"
        albedo.touch()
        await file_browser_path.input(str(base_path), end_key=KeyboardInput.ENTER)
        await choose_file_button.click()
        await ui_test.human_delay(10)

        input_folder_text = input_folder_field.model.get_value_as_string().lower()
        self.assertEqual(str(base_path).replace("\\", "/").lower(), input_folder_text[:-1])

        search_field.model.set_value("normal")
        await scan_button.click()
        await ui_test.human_delay(10)

        normal_name = normal.name
        normal_checkbox = ui_test.find(f"{scan_dialog_title}//Frame/**/CheckBox[*].name=='{normal_name}'")
        self.assertIsNotNone(normal_checkbox)
        # The 'Select' button should now be enabled, since there are now items to add to the queue.
        self.assertTrue(choose_scanned_files_button.widget.enabled)

        await choose_scanned_files_button.click()
        await ui_test.human_delay(10)

        self.assertEqual(1, len(model.get_item_children(None)))

    async def test_scan_folder_multiple(self):
        # Setup the test
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Start the test
        scan_folder_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='scan_folder'")

        # Make sure everything is rendered correctly
        self.assertIsNotNone(scan_folder_button)

        await scan_folder_button.click()
        await ui_test.human_delay()

        scan_dialog_title = "Scan Directory for Input Files"
        select_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Image[*].identifier=='select_scan_folder'")
        search_field = ui_test.find(f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='scan_search_field'")

        scan_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='scan_folder_button'")
        await select_button.click()
        await ui_test.human_delay(50)
        file_browser_path = ui_test.find(
            "Select Directory to Scan//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
        )
        choose_file_button = ui_test.find("Select Directory to Scan//Frame/**/Button[*].text=='Select'")
        base_path = Path(self.temp_dir.name)
        normal = base_path / "normal_gl.png"
        normal.touch()
        albedo = base_path / "albedo.png"
        albedo.touch()
        # Making sure the search field is empty, so all items will be found.
        search_field.model.set_value("")
        await file_browser_path.input(str(base_path), end_key=KeyboardInput.ENTER)
        await choose_file_button.click()
        await ui_test.human_delay(10)

        await scan_button.click()
        await ui_test.human_delay(10)

        normal_name = normal.name
        normal_checkbox = ui_test.find(f"{scan_dialog_title}//Frame/**/CheckBox[*].name=='{normal_name}'")
        albedo_name = albedo.name
        albedo_checkbox = ui_test.find(f"{scan_dialog_title}//Frame/**/CheckBox[*].name=='{albedo_name}'")

        await ui_test.emulate_mouse_move_and_click(
            ui_test.Vec2(normal_checkbox.widget.screen_position_x - 2, normal_checkbox.widget.screen_position_y)
        )
        await ui_test.input.emulate_keyboard(
            KeyboardEventType.KEY_PRESS, KeyboardInput.LEFT_SHIFT, KEYBOARD_MODIFIER_FLAG_SHIFT
        )
        await ui_test.emulate_mouse_move_and_click(
            ui_test.Vec2(albedo_checkbox.widget.screen_position_x - 2, albedo_checkbox.widget.screen_position_y)
        )

        # Since both items are selected, affecting the checkbox for one will update the other.
        await ui_test.emulate_mouse_move_and_click(normal_checkbox.position)
        self.assertEqual(normal_checkbox.model.get_value_as_bool(), albedo_checkbox.model.get_value_as_bool())

        # Set them back to checked and send them to the queue
        await ui_test.emulate_mouse_move_and_click(normal_checkbox.position)
        choose_scanned_files_button = ui_test.find(
            f"{scan_dialog_title}//Frame/**/Button[*].identifier=='choose_scanned_files'"
        )

        await choose_scanned_files_button.click()
        await ui_test.human_delay(10)

        self.assertEqual(2, len(model.get_item_children(None)))

        # Disable the dialog
        cancel_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='cancel'")
        await cancel_button.click()

    async def test_scan_folder_empty_dir(self):
        # Setup the test
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Start the test
        scan_folder_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='scan_folder'")

        # Make sure everything is rendered correctly
        self.assertIsNotNone(scan_folder_button)

        await scan_folder_button.click()
        await ui_test.human_delay()

        # Hitting the scan button without a directory should do nothing, so make sure that the 'Select' button
        # should be disabled both before and after hitting the 'Scan' button.
        scan_dialog_title = "Scan Directory for Input Files"
        scan_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='scan_folder_button'")
        choose_scanned_files_button = ui_test.find(
            f"{scan_dialog_title}//Frame/**/Button[*].identifier=='choose_scanned_files'"
        )
        input_folder_field = ui_test.find(
            f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='input_folder_field'"
        )
        input_folder_field.model.set_value("")
        self.assertFalse(choose_scanned_files_button.widget.enabled)

        await scan_button.click()
        await ui_test.human_delay()

        self.assertFalse(choose_scanned_files_button.widget.enabled)
        # Disable the dialog
        cancel_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='cancel'")
        await cancel_button.click()

    async def test_drop_valid_files(self):
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        base_path = Path(self.temp_dir.name)
        good_items = [base_path / "0.jpg", base_path / "1.jpg", base_path / "2.JPG"]
        for item in good_items:
            item.touch()

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Start the test
        widget = self.texture_import_list_widget
        event = DropEvent()
        event.payload = {"paths": [str(item) for item in good_items]}

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(file_items), 0)

        # Simulate dropping files on the widget
        widget._on_drag_drop_external(event)  # noqa PLW0212 protected-access
        await ui_test.human_delay(70)

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(file_items), len(good_items))

    async def test_drop_invalid_files(self):
        # Setup the test
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        base_path = Path(self.temp_dir.name)
        good_items = [base_path / "1.jpg", base_path / "2.usd", base_path / "3.USD"]
        bad_items = [base_path / "3.nogood", base_path / "4.INVALID"]
        for item in good_items:
            item.touch()
        for item in bad_items:
            item.touch()
        all_items = [str(item) for item in good_items] + [str(item) for item in bad_items]

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Start the test
        widget = self.texture_import_list_widget
        event = DropEvent()
        event.payload = {"paths": all_items}

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(file_items), 0)

        # Simulate dropping files on the widget The failed drop will raise an error dialog that we don't need here.
        with patch("omni.flux.asset_importer.widget.texture_import_list.widget._texture_validation_failed_callback"):
            widget._on_drag_drop_external(event)  # noqa PLW0212 protected-access
            await ui_test.human_delay()

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        # Only the good items should be added
        self.assertEqual(len(file_items), len(good_items))

    async def test_drop_directory(self):
        # Setup the test
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        base_path = Path(self.temp_dir.name)
        subdir1 = base_path / "sub1"
        subdir2 = base_path / "sub2"
        subdir1.mkdir(parents=True)
        subdir2.mkdir(parents=True)
        items = [subdir1, subdir2]

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Start the test
        widget = self.texture_import_list_widget
        event = DropEvent()
        event.payload = {"paths": items}

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(file_items), 0)

        # Simulate dropping files on the widget The failed drop will raise an error dialog that we don't need here.
        with patch("omni.flux.asset_importer.widget.texture_import_list.widget._texture_validation_failed_callback"):
            widget._on_drag_drop_external(event)  # noqa PLW0212 protected-access
            await ui_test.human_delay()

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        # Nothing should have been added
        self.assertEqual(len(file_items), 0)
