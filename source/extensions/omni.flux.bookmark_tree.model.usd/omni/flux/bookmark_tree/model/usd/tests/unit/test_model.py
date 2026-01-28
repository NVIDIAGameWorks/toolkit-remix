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

from unittest.mock import Mock, call, patch

import omni.kit
import omni.kit.test
import omni.usd
from omni.flux.bookmark_tree.model.usd import UsdBookmarkCollectionModel as BookmarkModel
from omni.flux.bookmark_tree.model.usd import USDListener
from omni.flux.bookmark_tree.widget import BookmarkCollectionItem, BookmarkItem, ComponentTypes, CreateBookmarkItem
from omni.kit import commands
from pxr import Usd


class TestModel(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.stage = None

    async def test_refresh_no_stage_quick_return(self):
        # Arrange
        model = BookmarkModel()

        with (
            patch.object(BookmarkModel, "set_items") as set_items_mock,
            patch.object(BookmarkModel, "stage") as stage_mock,
        ):
            stage_mock.return_value = None

            # Act
            model.refresh()
            await omni.kit.app.get_app().next_update_async()

        # Assert
        self.assertEqual(0, set_items_mock.call_count)

    async def test_refresh_valid_sets_items_with_root_layer_edit_context(self):
        # Arrange
        model = BookmarkModel()

        # Act
        with (
            patch.object(BookmarkModel, "set_items") as set_items_mock,
            patch.object(BookmarkModel, "_get_items_from_usd") as usd_items_mock,
            patch("pxr.Usd.EditContext") as edit_context_mock,
        ):
            model.refresh()
            for _ in range(5):
                await omni.kit.app.get_app().next_update_async()

        # Assert
        self.assertEqual(1, set_items_mock.call_count)
        self.assertEqual(1, usd_items_mock.call_count)
        self.assertEqual(1, edit_context_mock.call_count)

        self.assertEqual(call(self.stage, self.stage.GetRootLayer()), edit_context_mock.call_args)

    async def test_enable_listeners_enable_adds_listeners_refreshes_stage_and_items(self):
        await self.__run_test_enable_listeners(True)

    async def test_enable_listeners_disable_removes_model(self):
        await self.__run_test_enable_listeners(False)

    async def test_create_collection_no_stage_quick_return(self):
        # Arrange
        with (
            patch.object(commands, "execute") as execute_mock,
            patch.object(omni.usd.UsdContext, "get_stage") as get_stage_mock,
        ):
            get_stage_mock.return_value = None

            model = BookmarkModel()

            # Act
            model.create_collection("TestCollection", None)

        # Assert
        self.assertEqual(0, execute_mock.call_count)

    async def test_create_collection_no_prim_creates_prim_and_collection_with_root_layer_edit_context(self):
        await self.__run_test_create_collection(False, False)

    async def test_create_collection_with_prim_creates_collection_with_root_layer_edit_context(self):
        await self.__run_test_create_collection(True, False)

    async def test_create_collection_with_parent_adds_item_to_collection_with_root_layer_edit_context(self):
        await self.__run_test_create_collection(True, True)

    async def test_create_collection_undo_group_true_should_use_undo_group(self):
        await self.__run_test_create_collection_undo_group(True)

    async def test_create_collection_undo_group_false_should_use_nullcontext(self):
        await self.__run_test_create_collection_undo_group(False)

    async def test_delete_collection_deletes_collection_with_root_layer_edit_context(self):
        await self.__run_test_delete_collection(False, False)

    async def test_delete_collection_with_parent_removes_item_from_collection_with_root_layer_edit_context(self):
        await self.__run_test_delete_collection(True, False)

    async def test_delete_collection_with_child_collection_deletes_recursively_with_root_layer_edit_context(self):
        await self.__run_test_delete_collection(False, True)

    async def test_delete_collection_undo_group_true_should_use_undo_group(self):
        await self.__run_test_delete_collection_undo_group(True)

    async def test_delete_collection_undo_group_false_should_use_nullcontext(self):
        await self.__run_test_delete_collection_undo_group(False)

    async def test_rename_collection_renames_collection_with_root_layer_edit_context(self):
        await self.__run_test_rename_collection(False)

    async def test_rename_collection_with_parent_removes_old_and_adds_new_collection_with_root_layer_edit_context(self):
        await self.__run_test_rename_collection(True)

    async def test_rename_collection_undo_group_true_should_use_undo_group(self):
        await self.__run_test_rename_collection_undo_group(True)

    async def test_rename_collection_undo_group_false_should_use_nullcontext(self):
        await self.__run_test_rename_collection_undo_group(False)

    async def test_clear_collection_clears_collection_with_root_layer_edit_context(self):
        # Arrange
        collection_path = "TestNode/Bookmarks:collection:TestCollection"

        stage_mock = Mock()
        root_layer_mock = Mock()
        stage_mock.GetRootLayer.return_value = root_layer_mock
        collection_item_mock = Mock()
        collection_item_mock.component_type = ComponentTypes.bookmark_collection.value
        collection_item_mock.children = []

        with (
            patch.object(commands, "execute") as execute_mock,
            patch.object(omni.usd.UsdContext, "get_stage") as get_stage_mock,
            patch("pxr.Usd.EditContext") as edit_context_mock,
            patch.object(BookmarkModel, "find_item") as find_item_mock,
        ):
            find_item_mock.return_value = collection_item_mock
            get_stage_mock.return_value = stage_mock

            model = BookmarkModel()

            # Act
            model.clear_collection(collection_path)

        # Assert
        self.assertEqual(1, edit_context_mock.call_count)
        self.assertEqual(1, execute_mock.call_count)

        self.assertEqual(
            call("ClearCollection", collection_path=collection_path, usd_context_name=""), execute_mock.call_args
        )
        self.assertEqual(call(stage_mock, root_layer_mock), edit_context_mock.call_args)

    async def test_clear_collection_undo_group_true_should_use_undo_group(self):
        await self.__run_test_clear_collection_undo_group(True)

    async def test_clear_collection_undo_group_false_should_use_nullcontext(self):
        await self.__run_test_clear_collection_undo_group(False)

    async def test_add_item_to_collection_adds_item_to_collection_with_root_layer_edit_context(self):
        # Arrange
        collection_path = "TestNode/Bookmarks:collection:TestCollection"
        prim_path = "TestNode/instances/TestPrim"

        stage_mock = Mock()
        root_layer_mock = Mock()
        stage_mock.GetRootLayer.return_value = root_layer_mock

        with (
            patch.object(commands, "execute") as execute_mock,
            patch.object(omni.usd.UsdContext, "get_stage") as get_stage_mock,
            patch("pxr.Usd.EditContext") as edit_context_mock,
        ):
            get_stage_mock.return_value = stage_mock

            model = BookmarkModel()

            # Act
            model.add_item_to_collection(prim_path, collection_path)

        # Assert
        self.assertEqual(1, execute_mock.call_count)
        self.assertEqual(1, edit_context_mock.call_count)

        self.assertEqual(
            call("AddItemToCollection", path_to_add=prim_path, collection_path=collection_path, usd_context_name=""),
            execute_mock.call_args,
        )
        self.assertEqual(call(stage_mock, root_layer_mock), edit_context_mock.call_args)

    async def test_add_item_to_collection_undo_group_true_should_use_undo_group(self):
        await self.__run_test_add_item_to_collection_undo_group(True)

    async def test_add_item_to_collection_undo_group_false_should_use_nullcontext(self):
        await self.__run_test_add_item_to_collection_undo_group(False)

    async def test_remove_item_from_collection_removes_item_from_collection_with_root_layer_edit_context(self):
        # Arrange
        collection_path = "TestNode/Bookmarks:collection:TestCollection"
        prim_path = "TestNode/instances/TestPrim"

        stage_mock = Mock()
        root_layer_mock = Mock()
        stage_mock.GetRootLayer.return_value = root_layer_mock

        with (
            patch.object(commands, "execute") as execute_mock,
            patch.object(omni.usd.UsdContext, "get_stage") as get_stage_mock,
            patch("pxr.Usd.EditContext") as edit_context_mock,
        ):
            get_stage_mock.return_value = stage_mock

            model = BookmarkModel()

            # Act
            model.remove_item_from_collection(prim_path, collection_path)

        # Assert
        self.assertEqual(1, execute_mock.call_count)
        self.assertEqual(1, edit_context_mock.call_count)

        self.assertEqual(
            call(
                "RemoveItemFromCollection",
                prim_or_prop_path=prim_path,
                collection_path=collection_path,
                usd_context_name="",
            ),
            execute_mock.call_args,
        )
        self.assertEqual(call(stage_mock, root_layer_mock), edit_context_mock.call_args)

    async def test_remove_item_from_collection_undo_group_true_should_use_undo_group(self):
        await self.__run_test_remove_item_from_collection_undo_group(True)

    async def test_remove_item_from_collection_undo_group_false_should_use_nullcontext(self):
        await self.__run_test_remove_item_from_collection_undo_group(False)

    async def test_get_active_items_returns_selection_prim_paths(self):
        # Arrange
        base_path = "/TestNode/isntances/"
        item_0 = base_path + "item_0"
        item_1 = base_path + "item_1"
        item_2 = base_path + "item_2"
        item_3 = base_path + "item_3"

        mock_list = [item_0, item_1, item_2, item_3, item_0, item_1, item_2, item_3]
        expected_list = [item_0, item_1, item_2, item_3]

        model = BookmarkModel()

        # Act
        with patch.object(omni.usd.UsdContext, "get_selection") as selection_mock:
            selection_mock.return_value.get_selected_prim_paths.return_value = mock_list

            result = model.get_active_items()

        # Assert
        self.assertListEqual(sorted(expected_list), sorted(result))

    async def test_set_active_items_sets_unique_bookmark_items_prim_paths(self):
        # Arrange
        base_path = "/TestNode/instances/"
        item_0_title = "item_0"
        item_1_title = "item_1"
        item_2_title = "item_2"

        item_0 = BookmarkItem(item_0_title, data=base_path + item_0_title)
        item_1 = BookmarkItem(item_1_title, data=base_path + item_1_title)
        item_2 = BookmarkCollectionItem(item_2_title, data=base_path + item_2_title)
        item_3 = CreateBookmarkItem()

        mock_list = [item_0, item_1, item_2, item_3, item_0, item_1, item_2, item_3]
        expected_list = [base_path + item_0_title, base_path + item_1_title]

        model = BookmarkModel()

        with patch.object(omni.usd.UsdContext, "get_selection") as selection_mock:
            set_mock = selection_mock.return_value.set_selected_prim_paths

            # Act
            model.set_active_items(mock_list)

        # Assert
        args, _ = set_mock.call_args
        self.assertListEqual(sorted(expected_list), sorted(args[0]))
        self.assertEqual(True, args[1])

    async def __run_test_enable_listeners(self, enable: bool):
        # Arrange
        model = BookmarkModel()

        with (
            patch.object(USDListener, "add_model") as add_model_mock,
            patch.object(USDListener, "remove_model") as remove_model_mock,
            patch.object(omni.usd.UsdContext, "get_stage_event_stream") as event_stream_mock,
            patch.object(omni.usd.UsdContext, "get_stage") as get_stage_mock,
            patch.object(BookmarkModel, "refresh") as refresh_mock,
        ):
            create_sub_mock = event_stream_mock.return_value.create_subscription_to_pop

            # Act
            model.enable_listeners(enable)

        # Assert
        self.assertEqual(1 if enable else 0, add_model_mock.call_count)
        self.assertEqual(1 if enable else 0, create_sub_mock.call_count)
        self.assertEqual(1 if enable else 0, get_stage_mock.call_count)
        self.assertEqual(1 if enable else 0, refresh_mock.call_count)

        self.assertEqual(0 if enable else 1, remove_model_mock.call_count)

        if enable:
            _, kwargs = create_sub_mock.call_args
            self.assertDictEqual({"name": "StageEvent"}, kwargs)

    async def __run_test_create_collection(self, existing_prim: bool, use_parent: bool):
        # Arrange
        default_prim = "TestNode"
        collection_name = "TestCollection"
        expected_base_prim = f"{default_prim}/Bookmarks"
        expected_collection_prim = f"{expected_base_prim}:collection:{collection_name}"

        stage_mock = Mock()
        root_layer_mock = Mock()
        stage_mock.GetPrimAtPath.return_value.IsValid.return_value = existing_prim
        stage_mock.HasDefaultPrim.return_value = True
        stage_mock.GetDefaultPrim.return_value.GetPath.return_value = default_prim
        stage_mock.GetRootLayer.return_value = root_layer_mock

        parent_mock = Mock()
        parent_data_mock = Mock()
        parent_mock.data = parent_data_mock

        with (
            patch.object(commands, "execute") as execute_mock,
            patch.object(omni.usd.UsdContext, "get_stage") as get_stage_mock,
            patch("pxr.Usd.EditContext") as edit_context_mock,
            patch("pxr.Usd.CollectionAPI.GetCollection") as get_collection_mock,
            patch.object(BookmarkModel, "add_item_to_collection") as add_item_mock,
        ):
            get_stage_mock.return_value = stage_mock
            execute_mock.side_effect = [(None, expected_collection_prim)]
            if not existing_prim:
                execute_mock.side_effect = [None, *execute_mock.side_effect]

            model = BookmarkModel()

            # Act
            model.create_collection(collection_name, parent_mock if use_parent else None)

        # Assert
        self.assertEqual(1 if existing_prim else 2, execute_mock.call_count)
        self.assertEqual(1 if use_parent else 0, add_item_mock.call_count)
        self.assertEqual(1, edit_context_mock.call_count)
        self.assertEqual(1, get_collection_mock.call_count)

        if not existing_prim:
            self.assertEqual(
                call(
                    "CreatePrimCommand",
                    prim_path=expected_base_prim,
                    prim_type="Scope",
                    select_new_prim=False,
                    context_name="",
                ),
                execute_mock.call_args_list[0],
            )

        self.assertEqual(
            call(
                "CreateCollection", prim_path=expected_base_prim, collection_name=collection_name, usd_context_name=""
            ),
            execute_mock.call_args_list[0 if existing_prim else 1],
        )

        if use_parent:
            self.assertEqual(call(expected_collection_prim, parent_data_mock, False), add_item_mock.call_args)

        self.assertEqual(call(stage_mock, root_layer_mock), edit_context_mock.call_args)

    async def __run_test_create_collection_undo_group(self, use_undo_group: bool):
        # Arrange
        model = BookmarkModel()

        with patch.object(omni.kit.undo, "group") as undo_mock:
            # Act
            model.create_collection("TestCollection", None, use_undo_group=use_undo_group)

        # Assert
        self.assertEqual(1 if use_undo_group else 0, undo_mock.call_count)

    async def __run_test_delete_collection(self, use_parent: bool, use_children: bool):
        # Arrange
        collection_0_path = "/TestNode/Bookmarks:collection:test_collection_0"
        collection_1_path = "/TestNode/Bookmarks:collection:test_collection_1"
        collection_2_path = "/TestNode/Bookmarks:collection:test_collection_2"

        collection_mock = Mock()
        child_1 = collection_1_path
        child_2 = collection_2_path
        child_3 = Mock()
        if use_children:
            collection_mock.GetIncludesRel.return_value.GetTargets.side_effect = [[child_1], [child_2], [child_3]]
        else:
            collection_mock.GetIncludesRel.return_value.GetTargets.return_value = []

        parent_mock = Mock()
        parent_data = Mock()
        parent_mock.data = parent_data

        stage_mock = Mock()
        root_layer_mock = Mock()
        stage_mock.GetRootLayer.return_value = root_layer_mock

        with (
            patch.object(omni.usd.UsdContext, "get_stage") as get_stage_mock,
            patch.object(Usd.CollectionAPI, "GetCollection") as get_collection_mock,
            patch.object(Usd.CollectionAPI, "IsCollectionAPIPath") as is_collection_mock,
            patch.object(commands, "execute") as execute_mock,
            patch("pxr.Usd.EditContext") as edit_context_mock,
            patch.object(BookmarkModel, "remove_item_from_collection") as remove_item_mock,
        ):
            get_stage_mock.return_value = stage_mock
            get_collection_mock.return_value = collection_mock
            is_collection_mock.side_effect = [True, True, False]

            model = BookmarkModel()

            # Act
            model.delete_collection(collection_0_path, parent_mock if use_parent else None)

        # Assert
        self.assertEqual(3 if use_children else 1, get_collection_mock.call_count)
        self.assertEqual(3 if use_children else 1, execute_mock.call_count)
        self.assertEqual(3 if use_children else 1, edit_context_mock.call_count)
        self.assertEqual(3 if use_children else 0, is_collection_mock.call_count)
        self.assertEqual(1 if use_parent else 0, remove_item_mock.call_count)

        self.assertEqual(call(stage_mock, root_layer_mock), edit_context_mock.call_args)

        if use_children:
            self.assertEqual(call(stage_mock, collection_0_path), get_collection_mock.call_args_list[0])
            self.assertEqual(call(stage_mock, collection_1_path), get_collection_mock.call_args_list[1])
            self.assertEqual(call(stage_mock, collection_2_path), get_collection_mock.call_args_list[2])

            self.assertEqual(
                call("DeleteCollection", collection_path=collection_2_path, usd_context_name=""),
                execute_mock.call_args_list[0],
            )
            self.assertEqual(
                call("DeleteCollection", collection_path=collection_1_path, usd_context_name=""),
                execute_mock.call_args_list[1],
            )
            self.assertEqual(
                call("DeleteCollection", collection_path=collection_0_path, usd_context_name=""),
                execute_mock.call_args_list[2],
            )
        else:
            self.assertEqual(call(stage_mock, collection_0_path), get_collection_mock.call_args)
            self.assertEqual(
                call("DeleteCollection", collection_path=collection_0_path, usd_context_name=""), execute_mock.call_args
            )

        if use_parent:
            self.assertEqual(call(collection_0_path, parent_data), remove_item_mock.call_args)

    async def __run_test_delete_collection_undo_group(self, use_undo_group: bool):
        # Arrange
        model = BookmarkModel()

        collection_mock = Mock()
        collection_mock.GetIncludesRel.return_value.GetTargets.return_value = []

        with (
            patch.object(omni.kit.undo, "group") as undo_mock,
            patch.object(Usd.CollectionAPI, "GetCollection") as get_collection_mock,
            patch.object(commands, "execute"),
        ):
            get_collection_mock.return_value = collection_mock

            # Act
            model.delete_collection("TestCollection", None, use_undo_group=use_undo_group)

        # Assert
        self.assertEqual(1 if use_undo_group else 0, undo_mock.call_count)

    async def __run_test_rename_collection(self, use_parent: bool):
        # Arrange
        collection_base_path = "/TestNode/Bookmarks:bookmark:"
        old_collection_path = collection_base_path + "TestCollection"
        new_collection_name = "NewTestCollection"
        new_collection_path = collection_base_path + new_collection_name

        parent_mock = Mock()
        parent_data = Mock()
        parent_mock.data = parent_data

        stage_mock = Mock()
        root_layer_mock = Mock()
        stage_mock.GetRootLayer.return_value = root_layer_mock

        with (
            patch.object(omni.usd.UsdContext, "get_stage") as get_stage_mock,
            patch.object(commands, "execute") as execute_mock,
            patch("pxr.Usd.EditContext") as edit_context_mock,
            patch.object(BookmarkModel, "remove_item_from_collection") as remove_item_mock,
            patch.object(BookmarkModel, "add_item_to_collection") as add_item_mock,
        ):
            get_stage_mock.return_value = stage_mock
            execute_mock.return_value = (None, new_collection_path)

            model = BookmarkModel()

            # Act
            model.rename_collection(old_collection_path, new_collection_name, parent_mock if use_parent else None)

        # Assert
        self.assertEqual(1, execute_mock.call_count)
        self.assertEqual(1 if use_parent else 0, remove_item_mock.call_count)
        self.assertEqual(1 if use_parent else 0, add_item_mock.call_count)

        self.assertEqual(call(stage_mock, root_layer_mock), edit_context_mock.call_args)

        self.assertEqual(
            call(
                "RenameCollection",
                old_collection_path=old_collection_path,
                new_collection_name=new_collection_name,
                usd_context_name="",
            ),
            execute_mock.call_args,
        )

        if use_parent:
            self.assertEqual(call(old_collection_path, parent_data, False), remove_item_mock.call_args)
            self.assertEqual(call(new_collection_path, parent_data, False), add_item_mock.call_args)

    async def __run_test_rename_collection_undo_group(self, use_undo_group: bool):
        # Arrange
        collection_base_path = "/TestNode/Bookmarks:bookmark:"
        new_collection_name = "NewTestCollection"

        model = BookmarkModel()

        with patch.object(omni.kit.undo, "group") as undo_mock, patch.object(commands, "execute") as execute_mock:
            execute_mock.return_value = (None, f"{collection_base_path}{new_collection_name}")

            # Act
            model.rename_collection(
                f"{collection_base_path}TestCollection", "new_collection_name", None, use_undo_group=use_undo_group
            )

        # Assert
        self.assertEqual(1 if use_undo_group else 0, undo_mock.call_count)

    async def __run_test_clear_collection_undo_group(self, use_undo_group: bool):
        # Arrange
        stage_mock = Mock()
        root_layer_mock = Mock()
        stage_mock.GetRootLayer.return_value = root_layer_mock

        collection_item_mock = Mock()
        collection_item_mock.component_type = [
            ComponentTypes.bookmark_collection.value,
            ComponentTypes.bookmark_item.value,
            ComponentTypes.create_collection.value,
        ]

        with (
            patch.object(omni.usd.UsdContext, "get_stage") as get_stage_mock,
            patch.object(omni.kit.undo, "group") as undo_mock,
            patch("pxr.Usd.EditContext"),
            patch.object(BookmarkModel, "find_item") as get_collection_item_mock,
        ):
            get_stage_mock.return_value = stage_mock
            get_collection_item_mock.return_value = collection_item_mock
            model = BookmarkModel()

            # Act
            model.clear_collection("TestNode/Bookmarks:collection:TestCollection", use_undo_group=use_undo_group)

        # Assert
        self.assertEqual(1 if use_undo_group else 0, undo_mock.call_count)

    async def __run_test_add_item_to_collection_undo_group(self, use_undo_group: bool):
        # Arrange
        model = BookmarkModel()

        with patch.object(omni.kit.undo, "group") as undo_mock, patch.object(commands, "execute"):
            # Act
            model.add_item_to_collection(
                "/TestNode/instances/TestPrim",
                "TestNode/Bookmarks:collection:TestCollection",
                use_undo_group=use_undo_group,
            )

        # Assert
        self.assertEqual(1 if use_undo_group else 0, undo_mock.call_count)

    async def __run_test_remove_item_from_collection_undo_group(self, use_undo_group: bool):
        # Arrange
        model = BookmarkModel()

        with patch.object(omni.kit.undo, "group") as undo_mock, patch.object(commands, "execute"):
            # Act
            model.remove_item_from_collection(
                "/TestNode/instances/TestPrim",
                "TestNode/Bookmarks:collection:TestCollection",
                use_undo_group=use_undo_group,
            )

        # Assert
        self.assertEqual(1 if use_undo_group else 0, undo_mock.call_count)
