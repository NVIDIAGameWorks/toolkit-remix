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

from unittest.mock import patch

import omni.usd
from carb.input import KeyboardInput
from omni import ui
from omni.flux.custom_tags.core import CustomTagsCore
from omni.flux.custom_tags.window import EditCustomTagsWindow
from omni.flux.custom_tags.window.selection_tree import TagsEditItem
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, wait_stage_loading
from pxr import Sdf, Usd


class TestEditCustomTagsWindow(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

        root_layer = self.stage.GetRootLayer()

        # Create a sublayer and set it as the edit target to test the commands edit target
        sublayer = Sdf.Layer.CreateAnonymous()
        root_layer.subLayerPaths.append(sublayer.identifier)

        self.stage.SetEditTarget(Usd.EditTarget(sublayer))

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

        self.stage = None

    async def _create_collections(self) -> tuple[list[str], list[str]]:
        with Usd.EditContext(self.stage, self.stage.GetRootLayer()):
            prims = [
                "/RootNode/meshes/mesh_01",
                "/RootNode/meshes/mesh_02",
                "/RootNode/materials/mat_01/Shader",
                "/RootNode/instances/mesh_01_01",
            ]
            tags = ["Empty_Tag", "Test_Tag_01", "Test_Tag_02", "Test_Tag_03", "Test_Tag_04"]

            base_prim = self.stage.DefinePrim("/CustomTags", "Scope")

            for prim in prims:
                self.stage.DefinePrim(prim, "Xform")

            collections = []
            for tag in tags:
                collections.append(Usd.CollectionAPI.Apply(base_prim, tag))

            includes_rel = collections[1].CreateIncludesRel()
            includes_rel.AddTarget(prims[0])

            includes_rel = collections[2].CreateIncludesRel()
            includes_rel.AddTarget(prims[0])
            includes_rel.AddTarget(prims[1])

            includes_rel = collections[3].CreateIncludesRel()
            includes_rel.AddTarget(prims[0])
            includes_rel.AddTarget(prims[1])
            includes_rel.AddTarget(prims[2])

            includes_rel = collections[4].CreateIncludesRel()
            includes_rel.AddTarget(prims[0])
            includes_rel.AddTarget(prims[1])
            includes_rel.AddTarget(prims[2])
            includes_rel.AddTarget(prims[3])

        return prims, tags

    async def _setup_window(self, selected_paths: list[str] = None) -> tuple[EditCustomTagsWindow, ui.Window]:
        await arrange_windows()

        instance = EditCustomTagsWindow(selected_paths or [])

        self.assertIsNotNone(instance)

        await ui_test.human_delay()

        window = ui_test.find(instance._window.title).window
        self.assertIsNotNone(window)

        return instance, window

    async def test_window_works_as_expected_and_executes_commands_on_apply(self):
        await self.__run_test_window_works_as_expected(True)

    async def test_window_works_as_expected_and_closes_window_without_executing_commands_on_cancel(self):
        await self.__run_test_window_works_as_expected(False)

    async def __run_test_window_works_as_expected(self, apply_changes: bool):
        # Setup the Stage
        prims, tags = await self._create_collections()

        # Setup the window -> Select all the prims
        instance, window = await self._setup_window(prims)

        try:
            # Make sure all the expected elements are there
            available_tree = ui_test.find(f"{window.title}//Frame/**/TreeView[*].identifier=='available_tree'")
            assigned_tree = ui_test.find(f"{window.title}//Frame/**/TreeView[*].identifier=='assigned_tree'")
            create_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='create'")
            edit_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='edit'")
            delete_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='delete'")
            cancel_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='cancel'")
            apply_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='apply'")

            self.assertIsNotNone(available_tree)
            self.assertIsNotNone(assigned_tree)
            self.assertIsNotNone(create_button)
            self.assertIsNotNone(edit_button)
            self.assertIsNotNone(delete_button)
            self.assertIsNotNone(cancel_button)
            self.assertIsNotNone(apply_button)

            tree_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='tag'")

            available_model_item = [i.title for i in available_tree.model.get_item_children(None)]
            assigned_model_item = [i.title for i in assigned_tree.model.get_item_children(None)]

            available_items = [i for i in tree_items if i.widget.text in available_model_item]
            assigned_items = [i for i in tree_items if i.widget.text in assigned_model_item]

            self.assertEqual(len(available_items), len(tags) - 1)
            self.assertEqual(len(assigned_items), 1)

            # Test Edit/Delete enable state
            self.assertTrue(create_button.widget.enabled)
            self.assertFalse(edit_button.widget.enabled)
            self.assertFalse(delete_button.widget.enabled)

            # Select an item in the available tree
            await available_items[1].click()  # 0 is Empty_Tag
            await ui_test.human_delay()

            self.assertTrue(create_button.widget.enabled)
            self.assertTrue(edit_button.widget.enabled)
            self.assertTrue(delete_button.widget.enabled)

            # Test deleting the item removes it
            await delete_button.click()
            await ui_test.human_delay()

            self.assertTrue(create_button.widget.enabled)
            self.assertFalse(edit_button.widget.enabled)
            self.assertFalse(delete_button.widget.enabled)

            tree_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='tag'")

            available_model_item = [i.title for i in available_tree.model.get_item_children(None)]
            assigned_model_item = [i.title for i in assigned_tree.model.get_item_children(None)]

            available_items = [i for i in tree_items if i.widget.text in available_model_item]
            assigned_items = [i for i in tree_items if i.widget.text in assigned_model_item]

            self.assertEqual(len(available_items), len(tags) - 2)
            self.assertEqual(len(assigned_items), 1)

            # Test adding an item
            await create_button.click()
            await ui_test.human_delay()

            edit_items = ui_test.find_all(f"{window.title}//Frame/**/StringField[*].identifier=='edit_tag'")

            self.assertEqual(len(edit_items), 1)

            # Delete Existing Text
            for _ in range(len(TagsEditItem().value)):
                await edit_items[0].input("", human_delay_speed=0, end_key=KeyboardInput.BACKSPACE)
            await edit_items[0].input(tags[1], human_delay_speed=20, end_key=KeyboardInput.ENTER)
            await ui_test.human_delay()

            tree_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='tag'")

            available_model_item = [i.title for i in available_tree.model.get_item_children(None)]
            assigned_model_item = [i.title for i in assigned_tree.model.get_item_children(None)]

            available_items = [i for i in tree_items if i.widget.text in available_model_item]
            assigned_items = [i for i in tree_items if i.widget.text in assigned_model_item]

            self.assertEqual(len(available_items), len(tags) - 1)
            self.assertEqual(len(assigned_items), 1)

            self.assertListEqual(available_model_item, tags[:4])

            # Test editing an item with an invalid name
            await available_items[1].click()  # 0 is Empty_Tag
            await ui_test.human_delay()

            await edit_button.click()
            await ui_test.human_delay()

            edit_items = ui_test.find_all(f"{window.title}//Frame/**/StringField[*].identifier=='edit_tag'")

            self.assertEqual(len(edit_items), 1)

            await edit_items[0].input("", human_delay_speed=0, end_key=KeyboardInput.BACKSPACE)
            await edit_items[0].input("#In. Valid + Name", human_delay_speed=20, end_key=KeyboardInput.DOWN)
            await ui_test.human_delay()

            self.assertEqual("FieldError", edit_items[0].widget.style_type_name_override)
            self.assertEqual(
                "The tag name is not valid. The name can only contain letters, numbers, dashes and underscores.",
                edit_items[0].widget.tooltip,
            )

            await edit_items[0].input("", end_key=KeyboardInput.ENTER)
            await ui_test.human_delay()

            tree_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='tag'")

            available_model_item = [i.title for i in available_tree.model.get_item_children(None)]
            assigned_model_item = [i.title for i in assigned_tree.model.get_item_children(None)]

            available_items = [i for i in tree_items if i.widget.text in available_model_item]
            assigned_items = [i for i in tree_items if i.widget.text in assigned_model_item]

            self.assertEqual(len(available_items), len(tags) - 1)
            self.assertEqual(len(assigned_items), 1)

            self.assertListEqual(available_model_item, ["Empty_Tag", "Test_Tag_01", "Test_Tag_02", "Test_Tag_03"])

            # Test editing an item
            await available_items[1].click()  # 0 is Empty_Tag
            await ui_test.human_delay()

            await edit_button.click()
            await ui_test.human_delay()

            edit_items = ui_test.find_all(f"{window.title}//Frame/**/StringField[*].identifier=='edit_tag'")

            self.assertEqual(len(edit_items), 1)

            await edit_items[0].input("", human_delay_speed=0, end_key=KeyboardInput.BACKSPACE)
            await edit_items[0].input(tags[2], human_delay_speed=20, end_key=KeyboardInput.ENTER)
            await ui_test.human_delay()

            tree_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='tag'")

            available_model_item = [i.title for i in available_tree.model.get_item_children(None)]
            assigned_model_item = [i.title for i in assigned_tree.model.get_item_children(None)]

            available_items = [i for i in tree_items if i.widget.text in available_model_item]
            assigned_items = [i for i in tree_items if i.widget.text in assigned_model_item]

            self.assertEqual(len(available_items), len(tags) - 1)
            self.assertEqual(len(assigned_items), 1)

            self.assertListEqual(available_model_item, ["Empty_Tag", "Test_Tag_02", "Test_Tag_03", "Test_Tag_05"])

            # Test single item drag/drop
            await assigned_items[0].drag_and_drop(available_tree.position + (available_tree.size / 3))
            await ui_test.human_delay()

            tree_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='tag'")

            available_model_item = [i.title for i in available_tree.model.get_item_children(None)]
            assigned_model_item = [i.title for i in assigned_tree.model.get_item_children(None)]

            available_items = [i for i in tree_items if i.widget.text in available_model_item]
            assigned_items = [i for i in tree_items if i.widget.text in assigned_model_item]

            self.assertEqual(len(available_items), len(tags))
            self.assertEqual(len(assigned_items), 0)

            # Test multiple item drag/drop
            await available_items[2].click()
            await ui_test.human_delay()
            async with ui_test.KeyDownScope(KeyboardInput.LEFT_SHIFT):
                await available_items[-1].click()
                await ui_test.human_delay()
            await available_items[-1].drag_and_drop(assigned_tree.position + (assigned_tree.size / 3))
            await ui_test.human_delay()

            tree_items = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='tag'")

            available_model_item = [i.title for i in available_tree.model.get_item_children(None)]
            assigned_model_item = [i.title for i in assigned_tree.model.get_item_children(None)]

            available_items = [i for i in tree_items if i.widget.text in available_model_item]
            assigned_items = [i for i in tree_items if i.widget.text in assigned_model_item]

            self.assertEqual(len(available_items), 2)
            self.assertEqual(len(assigned_items), len(tags) - 2)

            # Test apply and cancel
            with (
                patch.object(CustomTagsCore, "add_tag_to_prim") as add_tag_mock,
                patch.object(CustomTagsCore, "remove_tag_from_prim") as remove_tag_mock,
                patch.object(CustomTagsCore, "rename_tag") as rename_tag_mock,
                patch.object(CustomTagsCore, "delete_tags") as delete_tags_mock,
                patch.object(CustomTagsCore, "create_tag") as create_tag_mock,
            ):
                if apply_changes:
                    await apply_button.click()
                    await ui_test.human_delay()

                    confirm_button = ui_test.find("Confirm Tag Deletion//Frame/**/Button[*].text=='Confirm'")

                    self.assertIsNotNone(confirm_button)

                    await confirm_button.click()
                else:
                    await cancel_button.click()

            await ui_test.human_delay()

            # Make sure the window is not visible
            self.assertFalse(window.visible)

            # If we are applying the changes, assert the commands are called correctly,
            # otherwise make sure no commands are executed
            self.assertEqual(add_tag_mock.call_count, 12 if apply_changes else 0)
            self.assertEqual(remove_tag_mock.call_count, 4 if apply_changes else 0)
            self.assertEqual(rename_tag_mock.call_count, 1 if apply_changes else 0)
            self.assertEqual(delete_tags_mock.call_count, 1 if apply_changes else 0)
            self.assertEqual(create_tag_mock.call_count, 1 if apply_changes else 0)
        finally:
            # Cleanup the test
            instance.destroy()
            await ui_test.human_delay()
