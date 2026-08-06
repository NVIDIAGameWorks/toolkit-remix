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

import asyncio
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, Mock, patch

import carb
import omni.kit
import omni.kit.test
import omni.usd
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardInput
from omni import ui
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.validator.plugin.context.usd_stage import asset_importer as asset_importer_module
from omni.flux.validator.plugin.context.usd_stage.asset_importer import AssetImporter
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path


class TestAssetImporterE2E(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self._widget_instances: list[tuple[AssetImporter, ui.Window]] = []
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()
        self.temp_dir = TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        for asset_importer, window in self._widget_instances:
            asset_importer.destroy()
            window.destroy()
        self._widget_instances.clear()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.temp_dir.cleanup()
        self.stage = None
        self.temp_dir = None

    async def __setup_widget(self, schema_data: AssetImporter.Data):
        await arrange_windows(topleft_window="Stage")

        window = ui.Window("TestAssetImporterWindow", height=400, width=800)
        asset_importer = AssetImporter()
        self._widget_instances.append((asset_importer, window))
        with window.frame:
            parent_schema = Mock()
            parent_schema.data = schema_data
            asset_importer.set_parent_schema(parent_schema)
            await asset_importer._build_ui(schema_data)

        await ui_test.human_delay()

        return window, asset_importer

    async def test_render_widget_fields_no_context_no_extension_should_render_correctly(self):
        await self.__run_render_widget()

    async def test_render_widget_fields_with_context_should_render_correctly(self):
        await self.__run_render_widget(context="test_context")

    async def test_render_widget_fields_with_extension_should_render_correctly(self):
        await self.__run_render_widget(use_usda=True)

    async def test_edit_context_field_should_be_readonly(self):
        # Setup the test
        context_name = "test_context"
        _input_files, _output_path, schema_data = await self.__setup_schema_data(context=context_name)
        window, _ = await self.__setup_widget(schema_data)  # Keep in memory during test

        # Start the test
        context_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='context_field'")

        # Make sure everything is rendered correctly
        self.assertIsNotNone(context_field)

        # Don't end edit
        await context_field.input("other_context", end_key=KeyboardInput.DOWN)

        await ui_test.human_delay()

        self.assertEqual(context_name, context_field.widget.model.get_value_as_string())

        # End edit
        await context_field.input("", end_key=KeyboardInput.ENTER)

        await ui_test.human_delay()

        self.assertEqual(context_name, context_field.widget.model.get_value_as_string())

    async def test_edit_output_directory_field_invalid_should_update_style_and_reset_on_end_edit(self):
        await self.__run_edit_output_directory_field(False, False, False)

    async def test_edit_output_directory_field_valid_should_update_style_and_update_schema_on_end_edit(self):
        await self.__run_edit_output_directory_field(True, False, False, reset_on_project_open=True)

    async def test_edit_output_directory_field_matching_input_file_should_update_style_and_reset_on_end_edit(self):
        await self.__run_edit_output_directory_field(False, False, True)

    async def test_output_directory_file_picker_invalid(self):
        await self.__run_edit_output_directory_field(False, True, False)

    async def test_output_directory_file_picker_valid(self):
        await self.__run_edit_output_directory_field(True, True, False)

    async def test_reactivate_after_clearing_output_directory_should_restore_server_default(self):
        """Reject a blank edit without preventing the next server-default refresh."""
        _input_files, _output_path, schema_data = await self.__setup_schema_data()
        schema_data.create_output_directory_if_missing = True
        window, asset_importer = await self.__setup_widget(schema_data)
        output_directory_field = ui_test.find(
            f"{window.title}//Frame/**/StringField[*].identifier=='output_directory_field'"
        )
        self.assertIsNotNone(output_directory_field)
        previous_schema_output_directory = schema_data.output_directory
        previous_field_value = output_directory_field.widget.model.get_value_as_string()

        await output_directory_field.click()
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
        await ui_test.human_delay()

        self.assertEqual("", output_directory_field.widget.model.get_value_as_string())
        self.assertEqual("FieldError", output_directory_field.widget.style_type_name_override)
        self.assertEqual(previous_schema_output_directory, schema_data.output_directory)

        await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
        await ui_test.human_delay()

        self.assertEqual(previous_field_value, output_directory_field.widget.model.get_value_as_string())
        self.assertEqual("Field", output_directory_field.widget.style_type_name_override)
        self.assertEqual(previous_schema_output_directory, schema_data.output_directory)

        server_output_directory = (Path(self.temp_dir.name) / "server_output").resolve()
        server_output_directory.mkdir()
        default_output_endpoint = "https://example.invalid/default-output-directory"
        schema_data.default_output_endpoint = default_output_endpoint
        send_request_mock = AsyncMock(return_value={"directory_path": str(server_output_directory)})
        with patch.object(asset_importer_module, "_send_request", send_request_mock):
            asset_importer.show(True, schema_data)
            await ui_test.human_delay()
            send_request_mock.assert_awaited_once_with("GET", default_output_endpoint)

        self.assertEqual(
            server_output_directory.as_posix(), Path(str(schema_data.output_directory)).resolve().as_posix()
        )
        self.assertEqual(
            server_output_directory.as_posix(),
            Path(output_directory_field.widget.model.get_value_as_string()).resolve().as_posix(),
        )

    async def test_edit_usd_extension_should_update_schema(self):
        mock_callback = Mock()
        callback_future = asyncio.Future()
        callback_future.set_result(None)
        mock_callback.return_value = callback_future

        output_usd_extension = "usda"

        input_files, output_path, schema_data = await self.__setup_schema_data()
        window, asset_importer = await self.__setup_widget(schema_data)  # Keep in memory during test

        # Start the test
        extension_combobox = ui_test.find(f"{window.title}//Frame/**/ComboBox[*].identifier=='extension_comboxbox'")

        # Make sure everything is rendered correctly
        self.assertIsNotNone(extension_combobox)
        self.assertEqual(0, extension_combobox.widget.model.get_item_value_model().get_value_as_int())

        # Select USDA. It does not look possible to click on the combobox options so set using the model
        extension_combobox.widget.model.get_item_value_model().set_value(1)
        await ui_test.human_delay()

        # Run the import
        await asset_importer._setup(schema_data, mock_callback, None)

        await ui_test.human_delay()

        # Make sure only files were imported with the right extension
        for input_file in input_files:
            self.assertTrue((output_path / input_file.name).with_suffix(f".{output_usd_extension}").exists())

    async def test_edit_input_files_should_update_schema(self):
        mock_callback = Mock()
        callback_future = asyncio.Future()
        callback_future.set_result(None)
        mock_callback.return_value = callback_future

        input_files, output_path, schema_data = await self.__setup_schema_data()
        window, asset_importer = await self.__setup_widget(schema_data)  # Keep in memory during test

        # Start the test
        remove_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='remove_file'")
        input_file_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")

        # Make sure everything is rendered correctly
        self.assertIsNotNone(remove_button)
        self.assertEqual(len(input_files), len(input_file_labels))

        # Remove the first item in the list
        await input_file_labels[0].click()
        await ui_test.human_delay()

        await remove_button.click()
        await ui_test.human_delay()

        # Run the import
        await asset_importer._setup(schema_data, mock_callback, None)

        await ui_test.human_delay()

        # Make sure only the selected files were imported
        self.assertFalse((output_path / input_files[0].name).with_suffix(".usd").exists())
        for input_file in input_files[1:]:
            self.assertTrue((output_path / input_file.name).with_suffix(".usd").exists())

    async def test_edit_normal_map_convention_should_update_schema(self):
        # Arrange
        input_files, _output_path, schema_data = await self.__setup_schema_data()
        window, asset_importer = await self.__setup_widget(schema_data)
        convention_label = ui_test.find(f"{window.title}//Frame/**/Label[*].identifier=='normal_map_convention_label'")
        convention_fields = ui_test.find_all(
            f"{window.title}//Frame/**/ComboBox[*].identifier=='normals_type_combobox'"
        )
        convention_model = convention_fields[0].widget.model
        self.assertIsNone(schema_data.normal_map_convention)
        self.assertEqual(0, convention_model.get_item_value_model().get_value_as_int())

        # Act
        convention_model.get_item_value_model().set_value(3)
        await ui_test.human_delay()

        # Assert
        self.assertEqual(3, len(input_files))
        self.assertEqual("Normal Map Convention", convention_label.widget.text)
        self.assertEqual(1, len(convention_fields))
        self.assertEqual(
            [
                "Preserve Imported",
                TextureTypes.NORMAL_OGL.value,
                TextureTypes.NORMAL_DX.value,
                TextureTypes.NORMAL_OTH.value,
            ],
            [
                convention_model.get_item_value_model(item).get_value_as_string()
                for item in convention_model.get_item_children(None)
            ],
        )
        self.assertIn(
            "normal-map textures referenced by imported models, not mesh normals",
            asset_importer._normal_map_convention_selector._info_icon._message,
        )
        self.assertEqual(TextureTypes.NORMAL_OTH.name, schema_data.normal_map_convention)

        input_file_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        remove_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='remove_file'")
        await input_file_labels[0].click()
        await remove_button.click()
        await ui_test.human_delay()

        convention_fields = ui_test.find_all(
            f"{window.title}//Frame/**/ComboBox[*].identifier=='normals_type_combobox'"
        )
        self.assertEqual(1, len(convention_fields))
        self.assertEqual(3, convention_fields[0].widget.model.get_item_value_model().get_value_as_int())
        self.assertEqual(TextureTypes.NORMAL_OTH.name, schema_data.normal_map_convention)

    async def __run_render_widget(self, context: str = "", use_usda: bool = False):
        # Setup the test
        input_files, output_path, schema_data = await self.__setup_schema_data(context=context, use_usda=use_usda)
        window, _ = await self.__setup_widget(schema_data)  # Keep in memory during test

        # Start the test
        context_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='context_field'")
        output_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='output_directory_field'")
        extension_combobox = ui_test.find(f"{window.title}//Frame/**/ComboBox[*].identifier=='extension_comboxbox'")
        add_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='add_file'")
        remove_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='remove_file'")
        input_file_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")

        # Make sure everything is rendered correctly
        self.assertIsNotNone(context_field)
        self.assertIsNotNone(output_field)
        self.assertIsNotNone(extension_combobox)
        self.assertIsNotNone(add_button)
        self.assertIsNotNone(remove_button)
        self.assertEqual(len(input_files), len(input_file_labels))

        self.assertEqual(context or "None", context_field.widget.model.get_value_as_string())
        self.assertEqual(Path(output_path).as_posix(), Path(output_field.widget.model.get_value_as_string()).as_posix())
        self.assertEqual(
            1 if use_usda else 0, extension_combobox.widget.model.get_item_value_model().get_value_as_int()
        )

        for i, input_file in enumerate(input_files):
            self.assertEqual(Path(input_file).as_posix(), Path(input_file_labels[i].widget.text).as_posix())

    async def test_input_versus_output_validation(self):
        # Setup folders and files:
        base_path = Path(self.temp_dir.name)
        carb.tokens.get_tokens_interface().set_value("asset_importer_test_dir", str(base_path))

        input_path_0 = (base_path / "input0").resolve()
        input_path_1 = (base_path / "input1").resolve()
        input_path_2 = (base_path / "input2").resolve()
        output_path = (base_path / "output").resolve()

        os.makedirs(input_path_0)
        os.makedirs(input_path_1)
        os.makedirs(input_path_2)
        os.makedirs(output_path)

        input_file_0 = (input_path_0 / "0.usda").resolve()
        input_file_1 = (input_path_1 / "1.usda").resolve()
        input_file_2 = (input_path_2 / "2.usda").resolve()
        input_files = [input_file_0, input_file_1, input_file_2]

        for input_file in input_files:
            shutil.copy(get_test_data_path(__name__, "usd/cubes.usda"), str(input_file))

        # setup data and a widget:
        schema_data = AssetImporter.Data(
            context_name="",
            input_files=[input_file_0, input_file_1],
            output_directory=f"{input_path_2}",
            output_usd_extension="usda",
        )
        window, _ = await self.__setup_widget(schema_data)  # Keep in memory during test
        output_directory_field = ui_test.find(
            f"{window.title}//Frame/**/StringField[*].identifier=='output_directory_field'"
        )
        self.assertIsNotNone(output_directory_field)

        # Existing input files 0, 1; output directory of input #2 - output directory style should be Field
        self.assertEqual("Field", output_directory_field.widget.style_type_name_override)

        # Add a new input file #2 and check if that will invalidate output directory field:
        add_inputs_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='add_file'")
        self.assertIsNotNone(add_inputs_button)
        await add_inputs_button.click()
        await ui_test.human_delay(50)

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
        await dir_path_field.input(str(input_path_2), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(50)

        await file_name_field.input(str(input_file_2.name), end_key=KeyboardInput.DOWN)
        await ui_test.human_delay()

        # Make sure we are selecting the right file
        self.assertEqual(str(input_path_2), dir_path_field.model._field.model.get_value_as_string())
        self.assertEqual(str(input_file_2.name), file_name_field.model.get_value_as_string())

        await import_button.click()
        await ui_test.human_delay(50)

        # If the value is invalid, the style should reflect that
        self.assertEqual("FieldError", output_directory_field.widget.style_type_name_override)

        # Now change output directory back to correct one:
        await output_directory_field.input("", end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()
        await output_directory_field.input(str(output_path), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()
        self.assertEqual("Field", output_directory_field.widget.style_type_name_override)

    async def __run_edit_output_directory_field(
        self, is_valid: bool, use_filepicker: bool, output_in_input: bool, reset_on_project_open: bool = False
    ):
        # Setup the test
        new_output_dir_path = (Path(self.temp_dir.name) / "new_output").resolve()

        if is_valid:
            os.makedirs(new_output_dir_path)

        mock_callback = Mock()
        callback_future = asyncio.Future()
        callback_future.set_result(None)
        mock_callback.return_value = callback_future

        input_files, output_path, schema_data = await self.__setup_schema_data()
        window, asset_importer = await self.__setup_widget(schema_data)  # Keep in memory during test

        expected_import_path = new_output_dir_path if is_valid else output_path
        expected_output_path = str(expected_import_path.resolve())

        output_directory_field = ui_test.find(
            f"{window.title}//Frame/**/StringField[*].identifier=='output_directory_field'"
        )

        # Make sure everything is rendered correctly
        self.assertIsNotNone(output_directory_field)

        # Start the test
        if use_filepicker:
            # an invalid path in the file picker will just become the first valid parent of the invalid path
            output_filepicker_button = ui_test.find(
                f"{window.title}//Frame/**/Image[*].identifier=='output_directory_open_file_picker'"
            )
            self.assertIsNotNone(output_filepicker_button)

            await output_filepicker_button.click()
            await ui_test.human_delay()

            window_name = "Choose output directory"

            # The file picker window should now be opened (0 < len(widgets))
            self.assertLess(0, len(ui_test.find_all(f"{window_name}//Frame/**/*")))

            select_button = ui_test.find(f"{window_name}//Frame/**/Button[*].text=='Select'")
            dir_path_field = ui_test.find(
                f"{window_name}//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
            )

            self.assertIsNotNone(select_button)
            self.assertIsNotNone(dir_path_field)

            # It takes a while for the tree to update
            await ui_test.human_delay(50)
            await dir_path_field.input(expected_output_path, end_key=KeyboardInput.ENTER)
            await ui_test.human_delay(50)

            # Make sure we are selecting the right file
            self.assertEqual(expected_output_path + "/", dir_path_field.model._path)

            await select_button.click()
            await ui_test.human_delay()
        elif output_in_input:
            # can't use this because when we write the input path `AppData/Local/Temp/tmpzpa_yyej/input`
            # the field will catch `AppData/Local/Temp/`, which is a valid path
            # so we emulate the keyboard with 0 human time to have the field to not catch this
            # await output_directory_field.input(str(input_files[0].parent), end_key=KeyboardInput.DOWN)

            await output_directory_field.double_click(human_delay_speed=2)
            await ui_test.human_delay(2)
            await ui_test.emulate_char_press(str(input_files[0].parent), human_delay_speed=0)
            await ui_test.emulate_keyboard_press(KeyboardInput.DOWN)

            await ui_test.human_delay()

            # If the value is invalid, the style should reflect that
            self.assertEqual("FieldError", output_directory_field.widget.style_type_name_override)

            # End edit
            await output_directory_field.input("", end_key=KeyboardInput.ENTER)

            await ui_test.human_delay()
        else:
            # Clear the output directory field only if is_valid, otherwise it will contain the "."
            # as its last correct value it will fall back to:
            if is_valid:
                output_directory_field.widget.model.set_value("")

            # can't use this because when we write the input path `AppData/Local/Temp/tmpzpa_yyej/input`
            # the field will catch `AppData/Local/Temp/`, which is a valid path
            # so we emulate the keyboard with 0 human time to have the field to not catch this
            # Don't end edit
            # await output_directory_field.input(str(new_output_dir_path), end_key=KeyboardInput.DOWN)

            await output_directory_field.double_click(human_delay_speed=2)
            await ui_test.human_delay(2)
            await ui_test.emulate_char_press(str(new_output_dir_path), human_delay_speed=0)
            await ui_test.emulate_keyboard_press(KeyboardInput.DOWN)

            await ui_test.human_delay()

            # If the value is invalid, the style should reflect that
            self.assertEqual(
                "Field" if is_valid else "FieldError", output_directory_field.widget.style_type_name_override
            )

            # End edit
            await output_directory_field.input("", end_key=KeyboardInput.ENTER)
            await ui_test.human_delay()

        # Make sure the expected value is set and the field style is valid
        self.assertEqual(
            Path(expected_output_path).as_posix(),
            Path(output_directory_field.widget.model.get_value_as_string()).resolve().as_posix(),
        )
        self.assertEqual("Field", output_directory_field.widget.style_type_name_override)

        if is_valid:
            server_output_dir_path = (Path(self.temp_dir.name) / "server_output").resolve()
            os.makedirs(server_output_dir_path)
            schema_data.default_output_endpoint = "https://example.invalid/default-output-directory"
            send_request_mock = AsyncMock(return_value={"directory_path": str(server_output_dir_path)})
            with patch.object(
                asset_importer_module,
                "_send_request",
                new=send_request_mock,
            ):
                asset_importer.show(True, schema_data)
                await ui_test.human_delay()
                send_request_mock.assert_not_awaited()
                self.assertEqual(
                    Path(expected_output_path).as_posix(), Path(str(schema_data.output_directory)).resolve().as_posix()
                )
                self.assertEqual(
                    Path(expected_output_path).as_posix(),
                    Path(output_directory_field.widget.model.get_value_as_string()).resolve().as_posix(),
                )

                if reset_on_project_open:
                    success, _ = await omni.usd.get_context("").open_stage_async(
                        get_test_data_path(__name__, "usd/cubes.usda")
                    )
                    self.assertTrue(success)
                    await ui_test.human_delay()
                    send_request_mock.assert_awaited_once_with("GET", schema_data.default_output_endpoint)
                    expected_import_path = server_output_dir_path
                    expected_output_path = str(server_output_dir_path)

                self.assertEqual(
                    Path(expected_output_path).as_posix(), Path(str(schema_data.output_directory)).resolve().as_posix()
                )
                self.assertEqual(
                    Path(expected_output_path).as_posix(),
                    Path(output_directory_field.widget.model.get_value_as_string()).resolve().as_posix(),
                )

            schema_data.default_output_endpoint = None

        # Run the import
        await asset_importer._setup(schema_data, mock_callback, None)

        await ui_test.human_delay()

        # Make sure files were imported in the right output directory
        for input_file in input_files:
            self.assertTrue((expected_import_path / input_file.name).with_suffix(".usd").exists())

    async def __setup_schema_data(self, context: str = "", use_usda: bool = False):
        base_path = Path(self.temp_dir.name)
        carb.tokens.get_tokens_interface().set_value("asset_importer_test_dir", str(base_path))

        input_path = base_path / "input"
        output_path = base_path / "output"

        os.makedirs(input_path)
        os.makedirs(output_path)

        input_file_0 = input_path / "0.usda"
        input_file_1 = input_path / "1.usda"
        input_file_2 = input_path / "2.usda"
        input_files = [input_file_0, input_file_1, input_file_2]

        for input_file in input_files:
            shutil.copy(get_test_data_path(__name__, "usd/cubes.usda"), str(input_file))

        schema_data = AssetImporter.Data(
            context_name=context,
            input_files=input_files,
            create_output_directory_if_missing=False,
            output_directory="${asset_importer_test_dir}/output",
            output_usd_extension="usda" if use_usda else "usd",
        )
        return input_files, output_path, schema_data
