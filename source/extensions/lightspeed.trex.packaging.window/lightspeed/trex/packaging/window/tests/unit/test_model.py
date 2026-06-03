"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from unittest.mock import AsyncMock, Mock, patch

import omni.kit.test
from lightspeed.trex.packaging.core.repair import (
    PackagingRepairAction,
    PackagingRepairProgress,
    PackagingRepairResult,
)
from lightspeed.trex.packaging.window.tree.item import PackagingErrorItem
from lightspeed.trex.packaging.window.tree.model import PackagingErrorModel


class TestPackagingErrorModelUnit(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self.maxDiff = None
        self._repair_core_patcher = patch("lightspeed.trex.packaging.window.tree.model.PackagingRepairCore")
        self._repair_core_class_mock = self._repair_core_patcher.start()
        self._repair_core_mock = Mock()
        self._repair_core_mock.apply_async = AsyncMock(return_value=PackagingRepairResult())
        self._repair_core_mock.is_file_path_valid.return_value = True
        self._repair_core_mock.was_asset_ingested.return_value = True
        self._repair_core_mock.asset_is_in_project_dir.return_value = True
        self._repair_core_class_mock.return_value = self._repair_core_mock

    async def tearDown(self):
        self._repair_core_patcher.stop()

    async def test_refresh_should_replace_items_and_keep_root_only_children(self):
        # Arrange
        model = PackagingErrorModel(context_name="TestContext")

        # Act
        model.refresh(
            [
                ("/path/to/layer_a.usda", "/RootNode/PrimA", "/missing/model_a.usda"),
                ("/path/to/layer_b.usda", "/RootNode/PrimB", "/missing/model_b.usda"),
            ]
        )

        # Assert
        children = model.get_item_children(None)
        self.assertEqual(
            [
                (
                    "/path/to/layer_a.usda",
                    "/RootNode/PrimA",
                    "/missing/model_a.usda",
                    "/missing/model_a.usda",
                    PackagingRepairAction.IGNORE,
                ),
                (
                    "/path/to/layer_b.usda",
                    "/RootNode/PrimB",
                    "/missing/model_b.usda",
                    "/missing/model_b.usda",
                    PackagingRepairAction.IGNORE,
                ),
            ],
            self.__get_item_values(children),
        )
        self.assertEqual([], model.get_item_children(children[0]))
        self.assertEqual(4, model.get_item_value_model_count(children[0]))

    async def test_replace_asset_paths_should_update_item_and_emit_action_changed(self):
        # Arrange
        model, (item, _) = self.__create_model_with_two_items()
        action_changed_mock = Mock()
        subscription = model.subscribe_action_changed(action_changed_mock)

        # Act
        model.replace_asset_paths({item: "/fixed/model_a.usda"})

        # Assert
        self.assertEqual("/fixed/model_a.usda", item.fixed_asset_path)
        self.assertEqual(PackagingRepairAction.REPLACE_ASSET, item.action)
        action_changed_mock.assert_called_once()
        self.assertIsNotNone(subscription)

    async def test_remove_asset_paths_should_update_item_and_emit_action_changed(self):
        # Arrange
        model, (_, item) = self.__create_model_with_two_items()
        action_changed_mock = Mock()
        subscription = model.subscribe_action_changed(action_changed_mock)

        # Act
        model.remove_asset_paths([item])

        # Assert
        self.assertIsNone(item.fixed_asset_path)
        self.assertEqual(PackagingRepairAction.REMOVE_REFERENCE, item.action)
        action_changed_mock.assert_called_once()
        self.assertIsNotNone(subscription)

    async def test_reset_asset_paths_should_update_item_and_emit_action_changed(self):
        # Arrange
        model, (item, _) = self.__create_model_with_two_items()
        item.fixed_asset_path = "/fixed/model_a.usda"
        action_changed_mock = Mock()
        subscription = model.subscribe_action_changed(action_changed_mock)

        # Act
        model.reset_asset_paths([item])

        # Assert
        self.assertEqual("/missing/model_a.usda", item.fixed_asset_path)
        self.assertEqual(PackagingRepairAction.IGNORE, item.action)
        action_changed_mock.assert_called_once()
        self.assertIsNotNone(subscription)

    async def test_reset_asset_paths_without_items_should_update_all_items_and_emit_action_changed(self):
        # Arrange
        model, (item_a, item_b) = self.__create_model_with_two_items()
        item_a.fixed_asset_path = "/fixed/model_a.usda"
        item_b.fixed_asset_path = None
        action_changed_mock = Mock()
        subscription = model.subscribe_action_changed(action_changed_mock)

        # Act
        model.reset_asset_paths(None)

        # Assert
        self.assertEqual("/missing/model_a.usda", item_a.fixed_asset_path)
        self.assertEqual(PackagingRepairAction.IGNORE, item_a.action)
        self.assertEqual("/missing/model_b.usda", item_b.fixed_asset_path)
        self.assertEqual(PackagingRepairAction.IGNORE, item_b.action)
        action_changed_mock.assert_called_once()
        self.assertIsNotNone(subscription)

    async def test_apply_new_paths_async_selected_items_should_delegate_to_repair_core(self):
        # Arrange
        item = self.__create_item(fixed_asset_path="/fixed/model.usda")
        ignored_items = [("/path/to/layer_b.usda", "/RootNode/PrimB", "/missing/model_b.usda")]
        self._repair_core_mock.apply_async.return_value = PackagingRepairResult(ignored_items=ignored_items)
        model = PackagingErrorModel(context_name="TestContext")
        action_changed_mock = Mock()
        subscription = model.subscribe_action_changed(action_changed_mock)

        # Act
        result = await model.apply_new_paths_async(items=[item])

        # Assert
        self._repair_core_class_mock.assert_called_once_with(context_name="TestContext")
        self.assertEqual(ignored_items, result.ignored_items)
        self.assertEqual(
            [("/path/to/layer.usda", "/RootNode/Prim", "/missing/model.usda", "/fixed/model.usda")],
            self.__get_repair_request_values(self._repair_core_mock.apply_async.call_args.args[0]),
        )
        action_changed_mock.assert_called_once()
        self.assertIsNotNone(subscription)

    async def test_apply_new_paths_async_without_items_should_apply_all_model_items(self):
        # Arrange
        model = PackagingErrorModel(context_name="TestContext")
        model.refresh(
            [
                ("/path/to/layer_a.usda", "/RootNode/PrimA", "/missing/model_a.usda"),
                ("/path/to/layer_b.usda", "/RootNode/PrimB", "/missing/model_b.usda"),
            ]
        )
        items = model.get_item_children(None)
        items[0].fixed_asset_path = "/fixed/model_a.usda"
        items[1].fixed_asset_path = None

        # Act
        result = await model.apply_new_paths_async()

        # Assert
        self.assertEqual([], result.ignored_items)
        self.assertEqual([], result.failed_repairs)
        self.assertEqual(
            [
                ("/path/to/layer_a.usda", "/RootNode/PrimA", "/missing/model_a.usda", "/fixed/model_a.usda"),
                ("/path/to/layer_b.usda", "/RootNode/PrimB", "/missing/model_b.usda", None),
            ],
            self.__get_repair_request_values(self._repair_core_mock.apply_async.call_args.args[0]),
        )

    async def test_apply_new_paths_async_should_delegate_to_repair_core(self):
        # Arrange
        item = self.__create_item(fixed_asset_path="/fixed/model.usda")
        ignored_items = [("/path/to/layer.usda", "/RootNode/Prim", "/missing/model.usda")]
        self._repair_core_mock.apply_async.return_value = PackagingRepairResult(ignored_items=ignored_items)
        model = PackagingErrorModel(context_name="TestContext")
        progress_callback_mock = Mock()
        is_cancelled_mock = Mock(return_value=False)
        app_mock = Mock()
        app_mock.next_update_async = AsyncMock()

        # Act
        with patch("lightspeed.trex.packaging.window.tree.model.omni.kit.app.get_app", return_value=app_mock):
            result = await model.apply_new_paths_async(
                items=[item],
                progress_callback=progress_callback_mock,
                is_cancelled=is_cancelled_mock,
            )

        # Assert
        self._repair_core_mock.raise_if_layers_dirty.assert_called_once()
        self.assertEqual(ignored_items, result.ignored_items)
        self.assertEqual(
            [("/path/to/layer.usda", "/RootNode/Prim", "/missing/model.usda", "/fixed/model.usda")],
            self.__get_repair_request_values(self._repair_core_mock.apply_async.call_args.args[0]),
        )
        self.assertIs(self._repair_core_mock.apply_async.call_args.kwargs["progress_callback"], progress_callback_mock)
        self.assertIs(self._repair_core_mock.apply_async.call_args.kwargs["is_cancelled"], is_cancelled_mock)
        progress_callback_mock.assert_any_call(0, 1, PackagingRepairProgress.APPLYING)

    async def test_apply_new_paths_async_cancelled_should_skip_action_changed_event(self):
        # Arrange
        self._repair_core_mock.apply_async.return_value = None
        model = PackagingErrorModel(context_name="TestContext")
        action_changed_mock = Mock()
        subscription = model.subscribe_action_changed(action_changed_mock)

        # Act
        result = await model.apply_new_paths_async(items=[self.__create_item()])

        # Assert
        self.assertIsNone(result)
        action_changed_mock.assert_not_called()
        self.assertIsNotNone(subscription)

    async def test_was_the_asset_ingested_should_delegate_to_repair_core(self):
        # Arrange
        model = PackagingErrorModel(context_name="TestContext")

        # Act
        result = model.was_the_asset_ingested("/path/to/replacement/model.usda")

        # Assert
        self.assertTrue(result)
        self._repair_core_mock.was_asset_ingested.assert_called_once_with(
            "/path/to/replacement/model.usda", ignore_invalid_paths=True
        )

    async def test_asset_is_in_project_dir_should_delegate_to_repair_core(self):
        # Arrange
        model = PackagingErrorModel(context_name="TestContext")
        layer = Mock(identifier="/path/to/layer.usda")

        # Act
        result = model.asset_is_in_project_dir("/path/to/replacement/model.usda", layer)

        # Assert
        self.assertTrue(result)
        self._repair_core_mock.asset_is_in_project_dir.assert_called_once_with(
            "/path/to/layer.usda", "/path/to/replacement/model.usda", include_deps_dir=False
        )

    async def test_is_replacement_asset_valid_should_require_ingested_model(self):
        # Arrange
        model = PackagingErrorModel(context_name="TestContext")
        item = self.__create_item()

        with patch("lightspeed.trex.packaging.window.tree.model.Sdf.Layer.FindOrOpen") as find_layer_mock:
            find_layer_mock.return_value = Mock(identifier="/path/to/layer.usda")

            # Act
            result = model.is_replacement_asset_valid(item, "/path/to/replacement/model.usda")

        # Assert
        self.assertTrue(result)
        self._repair_core_mock.is_file_path_valid.assert_called_once_with(
            "/path/to/layer.usda", "/path/to/replacement/model.usda", log_error=False
        )
        self._repair_core_mock.was_asset_ingested.assert_called_once_with(
            "/path/to/replacement/model.usda", ignore_invalid_paths=False
        )
        self._repair_core_mock.asset_is_in_project_dir.assert_called_once_with(
            "/path/to/layer.usda", "/path/to/replacement/model.usda", include_deps_dir=False
        )

    async def test_is_replacement_asset_valid_should_accept_project_texture_without_ingestion_metadata(self):
        # Arrange
        model = PackagingErrorModel(context_name="TestContext")
        item = self.__create_item(asset_path="/missing/texture.dds", fixed_asset_path="/missing/texture.dds")

        with patch("lightspeed.trex.packaging.window.tree.model.Sdf.Layer.FindOrOpen") as find_layer_mock:
            find_layer_mock.return_value = Mock(identifier="/path/to/layer.usda")

            # Act
            result = model.is_replacement_asset_valid(item, "/path/to/replacement/texture.dds")

        # Assert
        self.assertTrue(result)
        self._repair_core_mock.is_file_path_valid.assert_called_once_with(
            "/path/to/layer.usda", "/path/to/replacement/texture.dds", log_error=False
        )
        self._repair_core_mock.was_asset_ingested.assert_not_called()
        self._repair_core_mock.asset_is_in_project_dir.assert_called_once_with(
            "/path/to/layer.usda", "/path/to/replacement/texture.dds", include_deps_dir=False
        )

    async def test_destroy_should_destroy_repair_core(self):
        # Arrange
        model = PackagingErrorModel(context_name="TestContext")

        # Act
        model.destroy()

        # Assert
        self._repair_core_mock.destroy.assert_called_once()

    @staticmethod
    def __create_model_with_two_items() -> tuple[PackagingErrorModel, list[PackagingErrorItem]]:
        model = PackagingErrorModel(context_name="TestContext")
        model.refresh(
            [
                ("/path/to/layer_a.usda", "/RootNode/PrimA", "/missing/model_a.usda"),
                ("/path/to/layer_b.usda", "/RootNode/PrimB", "/missing/model_b.usda"),
            ]
        )
        return model, model.get_item_children(None)

    @staticmethod
    def __create_item(
        asset_path: str = "/missing/model.usda", fixed_asset_path: str | None = "/missing/model.usda"
    ) -> PackagingErrorItem:
        item = PackagingErrorItem("/path/to/layer.usda", "/RootNode/Prim", asset_path)
        item.fixed_asset_path = fixed_asset_path
        return item

    @staticmethod
    def __get_repair_request_values(repair_requests) -> list[tuple[str, str, str, str | None]]:
        return [
            (item.layer_identifier, str(item.prim_path), item.asset_path, item.fixed_asset_path)
            for item in repair_requests
        ]

    @staticmethod
    def __get_item_values(items: list[PackagingErrorItem]) -> list[tuple[str, str, str, str | None, object]]:
        return [
            (item.layer_identifier, str(item.prim_path), item.asset_path, item.fixed_asset_path, item.action)
            for item in items
        ]
