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

import omni.kit.test
import omni.usd
from carb.input import KeyboardInput
from lightspeed.layer_manager.core import LSS_LAYER_MOD_NAME, LSS_LAYER_MOD_NOTES, LSS_LAYER_MOD_VERSION
from lightspeed.trex.mod_packaging_details.widget import ModPackagingDetailsWidget
from omni import ui
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path
from pxr import Sdf


class TestModPackagingDetailsWidget(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.open_stage_async(get_test_data_path(__name__, "usd/project.usda"))

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.context = None

    async def __setup_widget(self):
        await arrange_windows(topleft_window="Stage")

        window = ui.Window("TestModPackagingDetailsWindow", height=400, width=400)
        with window.frame:
            mod_details = ModPackagingDetailsWidget(context_name="")
        await ui_test.human_delay()
        mod_details.show(True)

        return window, mod_details

    async def __destroy_widget(self, window, widget):
        widget.destroy()
        window.destroy()

    async def test_default_values_should_be_populated(self):
        window, widget = await self.__setup_widget()

        name_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='name_field'")
        version_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='version_field'")
        details_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='details_field'")

        default_mod_name = "project"
        default_mod_version = "1.0.0"
        default_mod_description = ""

        self.assertIsNotNone(name_field)
        self.assertIsNotNone(version_field)
        self.assertIsNotNone(details_field)

        self.assertEqual(default_mod_name, name_field.model.get_value_as_string())
        self.assertEqual(default_mod_version, version_field.model.get_value_as_string())
        self.assertEqual(default_mod_description, details_field.model.get_value_as_string())

        self.assertEqual(default_mod_name, widget.mod_name)
        self.assertEqual(default_mod_version, widget.mod_version)
        self.assertEqual(default_mod_description, widget.mod_details)

        await self.__destroy_widget(window, widget)

    async def test_saved_values_should_be_loaded(self):
        project_layer = self.context.get_stage().GetRootLayer()
        mod_layer = Sdf.Layer.FindOrOpen(project_layer.ComputeAbsolutePath(project_layer.subLayerPaths[0]))

        mod_name = "Main Project"
        mod_version = "1.0.0"
        mod_details = "Main Test Notes"

        custom_data = mod_layer.customLayerData
        custom_data.update(
            {
                LSS_LAYER_MOD_NAME: mod_name,
                LSS_LAYER_MOD_VERSION: mod_version,
                LSS_LAYER_MOD_NOTES: mod_details,
            }
        )
        mod_layer.customLayerData = custom_data

        window, widget = await self.__setup_widget()

        name_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='name_field'")
        version_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='version_field'")
        details_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='details_field'")

        self.assertIsNotNone(name_field)
        self.assertIsNotNone(version_field)
        self.assertIsNotNone(details_field)

        self.assertEqual(mod_name, name_field.model.get_value_as_string())
        self.assertEqual(mod_version, version_field.model.get_value_as_string())
        self.assertEqual(mod_details, details_field.model.get_value_as_string())

        self.assertEqual(mod_name, widget.mod_name)
        self.assertEqual(mod_version, widget.mod_version)
        self.assertEqual(mod_details, widget.mod_details)

        await self.__destroy_widget(window, widget)

    async def test_invalid_values_should_reset_to_last_known_valid_value(self):
        mod_name = "Valid Project"
        mod_version = "2.0.0"

        window, widget = await self.__setup_widget()

        name_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='name_field'")
        version_field = ui_test.find(f"{window.title}//Frame/**/StringField[*].identifier=='version_field'")

        self.assertIsNotNone(name_field)
        self.assertIsNotNone(version_field)

        # Enter valid values
        await ui_test.human_delay(30)  # If input is too quick, default text stays?

        await name_field.input(mod_name)
        await ui_test.human_delay()

        await version_field.input(mod_version)
        await ui_test.human_delay()

        # Try to input invalid values & don't end edit
        await name_field.input(" ", end_key=KeyboardInput.DOWN)
        await ui_test.human_delay()
        self.assertEqual("FieldError", name_field.widget.style_type_name_override)
        self.assertEqual("The value cannot be empty", name_field.widget.tooltip)

        # End edit & make sure we reset the value and state
        await name_field.input("", end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()
        self.assertEqual(mod_name, name_field.widget.model.get_value_as_string())
        self.assertEqual("Field", name_field.widget.style_type_name_override)
        self.assertEqual("", name_field.widget.tooltip)

        # Try to input invalid values & don't end edit
        await version_field.input("invalid_test", end_key=KeyboardInput.DOWN)
        await ui_test.human_delay()
        self.assertEqual("FieldError", version_field.widget.style_type_name_override)
        self.assertEqual(
            'The version must use the following format: "{MAJOR}.{MINOR}.{PATCH}". Example: 1.0.1',
            version_field.widget.tooltip,
        )

        # End edit & make sure we reset the value and state
        await version_field.input("", end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()
        self.assertEqual(mod_version, version_field.widget.model.get_value_as_string())
        self.assertEqual("Field", version_field.widget.style_type_name_override)
        self.assertEqual("", version_field.widget.tooltip)

        await self.__destroy_widget(window, widget)
