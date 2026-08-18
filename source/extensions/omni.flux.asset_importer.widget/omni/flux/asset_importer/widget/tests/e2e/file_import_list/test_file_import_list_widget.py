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
from unittest.mock import PropertyMock, patch

import omni.kit
import omni.kit.test
import omni.usd
from carb.input import KEYBOARD_MODIFIER_FLAG_SHIFT, KeyboardEventType, KeyboardInput
from omni import ui
from omni.flux.asset_importer.widget.file_import_list import (
    FileImportListDelegate,
    FileImportListModel,
    FileImportListWidget,
)
from omni.flux.asset_importer.widget.common.ingestion_checker import DIALOG_TITLE
from omni.flux.utils.common.omni_url import OmniUrl
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows

from omni.flux.asset_importer.widget.tests.e2e.common.scan_dialog_helpers import (
    destroy_scan_dialog_owner,
    ensure_scan_dialog_input_folder,
)

_CONTEXT_NAME = ""


class DropEvent:
    payload = {}


class TestFileImportListWidget(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.context = omni.usd.get_context(_CONTEXT_NAME)
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()
        self.temp_dir = TemporaryDirectory(dir=Path.home())
        self.window = None
        self.file_import_list_widget = None

    # After running each test
    async def tearDown(self):
        try:
            if self.context.get_stage():
                await self.context.close_stage_async()
        finally:
            try:
                await destroy_scan_dialog_owner(self.file_import_list_widget, self.window)
            finally:
                self.temp_dir.cleanup()
                self.file_import_list_widget = None
                self.stage = None
                self.context = None
                self.temp_dir = None
                self.window = None

    async def __setup_widget(
        self, model: FileImportListModel | None = None, delegate: FileImportListDelegate | None = None
    ):
        await arrange_windows(topleft_window="Stage")

        self.window = ui.Window("TestFileImportListWindow", height=400, width=400)
        with self.window.frame:
            self.file_import_list_widget = FileImportListWidget(model=model, delegate=delegate)

        await ui_test.human_delay()

        return self.window

    async def test_tree_should_show_all_items_and_action_buttons(self):
        # Populate the production list model with three real files.
        model = FileImportListModel()
        delegate = FileImportListDelegate()

        base_path = Path(self.temp_dir.name)
        items = [base_path / "0.usda", base_path / "1.usda", base_path / "2.usda"]
        for item in items:
            item.touch()

        model.refresh(items)

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Query the rendered rows and list actions from the live widget.
        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        add_item = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='add_file'")
        remove_item = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='remove_file'")

        # Every source has one styled row and the expected actions are available.
        self.assertEqual(len(items), len(file_items))
        self.assertIsNotNone(add_item)
        self.assertIsNotNone(remove_item)

        for file_item_label in file_items:
            self.assertEqual(file_item_label.widget.style_type_name_override, "PropertiesPaneSectionTreeItem")

    async def test_wrong_file_should_be_red(self):
        # Render invalid files through the production list model and delegate.
        model = FileImportListModel()
        delegate = FileImportListDelegate()

        with (
            patch("omni.flux.asset_importer.widget.common.items.ImportItem.is_valid") as mock_exist,
            patch(
                "omni.flux.asset_importer.widget.listener.FileListener.WAIT_TIME", new_callable=PropertyMock
            ) as mock_wait_time,
        ):
            mock_wait_time.return_value = 0.1
            mock_exist.return_value = (False, "")

            # Feed real touched files into the model while validation reports them as invalid.
            base_path = Path(self.temp_dir.name)
            items = [base_path / "0.usda", base_path / "1.usda", base_path / "2.usda"]
            for item in items:
                item.touch()

            model.refresh(items)

            window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

            # Invalid rows use the error style emitted by the production delegate.
            file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
            self.assertEqual(len(items), len(file_item_labels))

            for file_item_label in file_item_labels:
                self.assertEqual(file_item_label.widget.style_type_name_override, "PropertiesPaneSectionTreeItemError")

    async def test_add_should_open_file_picker_and_add_item(self):
        # Populate the list and create one additional file for the picker workflow.
        model = FileImportListModel()
        delegate = FileImportListDelegate()

        base_path = Path(self.temp_dir.name)
        items = [base_path / "0.usda", base_path / "1.usda", base_path / "2.usda"]
        for item in items:
            item.touch()

        urls = [OmniUrl(item) for item in items]

        new_item = base_path / "3.usda"
        new_item.touch()

        model.refresh(urls)

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Locate the rendered rows and open the real file picker from Add.
        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        add_item = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='add_file'")

        # The initial rows and Add action must exist before picker interaction.
        self.assertEqual(len(urls), len(file_items))
        self.assertIsNotNone(add_item)

        await add_item.click()
        await ui_test.human_delay()

        # Drive the production picker to the additional fixture.
        window_name = "Select a file to import"
        import_button = ui_test.find(f"{window_name}//Frame/**/Button[*].text=='Import'")
        dir_path_field = ui_test.find(f"{window_name}//Frame/**/StringField[*].identifier=='filepicker_directory_path'")
        file_name_field = ui_test.find(f"{window_name}//Frame/**/StringField[*].style_type_name_override=='Field'")

        self.assertIsNotNone(import_button)
        self.assertIsNotNone(dir_path_field)
        self.assertIsNotNone(file_name_field)

        # Wait for the picker tree to populate before selecting the fixture.
        await ui_test.human_delay(50)
        await dir_path_field.input(str(new_item.parent.resolve()), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(50)

        await file_name_field.input(str(new_item.name), end_key=KeyboardInput.DOWN)
        await ui_test.human_delay()

        # Both picker fields now identify the exact file that will be imported.
        self.assertEqual(
            str(new_item.parent.resolve()),
            dir_path_field.model._field.model.get_value_as_string(),
        )
        self.assertEqual(str(new_item.name), file_name_field.model.get_value_as_string())

        await import_button.click()

        await ui_test.human_delay()

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")

        # Confirming the picker appends one row with the normalized selected path.
        self.assertEqual(len(urls) + 1, len(file_items))
        # Normalize paths so short (8.3) and long forms compare equal on Windows
        self.assertEqual(
            new_item.resolve().as_posix(),
            Path(file_items[-1].widget.text).resolve().as_posix(),
        )

    async def test_add_uppercase_usd_file_with_picker_should_add_item(self):
        """Add an uppercase USD file through the file picker."""
        # Setup the test
        model = FileImportListModel()
        delegate = FileImportListDelegate()

        base_path = Path(self.temp_dir.name)
        items = [base_path / "0.usda", base_path / "1.usda", base_path / "2.usda"]
        for item in items:
            item.touch()

        urls = [OmniUrl(item) for item in items]

        new_item = base_path / "3.USDA"
        new_item.touch()

        model.refresh(urls)

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Start the test
        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        add_item = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='add_file'")

        # Make sure we have the required items
        self.assertEqual(len(urls), len(file_items))
        self.assertIsNotNone(add_item)

        await add_item.click()
        await ui_test.human_delay()

        # File Picker
        window_name = "Select a file to import"
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
            str(new_item.parent.resolve()),
            dir_path_field.model._field.model.get_value_as_string(),
        )
        self.assertEqual(str(new_item.name), file_name_field.model.get_value_as_string())

        await import_button.click()

        await ui_test.human_delay()

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")

        # A new file path should be added
        self.assertEqual(len(urls) + 1, len(file_items))
        # Normalize paths so short (8.3) and long forms compare equal on Windows
        self.assertEqual(
            new_item.resolve().as_posix(),
            Path(file_items[-1].widget.text).resolve().as_posix(),
        )

    async def test_remove_should_validate_selection_and_remove_items_if_valid(self):
        # Populate the production list with three removable files.
        model = FileImportListModel()
        delegate = FileImportListDelegate()

        base_path = Path(self.temp_dir.name)
        items = [base_path / "0.usda", base_path / "1.usda", base_path / "2.usda"]
        for item in items:
            item.touch()

        model.refresh(items)

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Locate the rendered rows and Remove action that drive the workflow.
        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        remove_item = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='remove_file'")

        # All initial rows and the Remove action are present before interaction.
        self.assertEqual(len(items), len(file_items))
        self.assertIsNotNone(remove_item)

        await remove_item.click()

        # Removing without a selection leaves every row untouched.
        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(items), len(file_items))

        await file_items[0].click()
        await ui_test.human_delay()

        await remove_item.click()

        # Selecting one row makes the next removal drop exactly that row.
        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(items) - 1, len(file_items))

        await file_items[0].click()
        await ui_test.human_delay()

        await remove_item.click()

        # A second selection and removal reduces the list to its required final row.
        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(items) - 2, len(file_items))

        await file_items[0].click()
        await ui_test.human_delay()

        await remove_item.click()

        # Validation prevents removing the last required input.
        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(1, len(file_items))

    async def test_scan_folder(self):
        # Open the production scan dialog from an empty file-import list.
        model = FileImportListModel()
        delegate = FileImportListDelegate()

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Locate the scan action that starts the user workflow.
        scan_folder_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='scan_folder'")

        # The scan action is rendered before the dialog is opened.
        self.assertIsNotNone(scan_folder_button)

        await scan_folder_button.click()
        await ui_test.human_delay()

        scan_dialog_title = "Scan Directory for Input Files"
        choose_scanned_files_button = ui_test.find(
            f"{scan_dialog_title}//Frame/**/Button[*].identifier=='choose_scanned_files'"
        )
        # Select starts disabled because the dialog has not discovered any files.
        self.assertFalse(choose_scanned_files_button.widget.enabled)

        scan_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='scan_folder_button'")
        input_folder_field = ui_test.find(
            f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='input_folder_field'"
        )
        search_field = ui_test.find(f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='scan_search_field'")

        base_path = Path(self.temp_dir.name)
        asset_file = base_path / "0.usda"
        asset_file.touch()
        asset_file2 = base_path / "1.usda"
        asset_file2.touch()
        await ensure_scan_dialog_input_folder(input_folder_field, base_path)

        input_folder_text = input_folder_field.model.get_value_as_string().lower().replace("\\", "/").rstrip("/")
        self.assertEqual(str(base_path).replace("\\", "/").lower(), input_folder_text)
        self.assertTrue(scan_button.widget.enabled)

        search_field.model.set_value("0")
        await scan_button.click()
        await ui_test.human_delay(10)

        self.assertTrue(choose_scanned_files_button.widget.enabled)
        asset_name = asset_file.name
        asset_checkbox = ui_test.find(f"{scan_dialog_title}//Frame/**/CheckBox[*].name=='{asset_name}'")
        self.assertIsNotNone(asset_checkbox)
        # A matching scan result enables Select and exposes its checkbox.

        await choose_scanned_files_button.click()
        await ui_test.human_delay(10)

        self.assertEqual(1, len(model.get_item_children(None)))

    async def test_scan_folder_picker_cancel_preserves_parent_dialog(self):
        # Open the production scan dialog and populate its editable state and real scan results.
        model = FileImportListModel()
        delegate = FileImportListDelegate()
        window = await self.__setup_widget(model=model, delegate=delegate)
        await ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='scan_folder'").click()
        await ui_test.human_delay()

        scan_dialog_title = "Scan Directory for Input Files"
        input_folder = Path(self.temp_dir.name)
        (input_folder / "chair.usda").touch()
        input_folder_field = ui_test.find(
            f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='input_folder_field'"
        )
        search_field = ui_test.find(f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='scan_search_field'")
        scan_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='scan_folder_button'")
        await ensure_scan_dialog_input_folder(input_folder_field, input_folder)
        search_field.model.set_value("chair")
        await scan_button.click()
        await ui_test.human_delay(10)
        self.assertIsNotNone(ui_test.find(f"{scan_dialog_title}//Frame/**/CheckBox[*].name=='chair.usda'"))

        # Open and cancel only the nested production directory picker.
        folder_picker = ui_test.find(f"{scan_dialog_title}//Frame/**/Image[*].identifier=='select_scan_folder'")
        await ui_test.emulate_mouse_move_and_click(folder_picker.position)
        await ui_test.human_delay()
        picker_title = "Select Directory to Scan"
        picker_cancel = ui_test.find_all(f"{picker_title}//Frame/**/Button[*].text=='Cancel'")[0]
        await picker_cancel.click()
        await ui_test.human_delay()

        # The parent retains its directory, search, and result until its own Cancel action is used.
        self.assertTrue(ui_test.find(scan_dialog_title).window.visible)
        self.assertEqual(input_folder_field.model.get_value_as_string(), str(input_folder))
        self.assertEqual(search_field.model.get_value_as_string(), "chair")
        self.assertIsNotNone(ui_test.find(f"{scan_dialog_title}//Frame/**/CheckBox[*].name=='chair.usda'"))
        await ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='cancel'").click()

    async def test_scan_folder_multiple(self):
        # Open the production scan dialog for a directory containing two files.
        model = FileImportListModel()
        delegate = FileImportListDelegate()

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Locate the scan action that opens the multi-selection workflow.
        scan_folder_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='scan_folder'")

        # The scan action is rendered before dialog interaction begins.
        self.assertIsNotNone(scan_folder_button)

        await scan_folder_button.click()
        await ui_test.human_delay()

        scan_dialog_title = "Scan Directory for Input Files"
        search_field = ui_test.find(f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='scan_search_field'")

        scan_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='scan_folder_button'")
        input_folder_field = ui_test.find(
            f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='input_folder_field'"
        )
        self.assertIsNotNone(input_folder_field, "Scan dialog input folder field not found")
        base_path = Path(self.temp_dir.name)
        asset_file = base_path / "0.usda"
        asset_file.touch()
        asset_file2 = base_path / "1.usda"
        asset_file2.touch()
        # Clear the search so both directory entries appear in the result list.
        search_field.model.set_value("")
        await ensure_scan_dialog_input_folder(input_folder_field, base_path)

        await scan_button.click()
        await ui_test.human_delay(10)

        asset_name = asset_file.name
        asset_checkbox = ui_test.find(f"{scan_dialog_title}//Frame/**/CheckBox[*].name=='{asset_name}'")
        asset_name2 = asset_file2.name
        asset_checkbox2 = ui_test.find(f"{scan_dialog_title}//Frame/**/CheckBox[*].name=='{asset_name2}'")
        self.assertIsNotNone(asset_checkbox, f"CheckBox for '{asset_name}' not found after scan")
        self.assertIsNotNone(asset_checkbox2, f"CheckBox for '{asset_name2}' not found after scan")

        # Shift-select both result rows through real mouse and keyboard input.
        await ui_test.emulate_mouse_move_and_click(
            ui_test.Vec2(asset_checkbox.widget.screen_position_x - 2, asset_checkbox.widget.screen_position_y)
        )
        await ui_test.input.emulate_keyboard(
            KeyboardEventType.KEY_PRESS, KeyboardInput.LEFT_SHIFT, KEYBOARD_MODIFIER_FLAG_SHIFT
        )
        await ui_test.emulate_mouse_move_and_click(
            ui_test.Vec2(asset_checkbox2.widget.screen_position_x - 2, asset_checkbox2.widget.screen_position_y)
        )

        # Toggling one selected checkbox applies the same value to the full selection.
        await ui_test.emulate_mouse_move_and_click(asset_checkbox.position)
        self.assertEqual(asset_checkbox.model.get_value_as_bool(), asset_checkbox2.model.get_value_as_bool())

        # Re-enable both rows and confirm them into the import list.
        await ui_test.emulate_mouse_move_and_click(asset_checkbox.position)
        choose_scanned_files_button = ui_test.find(
            f"{scan_dialog_title}//Frame/**/Button[*].identifier=='choose_scanned_files'"
        )

        await choose_scanned_files_button.click()
        await ui_test.human_delay(10)

        self.assertEqual(2, len(model.get_item_children(None)))

        # Close the real dialog before leaving the scenario.
        cancel_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='cancel'")
        await cancel_button.click()

    async def test_scan_folder_empty_dir(self):
        # Open the production scan dialog without providing a directory.
        model = FileImportListModel()
        delegate = FileImportListDelegate()

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Locate the scan action that starts the empty-directory workflow.
        scan_folder_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='scan_folder'")

        # The scan action remains available even though no input directory exists.
        self.assertIsNotNone(scan_folder_button)

        await scan_folder_button.click()
        await ui_test.human_delay()

        # Scanning without a directory must leave Select disabled before and after the attempt.
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
        # Close the real dialog before leaving the scenario.
        cancel_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='cancel'")
        await cancel_button.click()

    async def test_drop_valid_files(self):
        model = FileImportListModel()
        delegate = FileImportListDelegate()

        base_path = Path(self.temp_dir.name)
        good_items = [base_path / "0.usda", base_path / "1.usda", base_path / "2.USDA"]
        for item in good_items:
            item.touch()

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Build a real drag payload and confirm the rendered list starts empty.
        widget = self.file_import_list_widget
        event = DropEvent()
        event.payload = {"paths": [str(item) for item in good_items]}

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(file_items), 0)

        # Drop supported files through the widget boundary and let the list rebuild.
        widget.on_drag_drop_external(event)
        await ui_test.human_delay()

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(file_items), len(good_items))

    async def test_drop_invalid_files(self):
        # Mix supported and unsupported files in one external drag payload.
        model = FileImportListModel()
        delegate = FileImportListDelegate()

        base_path = Path(self.temp_dir.name)
        good_items = [base_path / "1.usda", base_path / "2.FBX", base_path / "3.USD"]
        bad_items = [base_path / "4.nogood", base_path / "5.INVALID", base_path / "extensionless"]
        for item in good_items:
            item.touch()
        for item in bad_items:
            item.touch()
        all_items = [str(item) for item in good_items] + [str(item) for item in bad_items]

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Confirm the rendered list starts empty before the mixed drop.
        widget = self.file_import_list_widget
        event = DropEvent()
        event.payload = {"paths": all_items}

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(file_items), 0)

        # Drop the mixed payload through the widget boundary.
        try:
            widget.on_drag_drop_external(event)
            await ui_test.human_delay()

            file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
            # Supported files become rows while rejected files produce the user-facing error dialog.
            self.assertEqual(len(file_items), len(good_items))
            self.assertIsNotNone(ui_test.find(DIALOG_TITLE))
        finally:
            for button in ui_test.find_all(
                f"{DIALOG_TITLE}//Frame/**/Button[*].identifier=='ingestion_error_ok_button'"
            ):
                await button.click()
            await ui_test.human_delay()

    async def test_drop_directory(self):
        # Build a drag payload containing directories instead of importable files.
        model = FileImportListModel()
        delegate = FileImportListDelegate()

        base_path = Path(self.temp_dir.name)
        subdir1 = base_path / "sub1"
        subdir2 = base_path / "sub2"
        subdir1.mkdir(parents=True)
        subdir2.mkdir(parents=True)
        items = [subdir1, subdir2]

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Confirm the rendered list starts empty before the invalid drop.
        widget = self.file_import_list_widget
        event = DropEvent()
        event.payload = {"paths": items}

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(file_items), 0)

        # Drop directories through the real widget while suppressing only the unrelated error-dialog callback.
        with patch("omni.flux.asset_importer.widget.file_import_list.widget._file_validation_failed_callback"):
            widget.on_drag_drop_external(event)
            await ui_test.human_delay()

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        # Directory payloads never become file-import rows.
        self.assertEqual(len(file_items), 0)
