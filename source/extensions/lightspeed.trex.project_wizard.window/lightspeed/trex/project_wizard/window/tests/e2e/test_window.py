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
import os
import shutil
import subprocess

# import subprocess
import tempfile
from enum import Enum
from pathlib import Path
from typing import Tuple

import carb.settings
from carb.input import KeyboardInput
from lightspeed.common import constants
from lightspeed.layer_manager import layer_types
from lightspeed.trex.project_wizard.core import SETTING_JUNCTION_NAME as _SETTING_JUNCTION_NAME
from lightspeed.trex.project_wizard.window import ProjectWizardWindow
from omni import ui, usd
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, wait_stage_loading
from pxr import Sdf


class TestComponents(Enum):

    """
    Simple Enum used to find the components of interest during tests
    """

    CANCEL_BUTTON = 1
    PREVIOUS_BUTTON = 2
    NEXT_BUTTON = 3
    OPEN_OPTION = 4
    CREATE_OPTION = 5
    EDIT_OPTION = 6
    REMASTER_OPTION = 7
    PROJECT_STRING_FIELD = 8
    REMIX_STRING_FIELD = 9
    PROJECT_FILE_ICON = 0
    REMIX_FILE_ICON = 11
    CAPTURE_TREE = 12
    AVAILABLE_MODS_TREE = 13
    SELECTED_MODS_TREE = 14
    FILE_PICKER_DIRECTORY = 15
    FILE_PICKER_FILENAME = 16
    FILE_PICKER_OPEN = 17


class TestWizardWindow(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self._isettings = carb.settings.get_settings()
        self._isettings.set(_SETTING_JUNCTION_NAME, True)
        await usd.get_context().new_stage_async()
        self.stage = usd.get_context().get_stage()
        self.temp_dir = tempfile.TemporaryDirectory()

        self.project_path, self.remix_dir = await self.__setup_directories()
        self.window, self.wizard = await self.__setup_widget()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if usd.get_context().get_stage():
            await usd.get_context().close_stage_async()

        self.window.destroy()

        await self.__cleanup_directories()
        self.temp_dir.cleanup()

        self._isettings.set(_SETTING_JUNCTION_NAME, False)

        self.stage = None
        self.temp_dir = None
        self.project_path = None
        self.remix_dir = None
        self.window = None
        self.wizard = None

    async def __setup_widget(self) -> Tuple[ui.Window, ProjectWizardWindow]:
        await arrange_windows(topleft_window="Stage")

        window = ui.Window("TestWizardWindow", width=1000, height=800)
        with window.frame:
            wizard = ProjectWizardWindow(width=1000, height=800)

        await ui_test.human_delay()

        # Avoid having the same title for multiple windows. Fixes test flakiness.
        wizard._wizard_window._window.title = f"{wizard._wizard_window._window.title}_{id(self)}"  # noqa PLW0212

        return window, wizard

    async def __setup_directories(self):
        project_dir = Path(self.temp_dir.name) / "projects" / "MyProject"
        project_path = (project_dir / "my_project.usda").resolve()

        remix_dir = (Path(self.temp_dir.name) / constants.REMIX_FOLDER).resolve()
        captures_dir = remix_dir / constants.REMIX_CAPTURE_FOLDER
        mods_dir = remix_dir / constants.REMIX_MODS_FOLDER
        lib_dir = remix_dir / "lib"

        mod_1_dir = mods_dir / "ExistingMod1"
        mod_2_dir = mods_dir / "ExistingMod2"

        os.makedirs(project_dir)
        os.makedirs(captures_dir)
        os.makedirs(lib_dir)
        os.makedirs(mod_1_dir)
        os.makedirs(mod_2_dir)

        (lib_dir / "d3d9.dll").touch()

        test_capture_path = Path(get_test_data_path(__name__, "usd/capture.usda")).resolve()
        test_mod_path = Path(get_test_data_path(__name__, "usd/mod.usda")).resolve()

        shutil.copy(str(test_capture_path), str(captures_dir / "capture.usda"))
        shutil.copy(str(test_mod_path), str(mod_1_dir / constants.REMIX_MOD_FILE))
        shutil.copy(str(test_mod_path), str(mod_2_dir / constants.REMIX_MOD_FILE))

        return project_path, remix_dir

    async def __create_project(self, create_symlinks: bool):
        test_project_path = Path(get_test_data_path(__name__, "usd/project.usda"))
        shutil.copy(str(test_project_path), str(self.project_path))

        if create_symlinks:
            remix_project = self.remix_dir / constants.REMIX_MODS_FOLDER / self.project_path.parent.stem
            subprocess.check_call(
                f'mklink /J "{remix_project}" "{self.project_path.parent}"',
                shell=True,
            )
            subprocess.check_call(
                f'mklink /J "{self.project_path.parent / constants.REMIX_DEPENDENCIES_FOLDER}" "{self.remix_dir}"',
                shell=True,
            )

    async def __cleanup_directories(self):
        shutil.rmtree(self.remix_dir / constants.REMIX_MODS_FOLDER / self.project_path.parent.stem, ignore_errors=True)
        shutil.rmtree(self.project_path.parent / constants.REMIX_DEPENDENCIES_FOLDER, ignore_errors=True)

    async def __find_file_picker_buttons(self, window_title):
        components = {
            TestComponents.FILE_PICKER_DIRECTORY: ui_test.find(
                f"{window_title}//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
            ),
            TestComponents.FILE_PICKER_FILENAME: ui_test.find(
                f"{window_title}//Frame/**/StringField[*].style_type_name_override=='Field'"
            ),
            TestComponents.FILE_PICKER_OPEN: ui_test.find(f"{window_title}//Frame/**/Button[*].text=='Open'"),
        }

        for component, button in components.items():
            self.assertIsNotNone(button, msg=f"Unexpectedly None: {component}")

        return components

    async def __find_navigation_buttons(self, window, should_exist: bool = True):
        components = {
            TestComponents.CANCEL_BUTTON: ui_test.find(
                f"{window.title}//Frame/**/Button[*].identifier=='CancelButton'"
            ),
            TestComponents.PREVIOUS_BUTTON: ui_test.find(
                f"{window.title}//Frame/**/Button[*].identifier=='PreviousButton'"
            ),
            TestComponents.NEXT_BUTTON: ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='NextButton'"),
        }

        if should_exist:
            for component, button in components.items():
                self.assertIsNotNone(button, msg=f"Unexpectedly None: {component}")
        else:
            for component, button in components.items():
                self.assertIsNone(button, msg=f"Unexpectedly Found: {component}")

        return components

    async def __find_start_page_components(self, window):
        option_buttons = ui_test.find_all(f"{window.title}//Frame/**/VStack[*].identifier=='OptionButton'")
        self.assertEqual(4, len(option_buttons))

        return {
            TestComponents.OPEN_OPTION: option_buttons[0],
            TestComponents.CREATE_OPTION: option_buttons[1],
            TestComponents.EDIT_OPTION: option_buttons[2],
            TestComponents.REMASTER_OPTION: option_buttons[3],
        }

    async def __find_setup_page_components(self, window, validate_capture_tree: bool = False):
        string_fields = ui_test.find_all(f"{window.title}//Frame/**/StringField[*].identifier=='FilePickerInput'")
        self.assertEqual(2, len(string_fields))

        icons = ui_test.find_all(f"{window.title}//Frame/**/Image[*].identifier=='FilePickerIcon'")
        self.assertEqual(2, len(icons))

        components = {
            TestComponents.PROJECT_STRING_FIELD: string_fields[0],
            TestComponents.REMIX_STRING_FIELD: string_fields[1],
            TestComponents.PROJECT_FILE_ICON: icons[0],
            TestComponents.REMIX_FILE_ICON: icons[1],
            TestComponents.CAPTURE_TREE: ui_test.find(
                f"{window.title}//Frame/**/TreeView[*].identifier=='CaptureTree'"
            ),
        }

        for component, button in components.items():
            # The capture tree be rendered load after the paths are input
            if component == TestComponents.CAPTURE_TREE and not validate_capture_tree:
                continue
            self.assertIsNotNone(button, msg=f"Unexpectedly None: {component}")

        return components

    async def __find_existing_mods_components(self, window):
        return {
            TestComponents.AVAILABLE_MODS_TREE: ui_test.find(
                f"{window.title}//Frame/**/TreeView[*].identifier=='AvailableModsTree'"
            ),
            TestComponents.SELECTED_MODS_TREE: ui_test.find(
                f"{window.title}//Frame/**/TreeView[*].identifier=='SelectedModsTree'"
            ),
        }

    async def test_navigation_should_go_through_all_pages_and_back(self):
        # Setup the test
        wizard_window = self.wizard._wizard_window._window  # noqa PLW0212

        # Start the test
        self.wizard.show_project_wizard(reset_page=True)

        await ui_test.human_delay()

        components = await self.__find_start_page_components(wizard_window)
        _ = await self.__find_navigation_buttons(wizard_window, should_exist=False)

        ###############################################################################
        # Open
        ###############################################################################

        # Create a project to open
        await self.__create_project(False)

        await components[TestComponents.OPEN_OPTION].click()
        await ui_test.human_delay()

        # Select a project in the File Picker
        picker_buttons = await self.__find_file_picker_buttons("Open an RTX Remix project")

        await ui_test.human_delay(50)
        await picker_buttons[TestComponents.FILE_PICKER_DIRECTORY].input(
            str(self.project_path.parent), end_key=KeyboardInput.ENTER
        )
        await ui_test.human_delay(50)
        await picker_buttons[TestComponents.FILE_PICKER_FILENAME].input(
            str(self.project_path.name), end_key=KeyboardInput.DOWN
        )
        await ui_test.human_delay()

        # Make sure we are selecting the right file
        self.assertEqual(
            str(self.project_path.parent),
            picker_buttons[  # noqa PLW0212
                TestComponents.FILE_PICKER_DIRECTORY
            ].model._field.model.get_value_as_string(),
        )
        self.assertEqual(
            str(self.project_path.name), picker_buttons[TestComponents.FILE_PICKER_FILENAME].model.get_value_as_string()
        )

        # Open the project without symlinks, expect to open the setup page
        await picker_buttons[TestComponents.FILE_PICKER_OPEN].click()
        await ui_test.human_delay()

        _ = await self.__find_setup_page_components(wizard_window)
        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        self.assertEqual("Open", nav_buttons[TestComponents.NEXT_BUTTON].widget.text)

        # "Open" button should be blocked
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        await ui_test.human_delay()

        _ = await self.__find_setup_page_components(wizard_window)

        # Go back to the main page
        await nav_buttons[TestComponents.PREVIOUS_BUTTON].click()
        await ui_test.human_delay()

        components = await self.__find_start_page_components(wizard_window)
        _ = await self.__find_navigation_buttons(wizard_window, should_exist=False)

        # Cleanup created project
        self.project_path.unlink()

        ###############################################################################
        # Create
        ###############################################################################
        await components[TestComponents.CREATE_OPTION].click()
        await ui_test.human_delay()

        _ = await self.__find_setup_page_components(wizard_window)
        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        self.assertEqual("Create", nav_buttons[TestComponents.NEXT_BUTTON].widget.text)

        # "Create" button should be blocked
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        await ui_test.human_delay()

        _ = await self.__find_setup_page_components(wizard_window)

        # Go back to the main page
        await nav_buttons[TestComponents.PREVIOUS_BUTTON].click()
        await ui_test.human_delay()

        components = await self.__find_start_page_components(wizard_window)
        _ = await self.__find_navigation_buttons(wizard_window, should_exist=False)

        ###############################################################################
        # Edit
        ###############################################################################
        await components[TestComponents.EDIT_OPTION].click()
        await ui_test.human_delay()

        _ = await self.__find_setup_page_components(wizard_window)
        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        self.assertEqual("Select Mods", nav_buttons[TestComponents.NEXT_BUTTON].widget.text)

        # "Select Mods" button should be blocked
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        await ui_test.human_delay()

        components = await self.__find_setup_page_components(wizard_window)

        # Fill up the fields
        await components[TestComponents.PROJECT_STRING_FIELD].input(str(self.project_path), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()

        await components[TestComponents.REMIX_STRING_FIELD].input(str(self.remix_dir), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()

        # Capture tree should now be rendered
        _ = await self.__find_setup_page_components(wizard_window, validate_capture_tree=True)

        capture_labels = ui_test.find_all(f"{wizard_window.title}//Frame/**/Label[*].identifier=='item_title'")
        self.assertGreater(len(capture_labels), 0)

        # "Select Mods" button should still be blocked
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        await ui_test.human_delay()

        # Select a capture
        await capture_labels[0].click()
        await ui_test.human_delay()

        # Go to the mod selection page, should be unblocked not that a capture is selected
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        await ui_test.human_delay()

        _ = await self.__find_existing_mods_components(wizard_window)
        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        self.assertEqual("Create", nav_buttons[TestComponents.NEXT_BUTTON].widget.text)

        # "Create" button should be blocked
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        await ui_test.human_delay()

        _ = await self.__find_existing_mods_components(wizard_window)

        # Go back to the setup page
        await nav_buttons[TestComponents.PREVIOUS_BUTTON].click()
        await ui_test.human_delay()

        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        # Go back to the main page
        await nav_buttons[TestComponents.PREVIOUS_BUTTON].click()
        await ui_test.human_delay()

        components = await self.__find_start_page_components(wizard_window)
        _ = await self.__find_navigation_buttons(wizard_window, should_exist=False)

        ###############################################################################
        # Remaster
        ###############################################################################
        await components[TestComponents.REMASTER_OPTION].click()
        await ui_test.human_delay()

        # Payload should remain from edit page so capture tree should be rendered
        _ = await self.__find_setup_page_components(wizard_window, validate_capture_tree=True)
        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        self.assertEqual("Select Mods", nav_buttons[TestComponents.NEXT_BUTTON].widget.text)

        # Go to the mod selection page
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        await ui_test.human_delay()

        _ = await self.__find_existing_mods_components(wizard_window)
        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        self.assertEqual("Create", nav_buttons[TestComponents.NEXT_BUTTON].widget.text)

        # "Create" button should be blocked
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        await ui_test.human_delay()

        _ = await self.__find_existing_mods_components(wizard_window)

        # Go back to the setup page
        await nav_buttons[TestComponents.PREVIOUS_BUTTON].click()
        await ui_test.human_delay()

        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        # Go back to the main page
        await nav_buttons[TestComponents.PREVIOUS_BUTTON].click()
        await ui_test.human_delay()

        _ = await self.__find_start_page_components(wizard_window)
        _ = await self.__find_navigation_buttons(wizard_window, should_exist=False)

    async def test_open_project_valid_symlinks_should_open_project(self):
        # Setup the test
        wizard_window = self.wizard._wizard_window._window  # noqa PLW0212

        # Start the test
        self.wizard.show_project_wizard(reset_page=True)

        await ui_test.human_delay()

        components = await self.__find_start_page_components(wizard_window)
        _ = await self.__find_navigation_buttons(wizard_window, should_exist=False)

        # Create a project to open with symlinks
        await self.__create_project(True)

        await components[TestComponents.OPEN_OPTION].click()
        await ui_test.human_delay()

        # Select a project in the File Picker
        picker_buttons = await self.__find_file_picker_buttons("Open an RTX Remix project")

        await ui_test.human_delay(50)
        await picker_buttons[TestComponents.FILE_PICKER_DIRECTORY].input(
            str(self.project_path.parent), end_key=KeyboardInput.ENTER
        )
        await ui_test.human_delay(50)
        await picker_buttons[TestComponents.FILE_PICKER_FILENAME].input(
            str(self.project_path.name), end_key=KeyboardInput.DOWN
        )
        await ui_test.human_delay()

        # Make sure we are selecting the right file
        self.assertEqual(
            str(self.project_path.parent),
            picker_buttons[  # noqa PLW0212
                TestComponents.FILE_PICKER_DIRECTORY
            ].model._field.model.get_value_as_string(),
        )
        self.assertEqual(
            str(self.project_path.name), picker_buttons[TestComponents.FILE_PICKER_FILENAME].model.get_value_as_string()
        )

        # Open the project without symlinks, expect to open the setup page
        await picker_buttons[TestComponents.FILE_PICKER_OPEN].click()
        await ui_test.human_delay()

        # Make sure the loaded stage is the project file
        self.assertEqual(self.project_path.as_posix(), usd.get_context().get_stage().GetRootLayer().identifier)

    async def test_open_project_invalid_symlinks_should_show_setup_and_open_project(self):
        # Setup the test
        wizard_window = self.wizard._wizard_window._window  # noqa PLW0212

        # Start the test
        self.wizard.show_project_wizard(reset_page=True)

        await ui_test.human_delay()

        components = await self.__find_start_page_components(wizard_window)
        _ = await self.__find_navigation_buttons(wizard_window, should_exist=False)

        # Create a project to open without symlinks
        await self.__create_project(False)

        await components[TestComponents.OPEN_OPTION].click()
        await ui_test.human_delay()

        # Select a project in the File Picker
        picker_buttons = await self.__find_file_picker_buttons("Open an RTX Remix project")

        await ui_test.human_delay(50)
        await picker_buttons[TestComponents.FILE_PICKER_DIRECTORY].input(
            str(self.project_path.parent), end_key=KeyboardInput.ENTER
        )
        await ui_test.human_delay(50)
        await picker_buttons[TestComponents.FILE_PICKER_FILENAME].input(
            str(self.project_path.name), end_key=KeyboardInput.DOWN
        )
        await ui_test.human_delay()

        # Make sure we are selecting the right file
        self.assertEqual(
            str(self.project_path.parent),
            picker_buttons[  # noqa PLW0212
                TestComponents.FILE_PICKER_DIRECTORY
            ].model._field.model.get_value_as_string(),
        )
        self.assertEqual(
            str(self.project_path.name), picker_buttons[TestComponents.FILE_PICKER_FILENAME].model.get_value_as_string()
        )

        # Open the project without symlinks, expect to open the setup page
        await picker_buttons[TestComponents.FILE_PICKER_OPEN].click()
        await ui_test.human_delay()

        components = await self.__find_setup_page_components(wizard_window)
        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        self.assertEqual("Open", nav_buttons[TestComponents.NEXT_BUTTON].widget.text)

        # "Open" button should be blocked
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        await ui_test.human_delay()

        _ = await self.__find_setup_page_components(wizard_window)

        await components[TestComponents.PROJECT_STRING_FIELD].input(str(self.project_path), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()

        await components[TestComponents.REMIX_STRING_FIELD].input(str(self.remix_dir), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()

        # Open the project
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        await ui_test.human_delay()

        await wait_stage_loading()

        # Make sure the loaded stage is the project file
        self.assertEqual(self.project_path.as_posix(), usd.get_context().get_stage().GetRootLayer().identifier)

    async def test_create_project_should_create_project(self):
        # Setup the test
        wizard_window = self.wizard._wizard_window._window  # noqa PLW0212

        # Start the test
        self.wizard.show_project_wizard(reset_page=True)

        await ui_test.human_delay()

        # Select the create option
        components = await self.__find_start_page_components(wizard_window)

        await components[TestComponents.CREATE_OPTION].click()
        await ui_test.human_delay()

        # Fill up the fields
        components = await self.__find_setup_page_components(wizard_window)
        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        await components[TestComponents.PROJECT_STRING_FIELD].input(str(self.project_path), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()

        await components[TestComponents.REMIX_STRING_FIELD].input(str(self.remix_dir), end_key=KeyboardInput.ENTER)
        # Let the captures widget load
        await ui_test.human_delay(50)

        capture_labels = ui_test.find_all(
            f"{wizard_window.title}//Frame/**/Label[*].name=='PropertiesPaneSectionTreeItem'"
        )

        self.assertGreater(len(capture_labels), 0)

        # Select a capture layer
        await capture_labels[0].click()
        await ui_test.human_delay()

        # Create the project
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        await ui_test.human_delay(50)

        # Make sure the project and symlinks were created
        remix_project = self.remix_dir / constants.REMIX_MODS_FOLDER / self.project_path.parent.stem

        self.assertTrue(self.project_path.exists())
        self.assertTrue((self.project_path.parent / constants.REMIX_DEPENDENCIES_FOLDER).exists())
        self.assertTrue((remix_project / self.project_path.name).exists())
        self.assertTrue((remix_project / constants.REMIX_MOD_FILE).exists())

        # Make sure the wizard was hidden
        self.assertFalse(wizard_window.visible)

        # Evaluate the layer content
        project_layer = Sdf.Layer.FindOrOpen(str(self.project_path))

        expected_mod_file = f"./{constants.REMIX_MOD_FILE}"
        expected_capture_file = f"./{constants.REMIX_DEPENDENCIES_FOLDER}/{constants.REMIX_CAPTURE_FOLDER}/capture.usda"

        # Make sure the project has the right sub-layers
        self.assertEqual(2, len(project_layer.subLayerPaths))
        self.assertEqual(expected_mod_file, project_layer.subLayerPaths[0])
        self.assertEqual(expected_capture_file, project_layer.subLayerPaths[1])

        # Make sure the project has the right file type metadata
        self.assertEqual(
            layer_types.LayerType.workfile.value,
            project_layer.customLayerData.get(layer_types.LayerTypeKeys.layer_type.value, None),
        )

        omni_layers_data = project_layer.customLayerData["omni_layer"]

        # Make sure the project has the right authoring layer and the capture layer is locked
        self.assertEqual(expected_mod_file, omni_layers_data.get("authoring_layer", None))
        self.assertDictEqual({expected_capture_file: True}, omni_layers_data.get("locked", None))

    async def test_edit_project_should_create_project_and_copy_mod(self):
        # Setup the test
        wizard_window = self.wizard._wizard_window._window  # noqa PLW0212

        # Start the test
        self.wizard.show_project_wizard(reset_page=True)

        await ui_test.human_delay()

        # Select the create option
        components = await self.__find_start_page_components(wizard_window)

        await components[TestComponents.EDIT_OPTION].click()
        await ui_test.human_delay()

        # Fill up the fields
        components = await self.__find_setup_page_components(wizard_window)
        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        await components[TestComponents.PROJECT_STRING_FIELD].input(str(self.project_path), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()

        await components[TestComponents.REMIX_STRING_FIELD].input(str(self.remix_dir), end_key=KeyboardInput.ENTER)
        # Let the captures widget load
        await ui_test.human_delay(50)

        capture_labels = ui_test.find_all(
            f"{wizard_window.title}//Frame/**/Label[*].name=='PropertiesPaneSectionTreeItem'"
        )

        self.assertGreater(len(capture_labels), 0)

        # Select a capture layer
        await capture_labels[0].click()
        await ui_test.human_delay()

        # Go to the existing mods page
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        # Let the mod widgets load
        await ui_test.human_delay(50)

        components = await self.__find_existing_mods_components(wizard_window)
        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        available_mod_labels = components[TestComponents.AVAILABLE_MODS_TREE].find_all(
            "/Label[*].identifier=='ExistingModLabel'"
        )

        self.assertGreater(len(available_mod_labels), 0)

        await available_mod_labels[0].drag_and_drop(components[TestComponents.SELECTED_MODS_TREE].center)

        # Create the project
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        await ui_test.human_delay(50)

        # Make sure the project and symlinks were created
        remix_project = self.remix_dir / constants.REMIX_MODS_FOLDER / self.project_path.parent.stem

        self.assertTrue(self.project_path.exists())
        self.assertTrue((self.project_path.parent / constants.REMIX_DEPENDENCIES_FOLDER).exists())
        self.assertTrue((remix_project / self.project_path.name).exists())
        self.assertTrue((remix_project / constants.REMIX_MOD_FILE).exists())

        # Make sure the wizard was hidden
        self.assertFalse(wizard_window.visible)

        expected_mod_file = f"./{constants.REMIX_MOD_FILE}"
        expected_capture_file = f"./{constants.REMIX_DEPENDENCIES_FOLDER}/{constants.REMIX_CAPTURE_FOLDER}/capture.usda"

        # Evaluate the mod layer
        mod_layer = Sdf.Layer.FindOrOpen(str(self.project_path.parent / expected_mod_file))

        # Make sure it's the same mod layer as the existing mod
        self.assertEqual("test", mod_layer.customLayerData.get("test_data", None))

        # Evaluate the layer content
        project_layer = Sdf.Layer.FindOrOpen(str(self.project_path))

        # Make sure the project has the right sub-layers
        self.assertEqual(2, len(project_layer.subLayerPaths))
        self.assertEqual(expected_mod_file, project_layer.subLayerPaths[0])
        self.assertEqual(expected_capture_file, project_layer.subLayerPaths[1])

        # Make sure the project has the right file type metadata
        self.assertEqual(
            layer_types.LayerType.workfile.value,
            project_layer.customLayerData.get(layer_types.LayerTypeKeys.layer_type.value, None),
        )

        omni_layers_data = project_layer.customLayerData["omni_layer"]

        # Make sure the project has the right authoring layer and the capture layer is locked
        self.assertEqual(expected_mod_file, omni_layers_data.get("authoring_layer", None))
        self.assertDictEqual({expected_capture_file: True}, omni_layers_data.get("locked", None))

    async def test_remaster_project_should_create_project_with_dependencies(self):
        # Setup the test
        wizard_window = self.wizard._wizard_window._window  # noqa PLW0212

        # Start the test
        self.wizard.show_project_wizard(reset_page=True)

        await ui_test.human_delay()

        # Select the create option
        components = await self.__find_start_page_components(wizard_window)

        await components[TestComponents.REMASTER_OPTION].click()
        await ui_test.human_delay()

        # Fill up the fields
        components = await self.__find_setup_page_components(wizard_window)
        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        await components[TestComponents.PROJECT_STRING_FIELD].input(str(self.project_path), end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()

        await components[TestComponents.REMIX_STRING_FIELD].input(str(self.remix_dir), end_key=KeyboardInput.ENTER)
        # Let the captures widget load
        await ui_test.human_delay(50)

        capture_labels = ui_test.find_all(
            f"{wizard_window.title}//Frame/**/Label[*].name=='PropertiesPaneSectionTreeItem'"
        )

        self.assertGreater(len(capture_labels), 0)

        # Select a capture layer
        await capture_labels[0].click()
        await ui_test.human_delay()

        # Go to the existing mods page
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        # Let the mod widgets load
        await ui_test.human_delay(50)

        components = await self.__find_existing_mods_components(wizard_window)
        nav_buttons = await self.__find_navigation_buttons(wizard_window)

        available_mod_labels = components[TestComponents.AVAILABLE_MODS_TREE].find_all(
            "/Label[*].identifier=='ExistingModLabel'"
        )

        self.assertGreater(len(available_mod_labels), 0)

        await available_mod_labels[0].drag_and_drop(components[TestComponents.SELECTED_MODS_TREE].center)

        # Create the project
        await nav_buttons[TestComponents.NEXT_BUTTON].click()
        await ui_test.human_delay(50)

        # Make sure the project and symlinks were created
        remix_project = self.remix_dir / constants.REMIX_MODS_FOLDER / self.project_path.parent.stem

        self.assertTrue(self.project_path.exists())
        self.assertTrue((self.project_path.parent / constants.REMIX_DEPENDENCIES_FOLDER).exists())
        self.assertTrue((remix_project / self.project_path.name).exists())
        self.assertTrue((remix_project / constants.REMIX_MOD_FILE).exists())

        # Make sure the wizard was hidden
        self.assertFalse(wizard_window.visible)

        # Evaluate the layer content
        project_layer = Sdf.Layer.FindOrOpen(str(self.project_path))

        expected_mod_file = f"./{constants.REMIX_MOD_FILE}"
        expected_extra_mod_file = (
            f"./{constants.REMIX_DEPENDENCIES_FOLDER}/{constants.REMIX_MODS_FOLDER}/"
            + available_mod_labels[0].widget.text.replace("\\", "/")
        )
        expected_capture_file = f"./{constants.REMIX_DEPENDENCIES_FOLDER}/{constants.REMIX_CAPTURE_FOLDER}/capture.usda"

        # Make sure the project has the right sub-layers
        self.assertEqual(3, len(project_layer.subLayerPaths))
        self.assertEqual(expected_mod_file, project_layer.subLayerPaths[0])
        self.assertEqual(expected_extra_mod_file, project_layer.subLayerPaths[1])
        self.assertEqual(expected_capture_file, project_layer.subLayerPaths[2])

        # Make sure the project has the right file type metadata
        self.assertEqual(
            layer_types.LayerType.workfile.value,
            project_layer.customLayerData.get(layer_types.LayerTypeKeys.layer_type.value, None),
        )

        omni_layers_data = project_layer.customLayerData["omni_layer"]

        # Make sure the project has the right authoring layer and the capture layer is locked
        self.assertEqual(expected_mod_file, omni_layers_data.get("authoring_layer", None))
        self.assertDictEqual({expected_capture_file: True}, omni_layers_data.get("locked", None))
