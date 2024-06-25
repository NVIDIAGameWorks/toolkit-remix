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

import tempfile
from pathlib import Path
from typing import Optional

import omni.kit.usd.layers as layers
import omni.ui as ui
import omni.usd
from carb.input import KeyboardInput
from omni.flux.layer_tree.usd.widget import LayerDelegate, LayerModel, LayerTreeWidget
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, wait_stage_loading
from pxr import Sdf


class TestWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.context = omni.usd.get_context()
        self.stage = self.context.get_stage()
        self.temp_dir = tempfile.TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.temp_dir.cleanup()
        self.context = None
        self.stage = None
        self.temp_dir = None

    async def __setup_widget(self, model: Optional[LayerModel] = None, delegate: Optional[LayerDelegate] = None):
        await arrange_windows(topleft_window="Stage")

        window = ui.Window("TestLayerTreeWindow", height=400, width=400)
        with window.frame:
            layer_tree = LayerTreeWidget(context_name="", model=model, delegate=delegate)

        await ui_test.human_delay()

        layer_tree.show(True)

        return window

    async def test_create_new_layer(self):
        root = self.stage.GetRootLayer()

        window = await self.__setup_widget()  # Keep in memory during test

        # Layer 0 should be unlocked by default
        self.assertEqual(0, len(root.subLayerPaths))

        disabled_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='CreateLayerDisabled'")
        create_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='CreateLayer'")

        # The create layer button should be disabled if no valid layer is selected
        self.assertIsNotNone(disabled_button)
        self.assertIsNone(create_button)

        # Clicking the disabled button shouldn't do anything
        await disabled_button.click()

        # There should only be 1 layer item
        self.assertEqual(1, len(ui_test.find_all(f"{window.title}//Frame/**/ZStack[*].identifier=='layer_item_root'")))

        # Select the root item
        layer_item = ui_test.find(f"{window.title}//Frame/**/ZStack[*].identifier=='layer_item_root'")
        await layer_item.click()

        disabled_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='CreateLayerDisabled'")
        create_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='CreateLayer'")

        # The create layer button should be now be enabled
        self.assertIsNone(disabled_button)
        self.assertIsNotNone(create_button)

        await create_button.click()

        await ui_test.human_delay()

        # The create new file window should now be opened
        file_picker_window_title = "Create a new layer file"
        create_button = ui_test.find(f"{file_picker_window_title}//Frame/**/Button[*].text=='Create'")
        dir_path_field = ui_test.find(
            f"{file_picker_window_title}//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
        )
        file_name_field = ui_test.find(
            f"{file_picker_window_title}//Frame/**/StringField[*].style_type_name_override=='Field'"
        )

        self.assertIsNotNone(create_button)
        self.assertIsNotNone(dir_path_field)
        self.assertIsNotNone(file_name_field)

        dir_name = str((Path(self.temp_dir.name)).resolve())
        file_name = "layer0.usda"

        # It takes a while for the tree to update
        await ui_test.human_delay(50)
        await dir_path_field.input(dir_name, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(50)

        await file_name_field.input(file_name, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()

        # Make sure we create the layer in the correct directory
        self.assertEqual(dir_name + "/", dir_path_field.model._path)  # noqa PLW0212
        self.assertEqual(file_name, file_name_field.model.get_value_as_string())

        await create_button.click()

        await ui_test.human_delay()

        # Make sure the layer was created correctly
        layer_path = str(Path(dir_name) / file_name)
        self.assertEqual(1, len(root.subLayerPaths))
        self.assertEqual(Path(layer_path), Path(root.subLayerPaths[0]))

        # The root item should be expanded so we should be able to find the new item in the UI
        item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].name=='PropertiesPaneSectionTreeItem'")
        self.assertEqual(2, len(item_labels))
        self.assertEqual("Root Layer", item_labels[0].widget.text)
        self.assertEqual(file_name, item_labels[1].widget.text)

    async def test_toggle_lock_state(self):
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer1_path = Path(self.temp_dir.name) / "layer1.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer1 = Sdf.Layer.CreateNew(str(layer1_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)
        root.subLayerPaths.append(layer1.identifier)

        layers_state = layers.get_layers(self.context).get_layers_state()

        # Setup layer1 to be excluded from locks
        model = LayerModel(exclude_lock_fn=lambda *_: [root.identifier, layer1.identifier])

        window = await self.__setup_widget(model=model)  # Keep in memory during test

        # Both layers should be unlocked by default
        self.assertFalse(layers_state.is_layer_locked(layer0.identifier))
        self.assertFalse(layers_state.is_layer_locked(layer1.identifier))

        # Root layer should not be lock-able or unlock-able & children layers are hidden
        self.assertEqual(0, len(ui_test.find_all(f"{window.title}//Frame/**/Image[*].name=='Unlock'")))
        self.assertEqual(0, len(ui_test.find_all(f"{window.title}//Frame/**/Image[*].name=='Lock'")))

        # Find the expansion button for the root and show the layer items
        expand_button = ui_test.find(f"{window.title}//Frame/**/HStack[*].identifier=='expansion_stack'")
        await expand_button.click()

        # There should only be 1 unlock button, because layer1 is excluded
        self.assertEqual(1, len(ui_test.find_all(f"{window.title}//Frame/**/Image[*].name=='Unlock'")))

        lock_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Unlock'")
        unlock_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Lock'")

        # A lock button should be visible now that the layer0 item is visible and unlocked
        self.assertIsNotNone(lock_button)
        self.assertIsNone(unlock_button)

        await lock_button.click()

        # layer0 should now be locked
        self.assertTrue(layers_state.is_layer_locked(layer0.identifier))

        # layer0 should now be locked so the unlock button should be replaced
        self.assertEqual(0, len(ui_test.find_all(f"{window.title}//Frame/**/Image[*].name=='Unlock'")))

        lock_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Unlock'")
        unlock_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Lock'")

        # An unlock button should be visible now that the layer0 item is visible and locked
        self.assertIsNone(lock_button)
        self.assertIsNotNone(unlock_button)

        await unlock_button.click()

        # Layer 0 should now be unlocked
        self.assertFalse(layers_state.is_layer_locked(layer0.identifier))

        lock_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Unlock'")
        unlock_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Lock'")

        # The UI should also have toggled again
        self.assertIsNotNone(lock_button)
        self.assertIsNone(unlock_button)
