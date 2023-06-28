"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, call

import omni.kit.test
from carb.input import KeyboardInput
from lightspeed.trex.mod_packaging_output.widget import ModPackagingOutputWidget
from omni import ui
from omni.flux.utils.common.omni_url import OmniUrl
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, wait_stage_loading


class TestModPackagingOutputWidget(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.context = omni.usd.get_context()
        await self.context.open_stage_async(get_test_data_path(__name__, "usd/project.usda"))

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.context = None
        self.temp_dir.cleanup()
        self.temp_dir = None

    async def __setup_widget(self):
        await arrange_windows(topleft_window="Stage")

        window = ui.Window("TestModPackagingDetailsWindow", height=400, width=400)
        with window.frame:
            mod_output = ModPackagingOutputWidget(context_name="")
        await ui_test.human_delay()
        mod_output.show(True)

        return window, mod_output

    async def __destroy_widget(self, window, widget):
        widget.destroy()
        window.destroy()

    async def test_default_value_should_be_populated(self):
        window, widget = await self.__setup_widget()

        enable_override = ui_test.find(f"{window.title}//Frame/**/CheckBox[*].identifier=='enable_override'")
        output_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='output_field'")
        disabled_overlay = ui_test.find(f"{window.title}//Frame/**/Rectangle[*].identifier=='disabled_overlay'")
        file_picker_button = ui_test.find(f"{window.title}//Frame/**/Image[*].identifier=='file_picker_button'")
        open_in_explorer_button = ui_test.find(
            f"{window.title}//Frame/**/Button[*].identifier=='open_in_explorer_button'"
        )

        self.assertIsNotNone(enable_override)
        self.assertIsNotNone(output_field)
        self.assertIsNotNone(disabled_overlay)
        self.assertIsNotNone(file_picker_button)
        self.assertIsNotNone(open_in_explorer_button)

        # Checkbox is not checked by default
        self.assertEqual(False, enable_override.model.get_value_as_bool())
        # String Field is populated with "path_to_project/package" by default
        self.assertEqual(
            OmniUrl(get_test_data_path(__name__, "usd/package")).path.lower(),
            output_field.model.get_value_as_string().lower(),
        )
        self.assertEqual(False, output_field.widget.enabled)
        # Overlay is enabled by default
        self.assertEqual(True, disabled_overlay.widget.visible)
        # File Picker button is disabled by default
        self.assertEqual(False, file_picker_button.widget.enabled)
        # Open In Explorer button is disabled by default because directory doesn't exist
        self.assertEqual(False, open_in_explorer_button.widget.enabled)

        await self.__destroy_widget(window, widget)

    async def test_invalid_value_should_reset_to_last_known_valid_value_and_override_should_enable_fields(self):
        window, widget = await self.__setup_widget()

        output_validity_changed_mock = Mock()
        _ = widget.subscribe_output_validity_changed(output_validity_changed_mock)

        default_package_dir = get_test_data_path(__name__, "usd/package")

        enable_override = ui_test.find(f"{window.title}//Frame/**/CheckBox[*].identifier=='enable_override'")
        output_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='output_field'")
        disabled_overlay = ui_test.find(f"{window.title}//Frame/**/Rectangle[*].identifier=='disabled_overlay'")
        file_picker_button = ui_test.find(f"{window.title}//Frame/**/Image[*].identifier=='file_picker_button'")
        open_in_explorer_button = ui_test.find(
            f"{window.title}//Frame/**/Button[*].identifier=='open_in_explorer_button'"
        )

        self.assertIsNotNone(enable_override)
        self.assertIsNotNone(output_field)
        self.assertIsNotNone(disabled_overlay)
        self.assertIsNotNone(file_picker_button)
        self.assertIsNotNone(open_in_explorer_button)

        # Enter valid values
        await enable_override.click()
        await ui_test.human_delay()

        # Checkbox should now be checked
        self.assertEqual(True, enable_override.model.get_value_as_bool())
        # String Field should be enabled
        self.assertEqual(True, output_field.widget.enabled)
        # Overlay should be disabled
        self.assertEqual(False, disabled_overlay.widget.visible)
        # File Picker button should be enabled
        self.assertEqual(True, file_picker_button.widget.enabled)
        # Open In Explorer button should still be disabled because directory doesn't exist
        self.assertEqual(False, open_in_explorer_button.widget.enabled)

        # Try to input invalid values & don't end edit
        await ui_test.human_delay(30)  # If input is too quick, default text stays?
        await output_field.input("C:/Test/file&.png", end_key=KeyboardInput.DOWN)
        await ui_test.human_delay()
        self.assertEqual("FieldError", output_field.widget.style_type_name_override)
        self.assertEqual("The output directory is not a valid path", output_field.widget.tooltip)

        self.assertEqual(1, output_validity_changed_mock.call_count)
        self.assertEqual(call(False), output_validity_changed_mock.call_args)

        # End edit & make sure we reset the value and state
        await output_field.input("", end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()
        self.assertEqual(OmniUrl(default_package_dir).path.lower(), output_field.model.get_value_as_string().lower())
        self.assertEqual("Field", output_field.widget.style_type_name_override)
        self.assertEqual("", output_field.widget.tooltip)

        self.assertEqual(3, output_validity_changed_mock.call_count)
        self.assertEqual(call(True), output_validity_changed_mock.call_args)

        await self.__destroy_widget(window, widget)

    async def test_open_in_explorer_button_state_should_update_on_field_change_and_click(self):
        window, widget = await self.__setup_widget()

        temp_package_dir = (Path(self.temp_dir.name) / "package").as_posix()

        enable_override = ui_test.find(f"{window.title}//Frame/**/CheckBox[*].identifier=='enable_override'")
        output_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='output_field'")
        disabled_overlay = ui_test.find(f"{window.title}//Frame/**/Rectangle[*].identifier=='disabled_overlay'")
        file_picker_button = ui_test.find(f"{window.title}//Frame/**/Image[*].identifier=='file_picker_button'")
        open_in_explorer_button = ui_test.find(
            f"{window.title}//Frame/**/Button[*].identifier=='open_in_explorer_button'"
        )

        self.assertIsNotNone(enable_override)
        self.assertIsNotNone(output_field)
        self.assertIsNotNone(disabled_overlay)
        self.assertIsNotNone(file_picker_button)
        self.assertIsNotNone(open_in_explorer_button)

        # Enable the fields
        await enable_override.click()
        await ui_test.human_delay()

        # Create the directory to enable the Open In Explorer button
        os.makedirs(temp_package_dir)
        await ui_test.human_delay()

        # Input a valid, existing value
        await ui_test.human_delay(30)  # If input is too quick, default text stays?
        await output_field.input(temp_package_dir)
        await ui_test.human_delay()

        # Open In Explorer button should now be enabled because directory exists
        self.assertEqual(True, open_in_explorer_button.widget.enabled)

        # Delete the directory to test on click when directory was deleted
        os.rmdir(temp_package_dir)

        # Open In Explorer button won't refresh until clicked
        self.assertEqual(True, open_in_explorer_button.widget.enabled)

        await open_in_explorer_button.click()
        await ui_test.human_delay()

        # Open In Explorer button should now be disabled because directory was deleted
        self.assertEqual(False, open_in_explorer_button.widget.enabled)

        await self.__destroy_widget(window, widget)

    async def test_output_path_should_return_output_path(self):
        window, widget = await self.__setup_widget()

        self.assertEqual(
            OmniUrl(get_test_data_path(__name__, "usd/package")).path.lower(),
            widget.output_path.lower(),
        )

        await self.__destroy_widget(window, widget)
