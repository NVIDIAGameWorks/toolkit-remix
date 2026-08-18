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
from omni.flux.asset_importer.widget.texture_import_list import (
    TextureImportListDelegate,
    TextureImportListModel,
    TextureImportListWidget,
    TextureTypes,
)
from omni.flux.asset_importer.widget.common.ingestion_checker import DIALOG_TITLE
from omni.flux.utils.common.omni_url import OmniUrl
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows

from omni.flux.asset_importer.widget.tests.e2e.common.scan_dialog_helpers import (
    destroy_scan_dialog_owner,
    ensure_scan_dialog_input_folder,
    replace_field_text,
)

_CONTEXT_NAME = ""


class DropEvent:
    payload = {}


class TestTextureImportListWidget(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.context = omni.usd.get_context(_CONTEXT_NAME)
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()
        self.temp_dir = TemporaryDirectory(dir=Path.home())
        self.window = None
        self.texture_import_list_widget = None

    # After running each test
    async def tearDown(self):
        try:
            if self.context.get_stage():
                await self.context.close_stage_async()
        finally:
            try:
                await destroy_scan_dialog_owner(self.texture_import_list_widget, self.window)
            finally:
                self.temp_dir.cleanup()
                self.stage = None
                self.context = None
                self.temp_dir = None
                self.texture_import_list_widget = None
                self.window = None

    async def __setup_widget(
        self, model: TextureImportListModel | None = None, delegate: TextureImportListDelegate | None = None
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
        # Populate the production texture list with real image files.
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        items = await self.__setup_input_files(model)
        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Query the rendered rows and list actions from the live widget.
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        add_item = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='add_file'")
        remove_item = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='remove_file'")
        scan_folder = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='scan_folder'")

        # Every texture has one styled row and the expected actions are available.
        self.assertEqual(len(items), len(file_item_labels))
        self.assertEqual(len(items), len(file_item_types))
        self.assertIsNotNone(add_item)
        self.assertIsNotNone(remove_item)
        self.assertIsNotNone(scan_folder)

    async def test_file_selection_should_not_render_normal_map_convention(self):
        # Arrange
        window = await self.__setup_widget()

        # Act
        convention_label = ui_test.find(f"{window.title}//Frame/**/Label[*].identifier=='normal_map_convention_label'")
        convention_field = ui_test.find(f"{window.title}//Frame/**/ComboBox[*].identifier=='normals_type_combobox'")

        # Assert
        self.assertIsNone(convention_label)
        self.assertIsNone(convention_field)

    async def test_wrong_file_should_be_red(self):
        # Render invalid textures through the production list model and delegate.
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

            # Feed real texture files into the model while validation reports them as invalid.
            items = await self.__setup_input_files(model)
            window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

            # Invalid rows use the error style emitted by the production delegate.
            file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
            file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")

            self.assertEqual(len(items), len(file_item_labels))
            self.assertEqual(len(items), len(file_item_types))

            for file_item_label in file_item_labels:
                self.assertEqual(file_item_label.widget.style_type_name_override, "PropertiesPaneSectionTreeItemError")

    async def test_add_should_open_file_picker_and_add_item(self):
        # Populate the list and create one additional texture for the picker workflow.
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        new_item = Path(self.temp_dir.name) / "roughness.png"
        new_item.touch()

        items = await self.__setup_input_files(model)
        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Locate the rendered rows and open the real file picker from Add.
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        add_item = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='add_file'")

        # The initial rows and Add action must exist before picker interaction.
        self.assertEqual(len(items), len(file_item_labels))
        self.assertEqual(len(items), len(file_item_types))
        self.assertIsNotNone(add_item)

        await add_item.click()
        await ui_test.human_delay()
        await omni.kit.app.get_app().next_update_async()

        # Drive the production picker to the additional texture fixture.
        window_name = "Select a texture to import"
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

        # Both picker fields now identify the exact texture that will be imported.
        self.assertEqual(
            str(new_item.parent.resolve()),
            dir_path_field.model._field.model.get_value_as_string(),
        )
        self.assertEqual(str(new_item.name), file_name_field.model.get_value_as_string())

        await import_button.click()

        await ui_test.human_delay()

        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")

        # Confirming the picker appends one row for the selected texture.
        self.assertEqual(len(items) + 1, len(file_item_labels))
        self.assertEqual(len(items) + 1, len(file_item_types))
        self.assertEqual(new_item.resolve().name, Path(file_item_labels[-1].widget.text).as_posix())

    async def test_remove_should_validate_selection_and_remove_items_if_valid(self):
        # Populate the production list with three removable textures.
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        items = await self.__setup_input_files(model)
        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Locate the rendered rows and Remove action that drive the workflow.
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        remove_item = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='remove_file'")

        # All initial rows and the Remove action are present before interaction.
        self.assertEqual(len(items), len(file_item_labels))
        self.assertEqual(len(items), len(file_item_types))
        self.assertIsNotNone(remove_item)

        await remove_item.click()

        # Removing without a selection leaves every row untouched.
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        self.assertEqual(len(items), len(file_item_labels))
        self.assertEqual(len(items), len(file_item_types))

        await file_item_labels[0].click()
        await ui_test.human_delay()

        await remove_item.click()

        # Selecting one row makes the next removal drop exactly that row.
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        self.assertEqual(len(items) - 1, len(file_item_labels))
        self.assertEqual(len(items) - 1, len(file_item_types))

        await file_item_labels[0].click()
        await ui_test.human_delay()

        await remove_item.click()

        # A second selection and removal reduces the list to its required final row.
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        self.assertEqual(len(items) - 2, len(file_item_labels))
        self.assertEqual(len(items) - 2, len(file_item_types))

        await file_item_labels[0].click()
        await ui_test.human_delay()

        await remove_item.click()

        # Validation prevents removing the last required texture.
        file_item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        file_item_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")
        self.assertEqual(1, len(file_item_labels))
        self.assertEqual(1, len(file_item_types))

    async def test_scan_folder(self):
        # Open the production scan dialog from an empty texture-import list.
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

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
        # Select starts disabled because the dialog has not discovered any textures.
        self.assertFalse(choose_scanned_files_button.widget.enabled)

        scan_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='scan_folder_button'")
        input_folder_field = ui_test.find(
            f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='input_folder_field'"
        )
        search_field = ui_test.find(f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='scan_search_field'")

        base_path = Path(self.temp_dir.name)
        normal = base_path / "normal_gl.PNG"
        normal.touch()
        albedo = base_path / "albedo.png"
        albedo.touch()
        await ensure_scan_dialog_input_folder(input_folder_field, base_path)

        input_folder_text = input_folder_field.model.get_value_as_string().lower().replace("\\", "/").rstrip("/")
        self.assertEqual(str(base_path).replace("\\", "/").lower(), input_folder_text)

        search_field.model.set_value("normal")
        await scan_button.click()
        await ui_test.human_delay(10)

        normal_name = normal.name
        normal_checkbox = ui_test.find(f"{scan_dialog_title}//Frame/**/CheckBox[*].name=='{normal_name}'")
        self.assertIsNotNone(normal_checkbox)
        # A matching scan result enables Select and exposes its checkbox.
        self.assertTrue(choose_scanned_files_button.widget.enabled)

        await choose_scanned_files_button.click()
        await ui_test.human_delay(10)

        self.assertEqual(1, len(model.get_item_children(None)))

    async def test_scan_folder_multiple(self):
        # Open the production scan dialog for a directory containing two textures.
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

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
        normal = base_path / "normal_gl.png"
        normal.touch()
        albedo = base_path / "albedo.png"
        albedo.touch()
        # Clear the search so both directory entries appear in the result list.
        search_field.model.set_value("")
        await ensure_scan_dialog_input_folder(input_folder_field, base_path)

        await scan_button.click()
        await ui_test.human_delay(10)

        normal_name = normal.name
        normal_checkbox = ui_test.find(f"{scan_dialog_title}//Frame/**/CheckBox[*].name=='{normal_name}'")
        albedo_name = albedo.name
        albedo_checkbox = ui_test.find(f"{scan_dialog_title}//Frame/**/CheckBox[*].name=='{albedo_name}'")
        self.assertIsNotNone(normal_checkbox, f"CheckBox for '{normal_name}' not found after scan")
        self.assertIsNotNone(albedo_checkbox, f"CheckBox for '{albedo_name}' not found after scan")
        choose_scanned_files_button = ui_test.find(
            f"{scan_dialog_title}//Frame/**/Button[*].identifier=='choose_scanned_files'"
        )

        # Leave the second result unchecked, select only the first row, and prove
        # checking that selected row enables confirmation from the complete state.
        await ui_test.emulate_mouse_move_and_click(albedo_checkbox.position)
        await ui_test.emulate_mouse_move_and_click(
            ui_test.Vec2(normal_checkbox.widget.screen_position_x - 2, normal_checkbox.widget.screen_position_y)
        )
        await ui_test.emulate_mouse_move_and_click(normal_checkbox.position)
        self.assertFalse(choose_scanned_files_button.widget.enabled)
        await ui_test.emulate_mouse_move_and_click(normal_checkbox.position)
        self.assertTrue(choose_scanned_files_button.widget.enabled)

        await ui_test.emulate_mouse_move_and_click(
            ui_test.Vec2(normal_checkbox.widget.screen_position_x - 2, normal_checkbox.widget.screen_position_y)
        )
        await ui_test.input.emulate_keyboard(
            KeyboardEventType.KEY_PRESS, KeyboardInput.LEFT_SHIFT, KEYBOARD_MODIFIER_FLAG_SHIFT
        )
        await ui_test.emulate_mouse_move_and_click(
            ui_test.Vec2(albedo_checkbox.widget.screen_position_x - 2, albedo_checkbox.widget.screen_position_y)
        )

        # Toggling one selected checkbox applies the same value to the full selection.
        await ui_test.emulate_mouse_move_and_click(normal_checkbox.position)
        self.assertEqual(normal_checkbox.model.get_value_as_bool(), albedo_checkbox.model.get_value_as_bool())
        self.assertFalse(choose_scanned_files_button.widget.enabled)

        # Re-enable both rows and confirm them into the texture list.
        await ui_test.emulate_mouse_move_and_click(normal_checkbox.position)
        self.assertTrue(choose_scanned_files_button.widget.enabled)

        await choose_scanned_files_button.click()
        await ui_test.human_delay(10)

        self.assertEqual(2, len(model.get_item_children(None)))

        # Close the real dialog before leaving the scenario.
        cancel_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='cancel'")
        await cancel_button.click()

    async def test_scan_folder_empty_dir(self):
        # Open the production scan dialog without providing a directory.
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

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

    async def test_scan_folder_marks_only_missing_directory_after_correcting_invalid_search(self):
        """A missing directory clears stale search errors and marks only the directory field."""
        # Reproduce a search error, then correct it while making the directory invalid.
        window = await self.__setup_widget(model=TextureImportListModel(), delegate=TextureImportListDelegate())
        open_scan_dialog_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='scan_folder'")
        await open_scan_dialog_button.click()
        await ui_test.human_delay()

        scan_dialog_title = "Scan Directory for Input Files"
        input_folder = Path(self.temp_dir.name)
        input_folder_field = ui_test.find(
            f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='input_folder_field'"
        )
        await ensure_scan_dialog_input_folder(input_folder_field, input_folder)
        search_field = ui_test.find(f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='scan_search_field'")
        scan_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='scan_folder_button'")
        await replace_field_text(search_field, "[")
        await scan_button.click()
        await ui_test.human_delay()
        self.assertEqual("FieldError", search_field.widget.style_type_name_override)

        input_folder_field = ui_test.find(
            f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='input_folder_field'"
        )
        search_field = ui_test.find(f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='scan_search_field'")
        scan_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='scan_folder_button'")
        search_field.model.set_value("valid")
        await ui_test.human_delay()
        self.assertEqual("valid", search_field.model.get_value_as_string())
        missing_folder = input_folder / "missing"
        input_folder_field.model.set_value(str(missing_folder))
        await ui_test.human_delay()
        self.assertEqual(str(missing_folder), input_folder_field.model.get_value_as_string())
        choose_scanned_files_button = ui_test.find(
            f"{scan_dialog_title}//Frame/**/Button[*].identifier=='choose_scanned_files'"
        )

        # Rescan after the correction so only the newly invalid directory remains highlighted.
        await scan_button.click()
        await ui_test.human_delay()

        input_folder_field = ui_test.find(
            f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='input_folder_field'"
        )
        search_field = ui_test.find(f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='scan_search_field'")
        self.assertEqual("FieldError", input_folder_field.widget.style_type_name_override)
        self.assertEqual(
            "Select a directory that exists and can be read.",
            input_folder_field.widget.tooltip,
        )
        self.assertEqual("Field", search_field.widget.style_type_name_override)
        self.assertNotEqual(
            "Enter a valid regular expression or clear the Search field.",
            search_field.widget.tooltip,
        )
        self.assertFalse(choose_scanned_files_button.widget.enabled)
        self.assertTrue(scan_button.widget.enabled)

    async def test_scan_folder_marks_only_invalid_search_after_correcting_missing_directory(self):
        """An invalid search clears stale directory errors and marks only the search field."""
        # Reproduce a directory error, then correct it while making the search invalid.
        window = await self.__setup_widget(model=TextureImportListModel(), delegate=TextureImportListDelegate())
        open_scan_dialog_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='scan_folder'")
        await open_scan_dialog_button.click()
        await ui_test.human_delay()

        scan_dialog_title = "Scan Directory for Input Files"
        input_folder = Path(self.temp_dir.name)
        input_folder_field = ui_test.find(
            f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='input_folder_field'"
        )
        search_field = ui_test.find(f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='scan_search_field'")
        scan_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='scan_folder_button'")
        input_folder_field.model.set_value(str(input_folder / "missing"))
        await scan_button.click()
        await ui_test.human_delay()
        self.assertEqual("FieldError", input_folder_field.widget.style_type_name_override)

        input_folder_field.model.set_value(str(input_folder))
        search_field.model.set_value("[")
        await ui_test.human_delay()

        # Rescan after the correction so only the newly invalid search remains highlighted.
        await scan_button.click()
        await ui_test.human_delay()

        input_folder_field = ui_test.find(
            f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='input_folder_field'"
        )
        search_field = ui_test.find(f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='scan_search_field'")
        self.assertEqual("Field", input_folder_field.widget.style_type_name_override)
        self.assertEqual("Select a directory to scan.", input_folder_field.widget.tooltip)
        self.assertEqual("FieldError", search_field.widget.style_type_name_override)
        self.assertEqual(
            "Enter a valid regular expression or clear the Search field.",
            search_field.widget.tooltip,
        )

    async def test_scan_folder_replaces_scroll_widgets_between_scans(self):
        """A repeated scan scrolls only the widgets from the current result view."""
        # Populate the production dialog twice so the second result view replaces the first.
        window = await self.__setup_widget(model=TextureImportListModel(), delegate=TextureImportListDelegate())
        open_scan_dialog_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='scan_folder'")
        await open_scan_dialog_button.click()
        await ui_test.human_delay()

        scan_dialog_title = "Scan Directory for Input Files"
        input_folder = Path(self.temp_dir.name)
        (input_folder / f"first_{'a' * 100}.png").touch()
        second_file = input_folder / f"second_{'b' * 100}.png"
        second_file.touch()

        input_folder_field = ui_test.find(
            f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='input_folder_field'"
        )
        await ensure_scan_dialog_input_folder(input_folder_field, input_folder)
        search_field = ui_test.find(f"{scan_dialog_title}//Frame/**/StringField[*].identifier=='scan_search_field'")
        scan_button = ui_test.find(f"{scan_dialog_title}//Frame/**/Button[*].identifier=='scan_folder_button'")
        await scan_button.click()
        await ui_test.human_delay(10)
        await replace_field_text(search_field, "second")

        # Rescan with the narrower filter, then drag the current result view's scroll handle.
        await scan_button.click()
        await ui_test.human_delay(10)
        current_row_scroll_frames = [
            frame
            for frame in ui_test.find_all(f"{scan_dialog_title}//Frame/**/ScrollingFrame[*]")
            if frame.widget.scroll_x_max > 0
        ]
        self.assertEqual(1, len(current_row_scroll_frames))
        self.assertEqual(0, current_row_scroll_frames[0].widget.scroll_x)
        scroll_manipulator = ui_test.find(
            f"{scan_dialog_title}//Frame/**/Rectangle[*].name=='PropertiesPaneSectionTreeManipulator'"
        )
        scroll_target = scroll_manipulator.center
        scroll_target.x += 20
        await ui_test.emulate_mouse_drag_and_drop(scroll_manipulator.center, scroll_target)
        await ui_test.human_delay()

        current_checkboxes = ui_test.find_all(f"{scan_dialog_title}//Frame/**/CheckBox[*]")
        self.assertEqual(1, len(current_checkboxes))
        self.assertEqual(second_file.name, current_checkboxes[0].widget.name)
        self.assertGreater(current_row_scroll_frames[0].widget.scroll_x, 0)

    async def test_drop_valid_files(self):
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        base_path = Path(self.temp_dir.name)
        good_items = [base_path / "0.jpg", base_path / "1.jpg", base_path / "2.JPG"]
        for item in good_items:
            item.touch()

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Build a real drag payload and confirm the rendered list starts empty.
        widget = self.texture_import_list_widget
        event = DropEvent()
        event.payload = {"paths": [str(item) for item in good_items]}

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(file_items), 0)

        # Drop supported textures through the widget boundary and let the list rebuild.
        widget.on_drag_drop_external(event)
        await ui_test.human_delay(70)

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(file_items), len(good_items))

    async def test_drop_invalid_files(self):
        # Mix supported and unsupported files in one external drag payload.
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        base_path = Path(self.temp_dir.name)
        good_items = [base_path / "1.jpg", base_path / "2.PNG"]
        bad_items = [
            base_path / "3.usd",
            base_path / "4.USD",
            base_path / "5.nogood",
            base_path / "6.INVALID",
            base_path / "extensionless",
        ]
        for item in good_items:
            item.touch()
        for item in bad_items:
            item.touch()
        all_items = [str(item) for item in good_items] + [str(item) for item in bad_items]

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Confirm the rendered list starts empty before the mixed drop.
        widget = self.texture_import_list_widget
        event = DropEvent()
        event.payload = {"paths": all_items}

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(file_items), 0)

        # Drop the mixed payload through the widget boundary.
        try:
            widget.on_drag_drop_external(event)
            await ui_test.human_delay()

            file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
            # Supported textures become rows while rejected files produce the user-facing error dialog.
            self.assertEqual(len(file_items), len(good_items))
            self.assertIsNotNone(ui_test.find(DIALOG_TITLE))
        finally:
            for button in ui_test.find_all(
                f"{DIALOG_TITLE}//Frame/**/Button[*].identifier=='ingestion_error_ok_button'"
            ):
                await button.click()
            await ui_test.human_delay()

    async def test_drop_directory(self):
        # Build a drag payload containing directories instead of importable textures.
        model = TextureImportListModel()
        delegate = TextureImportListDelegate()

        base_path = Path(self.temp_dir.name)
        subdir1 = base_path / "sub1"
        subdir2 = base_path / "sub2"
        subdir1.mkdir(parents=True)
        subdir2.mkdir(parents=True)
        items = [subdir1, subdir2]

        window = await self.__setup_widget(model=model, delegate=delegate)  # Keep in memory during test

        # Confirm the rendered list starts empty before the invalid drop.
        widget = self.texture_import_list_widget
        event = DropEvent()
        event.payload = {"paths": items}

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        self.assertEqual(len(file_items), 0)

        # Drop directories through the real widget while suppressing only the unrelated error-dialog callback.
        with patch("omni.flux.asset_importer.widget.texture_import_list.widget._texture_validation_failed_callback"):
            widget.on_drag_drop_external(event)
            await ui_test.human_delay()

        file_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        # Directory payloads never become texture-import rows.
        self.assertEqual(len(file_items), 0)
