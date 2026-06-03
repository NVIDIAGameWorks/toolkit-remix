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

import omni.kit.commands
import omni.kit.usd.layers as layers
import omni.ui as ui
import omni.usd
from carb.input import KeyboardInput
from omni.flux.layer_tree.usd.widget import LayerDelegate, LayerModel, LayerTreeWidget
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows
from pxr import Sdf, Usd


class TestWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.context = omni.usd.get_context()
        self.stage = self.context.get_stage()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.layer_trees = []
        self.windows = []

    # After running each test
    async def tearDown(self):
        current_menu = ui.Menu.get_current()
        if current_menu and current_menu.shown:
            current_menu.hide()
        for layer_tree in reversed(self.layer_trees):
            layer_tree.destroy()
        for window in reversed(self.windows):
            window.destroy()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.temp_dir.cleanup()
        self.context = None
        self.stage = None
        self.temp_dir = None
        self.layer_trees = []
        self.windows = []

    def __track_widget(self, window, layer_tree):
        self.windows.append(window)
        self.layer_trees.append(layer_tree)
        return window, layer_tree

    async def __setup_widget_with_tree(self, model: LayerModel | None = None, delegate: LayerDelegate | None = None):
        await arrange_windows(topleft_window="Stage")

        window = ui.Window("TestLayerTreeWindow", height=400, width=400)
        with window.frame:
            layer_tree = LayerTreeWidget(context_name="", model=model, delegate=delegate)

        await ui_test.human_delay()

        layer_tree.show(True)

        return self.__track_widget(window, layer_tree)

    async def __setup_widget(self, model: LayerModel | None = None, delegate: LayerDelegate | None = None):
        window, _ = await self.__setup_widget_with_tree(model=model, delegate=delegate)
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
        await disabled_button.click(human_delay_speed=10)

        # There should only be 1 layer item
        self.assertEqual(1, len(ui_test.find_all(f"{window.title}//Frame/**/ZStack[*].identifier=='layer_item_root'")))

        # Select the root item
        layer_item = ui_test.find(f"{window.title}//Frame/**/ZStack[*].identifier=='layer_item_root'")
        await layer_item.click(human_delay_speed=10)

        disabled_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='CreateLayerDisabled'")
        create_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='CreateLayer'")

        # The create layer button should be now be enabled
        self.assertIsNone(disabled_button)
        self.assertIsNotNone(create_button)

        await create_button.click(human_delay_speed=10)

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
        self.assertEqual(dir_name + "/", dir_path_field.model._path)
        self.assertEqual(file_name, file_name_field.model.get_value_as_string())

        await create_button.click(human_delay_speed=10)

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

        # Set layer0 as edit target so the tree expands to show it
        self.stage.SetEditTarget(Usd.EditTarget(layer0))

        layers_state = layers.get_layers(self.context).get_layers_state()

        # Setup layer1 to be excluded from locks
        model = LayerModel(exclude_lock_fn=lambda *_: [root.identifier, layer1.identifier])

        window = await self.__setup_widget(model=model)  # Keep in memory during test

        await ui_test.human_delay(20)

        # Both layers should be unlocked by default
        self.assertFalse(layers_state.is_layer_locked(layer0.identifier))
        self.assertFalse(layers_state.is_layer_locked(layer1.identifier))

        # Root is expanded by default, so layer0's unlock button should be visible
        # (layer1 is excluded from locks so has no button)
        self.assertEqual(1, len(ui_test.find_all(f"{window.title}//Frame/**/Image[*].name=='Unlock'")))
        self.assertEqual(0, len(ui_test.find_all(f"{window.title}//Frame/**/Image[*].name=='Lock'")))

        lock_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Unlock'")
        unlock_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Lock'")

        # A lock button should be visible now that the layer0 item is visible and unlocked
        self.assertIsNotNone(lock_button)
        self.assertIsNone(unlock_button)

        await lock_button.click(human_delay_speed=10)

        # layer0 should now be locked
        self.assertTrue(layers_state.is_layer_locked(layer0.identifier))

        # layer0 should now be locked so the unlock button should be replaced
        self.assertEqual(0, len(ui_test.find_all(f"{window.title}//Frame/**/Image[*].name=='Unlock'")))

        lock_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Unlock'")
        unlock_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Lock'")

        # An unlock button should be visible now that the layer0 item is visible and locked
        self.assertIsNone(lock_button)
        self.assertIsNotNone(unlock_button)

        await unlock_button.click(human_delay_speed=10)

        # Layer 0 should now be unlocked
        self.assertFalse(layers_state.is_layer_locked(layer0.identifier))

        lock_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Unlock'")
        unlock_button = ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Lock'")

        # The UI should also have toggled again
        self.assertIsNotNone(lock_button)
        self.assertIsNone(unlock_button)

    async def test_initial_expansion_with_deep_edit_target(self):
        """Test that layers expand to show a deeply nested edit target."""
        # Create a nested layer structure: root -> layer0 -> layer1 (edit target)
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer1_path = Path(self.temp_dir.name) / "layer1.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer1 = Sdf.Layer.CreateNew(str(layer1_path))

        # Nest layer1 inside layer0
        layer0.subLayerPaths.append(layer1.identifier)

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)

        # Set deep layer as edit target
        self.stage.SetEditTarget(layer1)

        window, layer_tree = await self.__setup_widget_with_tree()

        await ui_test.human_delay(20)

        # All layers should be visible (root expanded, layer0 expanded to show layer1)
        item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].name=='PropertiesPaneSectionTreeItem'")
        self.assertEqual(3, len(item_labels))
        self.assertEqual("Root Layer", item_labels[0].widget.text)
        self.assertEqual("layer0.usda", item_labels[1].widget.text)
        self.assertEqual("layer1.usda", item_labels[2].widget.text)
        self.assertEqual(["layer1.usda"], [item.title for item in layer_tree._layer_tree_widget.selection])

    async def test_initial_expansion_with_first_level_edit_target(self):
        """Test that first-level sublayer is visible when it's the edit target."""
        # Create layer0 as a sublayer of root
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer0 = Sdf.Layer.CreateNew(str(layer0_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)

        # Set layer0 as edit target
        self.stage.SetEditTarget(layer0)

        window, layer_tree = await self.__setup_widget_with_tree()

        await ui_test.human_delay(20)

        # Root should be expanded to show the edit target (layer0)
        item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].name=='PropertiesPaneSectionTreeItem'")
        self.assertEqual(2, len(item_labels))
        self.assertEqual("Root Layer", item_labels[0].widget.text)
        self.assertEqual("layer0.usda", item_labels[1].widget.text)
        self.assertEqual(["layer0.usda"], [item.title for item in layer_tree._layer_tree_widget.selection])

    async def test_initial_expansion_scrolls_startup_edit_target_into_view(self):
        # Build a real project layer stack large enough that the edit target starts below the visible rows.
        root = self.stage.GetRootLayer()
        edit_target_layer = None
        for index in range(16):
            layer = Sdf.Layer.CreateNew(str(Path(self.temp_dir.name) / f"layer{index}.usda"))
            root.subLayerPaths.append(layer.identifier)
            edit_target_layer = layer
        self.stage.SetEditTarget(Usd.EditTarget(edit_target_layer))

        # Show the layer panel in a short window, like the visible layer section in the modding layout.
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestLayerTreeWindow", height=180, width=400)
        with window.frame:
            layer_tree = LayerTreeWidget(context_name="", height=80)
            layer_tree.show(True)
        self.__track_widget(window, layer_tree)
        await ui_test.human_delay(20)

        # The edit target should be selected and the scroll frame should move down to reveal it.
        self.assertEqual(["layer15.usda"], [item.title for item in layer_tree._layer_tree_widget.selection])
        scroll_frames = [
            widget
            for widget in ui_test.find_all(f"{window.title}//Frame/**/ScrollingFrame[*].name=='TreePanelBackground'")
            if widget.widget.scroll_y_max > 0
        ]
        self.assertEqual(1, len(scroll_frames))
        self.assertGreater(scroll_frames[0].widget.scroll_y, 0)

    async def test_project_loaded_after_layer_tree_is_shown_focuses_edit_target(self):
        # Show the layer tree first, matching the app layout being built before the project is loaded.
        window, layer_tree = await self.__setup_widget_with_tree()
        await ui_test.human_delay(20)

        # Open a real USD project with a replacement layer after the tree has already consumed its startup refresh.
        project_layer = Sdf.Layer.CreateNew(str(Path(self.temp_dir.name) / "project.usda"))
        mod_layer = Sdf.Layer.CreateNew(str(Path(self.temp_dir.name) / "mod.usda"))
        project_layer.subLayerPaths.append(mod_layer.identifier)
        mod_layer.Save()
        project_layer.Save()

        success, error = await self.context.open_stage_async(project_layer.identifier)
        self.assertTrue(success, error)

        # Set the edit target after project open, like Remix does while restoring the modding session state.
        omni.kit.commands.execute("SetEditTargetCommand", layer_identifier=mod_layer.identifier, usd_context="")
        await ui_test.human_delay(20)

        # The existing layer tree should focus the late edit target without requiring the panel to be rebuilt.
        self.assertEqual(["mod.usda"], [item.title for item in layer_tree._layer_tree_widget.selection])
        item_labels = [
            label.widget.text
            for label in ui_test.find_all(f"{window.title}//Frame/**/Label[*].name=='PropertiesPaneSectionTreeItem'")
            if label.widget.visible
        ]
        self.assertEqual(["Root Layer", "mod.usda"], item_labels)

    async def test_user_selection_preserves_active_edit_target_indicator(self):
        # Build a real two-layer stack where the initial panel focus selects the edit target.
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer1_path = Path(self.temp_dir.name) / "layer1.usda"
        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer1 = Sdf.Layer.CreateNew(str(layer1_path))
        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)
        root.subLayerPaths.append(layer1.identifier)
        self.stage.SetEditTarget(Usd.EditTarget(layer0))

        window, layer_tree = await self.__setup_widget_with_tree()
        await ui_test.human_delay(20)

        # Select a non-edit-target layer through the visible tree, like a user preparing a merge.
        self.assertEqual(["layer0.usda"], [item.title for item in layer_tree._layer_tree_widget.selection])
        layer1_item = ui_test.find(f"{window.title}//Frame/**/Frame[*].tooltip=='{layer1.identifier}'")
        self.assertIsNotNone(layer1_item)
        await layer1_item.click()
        await ui_test.human_delay(5)
        self.assertEqual(["layer1.usda"], [item.title for item in layer_tree._layer_tree_widget.selection])
        active_backgrounds = [
            widget
            for widget in ui_test.find_all(f"{window.title}//Frame/**/ScrollingFrame[*].name=='ActiveLayerBackground'")
            if widget.widget.visible
        ]
        self.assertEqual(1, len(active_backgrounds))

        # Re-showing an already-visible panel must not steal selection back to the edit target.
        layer_tree.show(True)
        await ui_test.human_delay(20)

        self.assertEqual(["layer1.usda"], [item.title for item in layer_tree._layer_tree_widget.selection])

    async def test_context_menu_preserves_user_layer_selection_after_edit_target_initial_selection(self):
        # Arrange
        layer0_path = (Path(self.temp_dir.name) / "layer0.usda").as_posix()
        layer1_path = (Path(self.temp_dir.name) / "layer1.usda").as_posix()
        layer0 = Sdf.Layer.CreateNew(layer0_path)
        layer1 = Sdf.Layer.CreateNew(layer1_path)
        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)
        root.subLayerPaths.append(layer1.identifier)
        self.stage.SetEditTarget(layer0)

        window, layer_tree = await self.__setup_widget_with_tree(model=LayerModel())
        await ui_test.human_delay(20)

        # Verify the layer tree opened with the edit target visible.
        item_labels = [
            label
            for label in ui_test.find_all(f"{window.title}//Frame/**/Label[*].name=='PropertiesPaneSectionTreeItem'")
            if label.widget.visible
        ]
        self.assertEqual(["Root Layer", "layer0.usda", "layer1.usda"], [label.widget.text for label in item_labels])
        layer0_item = ui_test.find(f"{window.title}//Frame/**/Frame[*].tooltip=='{layer0.identifier}'")
        layer1_item = ui_test.find(f"{window.title}//Frame/**/Frame[*].tooltip=='{layer1.identifier}'")
        self.assertIsNotNone(layer0_item)
        self.assertIsNotNone(layer1_item)

        # Select two layers through the same UI interactions a user uses before merging layers.
        await layer0_item.click()
        await ui_test.human_delay(5)
        async with ui_test.KeyDownScope(KeyboardInput.LEFT_CONTROL):
            await layer1_item.click()
        await ui_test.human_delay(5)
        self.assertEqual(
            ["layer0.usda", "layer1.usda"],
            [item.title for item in layer_tree._layer_tree_widget.selection],
        )

        # Force a refresh to prove the delayed edit-target initialization does not overwrite user selection.
        layer_tree._on_item_changed(None, None)
        await ui_test.human_delay(20)
        self.assertEqual(
            ["layer0.usda", "layer1.usda"],
            [item.title for item in layer_tree._layer_tree_widget.selection],
        )

        # Open the row context menu and trigger the merge action that only appears for multi-selection.
        await layer0_item.click(right_click=True)
        await ui_test.select_context_menu("Merge Selected Layer Modifications into Strongest Layer")

        # Assert the real merge action moved everything into the strongest selected layer.
        await ui_test.human_delay(20)
        self.assertEqual([layer0.identifier], root.subLayerPaths)

    async def test_child_layer_context_menu_uses_current_selection_for_merge(self):
        # Build the same topology as a Remix project: the edit target is a replacement layer with child layers.
        mod_layer = Sdf.Layer.CreateNew((Path(self.temp_dir.name) / "mod.usda").as_posix())
        development_layer = Sdf.Layer.CreateNew((Path(self.temp_dir.name) / "development.usda").as_posix())
        lights_layer = Sdf.Layer.CreateNew((Path(self.temp_dir.name) / "lights.usda").as_posix())
        Sdf.CreatePrimInLayer(development_layer, "/RootNode")
        Sdf.CreatePrimInLayer(lights_layer, "/RootNode")
        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(mod_layer.identifier)
        mod_layer.subLayerPaths.append(development_layer.identifier)
        mod_layer.subLayerPaths.append(lights_layer.identifier)
        self.stage.SetEditTarget(Usd.EditTarget(mod_layer))

        # Show the tree expanded so the child project layers can be selected like in the Layers panel.
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestLayerTreeWindow", height=500, width=500)
        with window.frame:
            layer_tree = LayerTreeWidget(context_name="", height=360, expansion_default=True)
        self.__track_widget(window, layer_tree)
        await ui_test.human_delay()
        layer_tree.show(True)
        await ui_test.human_delay(20)

        # Select two child layers using the visible rows, not the edit-target layer selected at startup.
        development_row = ui_test.find(f"{window.title}//Frame/**/Frame[*].tooltip=='{development_layer.identifier}'")
        lights_row = ui_test.find(f"{window.title}//Frame/**/Frame[*].tooltip=='{lights_layer.identifier}'")
        self.assertIsNotNone(development_row)
        self.assertIsNotNone(lights_row)
        await development_row.click()
        await ui_test.human_delay(5)
        async with ui_test.KeyDownScope(KeyboardInput.LEFT_CONTROL):
            await lights_row.click()
        await ui_test.human_delay(5)
        self.assertEqual(
            ["development.usda", "lights.usda"],
            [item.title for item in layer_tree._layer_tree_widget.selection],
        )

        # Open the context menu from the selected child row and run the merge action exposed only for multi-selection.
        await development_row.click(right_click=True)
        await ui_test.select_context_menu("Merge Selected Layer Modifications into Strongest Layer")

        # The merge should use the child-layer selection, not the stale edit-target startup selection.
        await ui_test.human_delay(20)
        self.assertEqual([development_layer.identifier], mod_layer.subLayerPaths)

    async def test_context_menu_renames_layer_with_inline_editor(self):
        # Arrange
        layer_path = Path(self.temp_dir.name) / "layer.usda"
        renamed_path = layer_path.with_name("renamed.usda")
        layer = Sdf.Layer.CreateNew(layer_path.as_posix())
        layer.Save()
        self.stage.GetRootLayer().subLayerPaths.append(layer.identifier)

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestLayerTreeWindow", height=400, width=400)
        with window.frame:
            layer_tree = LayerTreeWidget(context_name="", height=240, expansion_default=True)
        self.__track_widget(window, layer_tree)
        await ui_test.human_delay()
        layer_tree.show(True)
        await ui_test.human_delay(20)

        layer_row = ui_test.find(f"{window.title}//Frame/**/Frame[*].tooltip=='{layer.identifier}'")
        self.assertIsNotNone(layer_row)

        # Act
        await layer_row.click(right_click=True)
        await ui_test.select_context_menu("Rename Layer...")
        await ui_test.human_delay(10)

        rename_field = ui_test.find(f"{window.title}//Frame/**/StringField[*]")
        self.assertIsNotNone(rename_field)
        self.assertEqual(layer_path.name, rename_field.model.get_value_as_string())
        rename_field.widget.model.set_value(renamed_path.name)
        await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
        await ui_test.human_delay(20)

        # Assert
        self.assertFalse(layer_path.exists())
        self.assertTrue(renamed_path.exists())
        self.assertEqual([renamed_path], [Path(path) for path in self.stage.GetRootLayer().subLayerPaths])
        item_labels = [
            label.widget.text
            for label in ui_test.find_all(f"{window.title}//Frame/**/Label[*].name=='PropertiesPaneSectionTreeItem'")
            if label.widget.visible
        ]
        self.assertEqual(["Root Layer", renamed_path.name], item_labels)

    async def test_empty_layer_context_menu_disables_transfer_action(self):
        # Arrange
        layer_path = Path(self.temp_dir.name) / "layer.usda"
        layer = Sdf.Layer.CreateNew(layer_path.as_posix())
        layer.Save()
        self.stage.GetRootLayer().subLayerPaths.append(layer.identifier)

        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestLayerTreeWindow", height=400, width=400)
        with window.frame:
            layer_tree = LayerTreeWidget(
                context_name="",
                height=240,
                expansion_default=True,
                project_layer_transfer_fn=lambda _item: None,
            )
        self.__track_widget(window, layer_tree)
        await ui_test.human_delay()
        layer_tree.show(True)
        await ui_test.human_delay(20)

        layer_row = ui_test.find(f"{window.title}//Frame/**/Frame[*].tooltip=='{layer.identifier}'")
        self.assertIsNotNone(layer_row)
        await layer_row.click()
        await ui_test.human_delay(5)
        self.assertEqual([layer_path.name], [item.title for item in layer_tree._layer_tree_widget.selection])

        # Act
        await layer_row.click(right_click=True)
        await ui_test.human_delay(5)
        context_menu = await ui_test.menu.get_context_menu(get_all=True)

        # Assert
        self.assertIn("Transfer All Layer Modifications to...", context_menu.get("_"))
        self.assertNotIn("New Layer...", context_menu.get("_"))
        self.assertNotIn("Imported Layer...", context_menu.get("_"))
        self.assertNotIn("Project Layer...", context_menu.get("_"))

    async def test_initial_expansion_with_second_sublayer_as_edit_target(self):
        """Test that root expands when second sublayer is set as edit target."""
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer1_path = Path(self.temp_dir.name) / "layer1.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer1 = Sdf.Layer.CreateNew(str(layer1_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)
        root.subLayerPaths.append(layer1.identifier)

        # Set layer1 as edit target
        self.stage.SetEditTarget(Usd.EditTarget(layer1))

        window, layer_tree = await self.__setup_widget_with_tree()

        await ui_test.human_delay(20)

        # Root should be expanded showing both sublayers, with layer1 selected
        item_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].name=='PropertiesPaneSectionTreeItem'")
        self.assertEqual(3, len(item_labels))
        self.assertEqual("Root Layer", item_labels[0].widget.text)
        self.assertEqual("layer0.usda", item_labels[1].widget.text)
        self.assertEqual("layer1.usda", item_labels[2].widget.text)
        self.assertEqual(["layer1.usda"], [item.title for item in layer_tree._layer_tree_widget.selection])
