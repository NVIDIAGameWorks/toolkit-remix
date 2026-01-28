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
from unittest.mock import Mock

import carb
import omni.kit
import omni.kit.test
import omni.usd
from carb.input import KeyboardInput
from omni import ui
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.asset_importer.widget.texture_import_list import TextureImportListDelegate
from omni.flux.validator.plugin.context.usd_stage.texture_importer import TextureImporter
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path


class TestTextureImporterE2E(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()
        self.temp_dir = TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.temp_dir.cleanup()
        self.stage = None
        self.temp_dir = None

    async def __setup_widget(self, schema_data: TextureImporter.Data):
        await arrange_windows(topleft_window="Stage")

        window = ui.Window("TestTextureImporterWindow", height=400, width=800)
        with window.frame:
            texture_importer = TextureImporter()
            await texture_importer._build_ui(schema_data)  # noqa PLW0212

        await ui_test.human_delay()

        return window, texture_importer

    async def test_render_widget_fields_no_context_no_extension_should_render_correctly(self):
        await self.__run_render_widget()

    async def test_render_widget_fields_with_context_should_render_correctly(self):
        await self.__run_render_widget(context="test_context")

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
        await self.__run_edit_output_directory_field(True, False, False)

    async def test_edit_output_directory_field_matching_input_file_should_update_style_and_reset_on_end_edit(self):
        await self.__run_edit_output_directory_field(False, False, True)

    async def test_output_directory_file_picker_invalid(self):
        await self.__run_edit_output_directory_field(False, True, False)

    async def test_output_directory_file_picker_valid(self):
        await self.__run_edit_output_directory_field(True, True, False)

    async def test_edit_input_files_should_update_schema(self):
        mock_callback = Mock()
        callback_future = asyncio.Future()
        callback_future.set_result(None)
        mock_callback.return_value = callback_future

        input_files, output_path, schema_data = await self.__setup_schema_data()
        window, texture_importer = await self.__setup_widget(schema_data)  # Keep in memory during test

        # Start the test
        remove_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='remove_file'")
        input_file_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        input_file_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")

        # Make sure everything is rendered correctly
        self.assertIsNotNone(remove_button)
        self.assertEqual(len(input_files), len(input_file_labels))
        self.assertEqual(len(input_files), len(input_file_types))

        # Remove the first item in the list
        await input_file_labels[0].click()
        await ui_test.human_delay()

        await remove_button.click()
        await ui_test.human_delay()

        # Make sure the item was removed
        input_file_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        input_file_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")

        self.assertEqual(len(input_files) - 1, len(input_file_labels))
        self.assertEqual(len(input_files) - 1, len(input_file_types))

        # Run the import
        await texture_importer._setup(schema_data, mock_callback, None)  # noqa PLW0212

        await ui_test.human_delay()

        # Make sure only the selected files were imported
        self.assertFalse((output_path / input_files[0][0].name).exists())
        for input_file_path, _ in input_files[1:]:
            self.assertTrue((output_path / input_file_path.name).exists())

    async def test_remove_wrong_input_files_should_update_schema(self):
        mock_callback = Mock()
        callback_future = asyncio.Future()
        callback_future.set_result(None)
        mock_callback.return_value = callback_future

        input_files, _output_path, schema_data = await self.__setup_schema_data()
        window, _texture_importer = await self.__setup_widget(schema_data)  # Keep in memory during test

        # Start the test
        remove_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='remove_file'")
        input_file_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        input_file_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")

        # Make sure everything is rendered correctly
        self.assertIsNotNone(remove_button)
        self.assertEqual(len(input_files), len(input_file_labels))
        self.assertEqual(len(input_files), len(input_file_types))

        # remove all files
        self.temp_dir.cleanup()

        # Remove the first item in the list
        await input_file_labels[0].click()
        await ui_test.human_delay()

        await remove_button.click()
        await ui_test.human_delay()

        # Make sure the item was removed
        input_file_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        input_file_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")

        self.assertEqual(len(input_files) - 1, len(input_file_labels))
        self.assertEqual(len(input_files) - 1, len(input_file_types))

    async def __run_render_widget(self, context: str = ""):
        # Setup the test
        input_files, output_path, schema_data = await self.__setup_schema_data(context=context)
        window, _ = await self.__setup_widget(schema_data)  # Keep in memory during test

        # Start the test
        context_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='context_field'")
        output_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='output_directory_field'")
        add_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='add_file'")
        remove_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='remove_file'")
        input_file_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='file_path'")
        input_file_types = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='texture_type'")

        # Make sure everything is rendered correctly
        self.assertIsNotNone(context_field)
        self.assertIsNotNone(output_field)
        self.assertIsNotNone(add_button)
        self.assertIsNotNone(remove_button)
        self.assertEqual(len(input_files), len(input_file_labels))
        self.assertEqual(len(input_files), len(input_file_types))

        self.assertEqual(context if context else "None", context_field.widget.model.get_value_as_string())
        self.assertEqual(Path(output_path).as_posix(), Path(output_field.widget.model.get_value_as_string()).as_posix())

        for i, input_file in enumerate(input_files):
            expected_type_index = [
                t.name
                for t in TextureTypes
                if TextureImportListDelegate._TEXTURE_TYPE_IMPORT_ENABLED_MAP.get(t, False)  # noqa PLW0212
            ].index(input_file[1])
            self.assertEqual(
                expected_type_index, input_file_types[i].widget.model.get_item_value_model().get_value_as_int()
            )
            self.assertEqual(str(os.path.basename(input_file[0])), input_file_labels[i].widget.text)

    async def test_input_versus_output_validation(self):
        # Setup folders and files:
        base_path = Path(self.temp_dir.name)
        carb.tokens.get_tokens_interface().set_value("texture_importer_test_dir", str(base_path))

        input_path_0 = (base_path / "input0").resolve()
        input_path_1 = (base_path / "input1").resolve()
        input_path_2 = (base_path / "input2").resolve()
        output_path = (base_path / "output").resolve()

        os.makedirs(input_path_0)
        os.makedirs(input_path_1)
        os.makedirs(input_path_2)
        os.makedirs(output_path)

        input_file_0 = ((input_path_0 / "albedo.png").resolve(), TextureTypes.DIFFUSE.name)
        input_file_1 = ((input_path_1 / "metallic.png").resolve(), TextureTypes.METALLIC.name)
        input_file_2 = ((input_path_2 / "normal_gl.png").resolve(), TextureTypes.NORMAL_OGL.name)
        input_files = [input_file_0, input_file_1, input_file_2]

        for input_file_path, _ in input_files:
            shutil.copy(
                get_test_data_path(__name__, Path("textures") / Path(input_file_path).name), str(input_file_path)
            )

        # setup data and a widget:
        schema_data = TextureImporter.Data(
            context_name="", input_files=[input_file_0, input_file_1], output_directory=f"{input_path_2}"
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

        filepicker_dialog_name = "Select a texture to import"
        # The file picker window should now be opened (0 < len(widgets))
        self.assertLess(0, len(ui_test.find_all(f"{filepicker_dialog_name}//Frame/**/*")))

        import_button = ui_test.find(f"{filepicker_dialog_name}//Frame/**/Button[*].text=='Import'")
        directory_path_field = ui_test.find(f"{filepicker_dialog_name}//Frame/**/filepicker_directory_path")
        file_name_field = ui_test.find(
            f"{filepicker_dialog_name}//Frame/**/StringField[*].style_type_name_override=='Field'"
        )
        self.assertIsNotNone(import_button)
        self.assertIsNotNone(directory_path_field)
        self.assertIsNotNone(file_name_field)

        # It takes a while for the tree to update
        await ui_test.human_delay(50)
        await directory_path_field.input(str(input_path_2), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(50)

        await file_name_field.input(str(input_file_2[0].name), end_key=KeyboardInput.DOWN)
        await ui_test.human_delay()

        # Make sure we are selecting the right file
        self.assertEqual(
            str(input_path_2),
            directory_path_field.model._field.model.get_value_as_string(),  # noqa PLW0212
        )
        self.assertEqual(str(input_file_2[0].name), file_name_field.model.get_value_as_string())

        await import_button.click()
        await ui_test.human_delay(50)

        # Added input file that is in the same directory as output, check if output directory is invalid:
        self.assertEqual("FieldError", output_directory_field.widget.style_type_name_override)

        # Now change output directory back to correct one:
        await output_directory_field.input("", end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()
        await output_directory_field.input(str(output_path), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()
        self.assertEqual("Field", output_directory_field.widget.style_type_name_override)

    async def __run_edit_output_directory_field(self, is_valid: bool, use_filepicker: bool, output_in_input: bool):
        # Setup the test
        new_output_dir_path = (Path(self.temp_dir.name) / "new_output").resolve()

        if is_valid:
            os.makedirs(new_output_dir_path)

        mock_callback = Mock()
        callback_future = asyncio.Future()
        callback_future.set_result(None)
        mock_callback.return_value = callback_future

        input_files, output_path, schema_data = await self.__setup_schema_data()
        window, texture_importer = await self.__setup_widget(schema_data)  # Keep in memory during test

        expected_output_path = str((new_output_dir_path if is_valid else output_path).resolve())

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
            self.assertEqual(expected_output_path + "/", dir_path_field.model._path)  # noqa PLW0212

            await select_button.click()
            await ui_test.human_delay()
        elif output_in_input:
            # can't use this because when we write the input path `AppData/Local/Temp/tmpzpa_yyej/input`
            # the field will catch `AppData/Local/Temp/`, which is a valid path
            # so we emulate the keyboard with 0 human time to have the field to not catch this
            # await output_directory_field.input(str(input_files[0][0].parent), end_key=KeyboardInput.DOWN)

            await output_directory_field.double_click(human_delay_speed=2)
            await ui_test.human_delay(2)
            await ui_test.emulate_char_press(str(input_files[0][0].parent), human_delay_speed=0)
            await ui_test.emulate_keyboard_press(KeyboardInput.DOWN)

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

        # Run the import
        await texture_importer._setup(schema_data, mock_callback, None)  # noqa PLW0212

        await ui_test.human_delay()

        # Make sure files were imported in the right output directory
        for input_file_path, _ in input_files:
            self.assertTrue(((new_output_dir_path if is_valid else output_path) / input_file_path.name).exists())

    async def __setup_schema_data(self, context: str = ""):
        base_path = Path(self.temp_dir.name)
        carb.tokens.get_tokens_interface().set_value("texture_importer_test_dir", str(base_path))

        input_path = base_path / "input"
        output_path = base_path / "output"

        os.makedirs(input_path)
        os.makedirs(output_path)

        input_file_0 = input_path / "albedo.png"
        input_file_1 = input_path / "metallic.png"
        input_file_2 = input_path / "normal_gl.png"
        input_files = [
            (input_file_0, TextureTypes.DIFFUSE.name),
            (input_file_1, TextureTypes.METALLIC.name),
            (input_file_2, TextureTypes.NORMAL_OGL.name),
        ]

        for input_file_path, _ in input_files:
            shutil.copy(
                get_test_data_path(__name__, Path("textures") / Path(input_file_path).name), str(input_file_path)
            )

        schema_data = TextureImporter.Data(
            context_name=context,
            input_files=input_files,
            create_output_directory_if_missing=False,
            output_directory="${texture_importer_test_dir}/output",
        )
        return input_files, output_path, schema_data
