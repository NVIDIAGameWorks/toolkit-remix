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
from pathlib import Path
from unittest.mock import Mock, PropertyMock, patch

import omni.kit
import omni.kit.test
import omni.usd
from omni.flux.asset_importer.widget.extension import get_file_listener_instance as _get_file_listener_instance
from omni.flux.asset_importer.widget.file_import_list import FileImportItem, FileImportListModel
from omni.flux.asset_importer.widget.listener import FileListener as _FileListener


class TestFileImportListModel(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.stage = None

    async def test_refresh_should_set_children_and_call_item_changed(self):
        # Arrange
        model = FileImportListModel()

        items = [Path("Test/0"), Path("Test/1"), Path("Test/2")]

        # Act
        with patch.object(FileImportListModel, "_item_changed") as mock:
            model.refresh(items)

        # Assert
        self.assertEqual(len(items), len(model._children))  # noqa PLW0212

        for i in range(len(model._children)):  # noqa PLW0212
            self.assertEqual(items[i], Path(str(list(model._children.keys())[i]._path)))  # noqa PLW0212

        self.assertEqual(1, mock.call_count)

    async def test_add_item_should_append_and_call_item_changed(self):
        # Arrange
        model = FileImportListModel()

        items = {Mock(): (), Mock(): ()}
        model._children = items.copy()  # noqa PLW0212

        new_item = Mock()

        # Act
        with patch.object(FileImportListModel, "_item_changed") as mock:
            model.add_item(new_item)

        # Assert
        self.assertEqual(len(items) + 1, len(model._children))  # noqa PLW0212
        self.assertEqual(new_item, list(model._children.keys())[-1])  # noqa PLW0212

        self.assertEqual(1, mock.call_count)

    async def test_remove_item_should_remove_and_call_item_changed(self):
        # Arrange
        model = FileImportListModel()

        removed_item = Mock()
        items = {Mock(): (), Mock(): (), removed_item: ()}
        model._children = items.copy()  # noqa PLW0212

        # Act
        with patch.object(FileImportListModel, "_item_changed") as mock:
            model.remove_items([removed_item])

        # Assert
        self.assertEqual(len(items) - 1, len(list(model._children.keys())))  # noqa PLW0212

        with self.assertRaises(ValueError):
            list(model._children.keys()).index(removed_item)  # noqa PLW0212

        self.assertEqual(1, mock.call_count)

    async def test_get_item_children_no_parent_should_return_children(self):
        await self.__run_get_item_children(False)

    async def test_get_item_children_with_parent_should_return_empty_array(self):
        await self.__run_get_item_children(True)

    async def test_get_item_value_model_should_return_item_value_model(self):
        # Arrange
        model = FileImportListModel()
        item = FileImportItem(Path("Test"))

        # Act
        val = model.get_item_value_model(item)

        # Assert
        self.assertEqual(item.value_model.get_value_as_string(), val.get_value_as_string())

    async def test_listener_called_multiple_time(self):
        # wait for the listener to be empty
        await _get_file_listener_instance().deferred_destroy()

        # Arrange
        model = FileImportListModel()
        item = FileImportItem(Path("Test"))
        with (
            patch.object(model, "_on_changed") as changed_mock,
            patch("omni.flux.asset_importer.widget.common.items.ImportItem.is_valid") as mock_exist,
            patch(
                "omni.flux.asset_importer.widget.listener.FileListener.WAIT_TIME", new_callable=PropertyMock
            ) as mock_wait_time,
        ):
            mock_wait_time.return_value = 0.1
            mock_exist.side_effect = [(True, ""), (False, ""), (False, ""), (False, "")]

            # Act
            model.add_item(item)

            await asyncio.sleep(_FileListener.WAIT_TIME + 0.01)
            self.assertEqual(changed_mock.call_count, 0)

            await asyncio.sleep(_FileListener.WAIT_TIME + 0.01)
            self.assertEqual(changed_mock.call_count, 1)

            await asyncio.sleep(_FileListener.WAIT_TIME + 0.01)
            self.assertEqual(changed_mock.call_count, 2)

            # Act
            model.remove_items([item])

            await asyncio.sleep(_FileListener.WAIT_TIME + 0.01)
            self.assertEqual(changed_mock.call_count, 2)

            # Act
            model.add_item(item)

            await asyncio.sleep(_FileListener.WAIT_TIME + 0.01)
            self.assertEqual(changed_mock.call_count, 3)

            model.remove_items([item])

    async def test_get_item_value_model_count_should_return_1(self):
        # Arrange
        model = FileImportListModel()

        # Act
        val = model.get_item_value_model_count(Mock())

        # Assert
        self.assertEqual(1, val)

    async def __run_get_item_children(self, use_parent: bool):
        # Arrange
        model = FileImportListModel()

        items = {FileImportItem(Path("Test")): (), Mock(): (), Mock(): ()}
        model._children = items  # noqa PLW0212

        # Act
        val = model.get_item_children(list(items.keys())[0] if use_parent else None)

        # Assert
        self.assertEqual(0 if use_parent else len(items), len(val))

        for i, item in enumerate(val):
            self.assertEqual(list(items.keys())[i], item)
