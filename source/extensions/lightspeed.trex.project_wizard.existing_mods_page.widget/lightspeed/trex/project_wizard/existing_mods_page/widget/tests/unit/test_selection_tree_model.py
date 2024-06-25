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
from unittest.mock import patch

import omni.kit.test
from lightspeed.trex.project_wizard.existing_mods_page.widget.selection_tree.items import ModSelectionItem
from lightspeed.trex.project_wizard.existing_mods_page.widget.selection_tree.model import ModSelectionModel


class TestSelectionTreeModel(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        self.temp_dir.cleanup()
        self.temp_dir = None

    async def test_refresh_sets_items_and_calls_item_changed(self):
        # Arrange
        mods = [("ModDir0", "mod_file_0.usda"), ("ModDir1", "mod_file_1.usda"), ("ModDir2", "mod_file_2.usda")]
        paths = []
        for mod_dir, mod_file in mods:
            paths.append(Path(self.temp_dir.name) / mod_dir / mod_file)

        model = ModSelectionModel()

        # Act
        model.refresh(paths)

        # Assert
        self.assertEqual(len(paths), len(model._items))  # noqa PLW0212
        for i, path in enumerate(paths):
            self.assertEqual(path, model._items[i]._path)  # noqa PLW0212

    async def test_find_item_valid_item_should_return_item(self):
        # Arrange
        mods = [("ModDir0", "mod_file_0.usda"), ("ModDir1", "mod_file_1.usda"), ("ModDir2", "mod_file_2.usda")]
        paths = []
        for mod_dir, mod_file in mods:
            paths.append(Path(self.temp_dir.name) / mod_dir / mod_file)

        items = [ModSelectionItem(p) for p in paths]

        model = ModSelectionModel()
        model._items = items  # noqa PLW0212

        # Act
        mod_1 = model.find_item(str(paths[0]))
        mod_2 = model.find_item(str(paths[1]))
        mod_3 = model.find_item(str(paths[2]))

        # Assert
        self.assertIsNotNone(mod_1)
        self.assertIsNotNone(mod_2)
        self.assertIsNotNone(mod_3)

        self.assertEqual(items[0], mod_1)
        self.assertEqual(items[1], mod_2)
        self.assertEqual(items[2], mod_3)

    async def test_find_item_invalid_item_should_return_none(self):
        # Arrange
        mods = [("ModDir0", "mod_file_0.usda"), ("ModDir1", "mod_file_1.usda"), ("ModDir2", "mod_file_2.usda")]
        paths = []
        for mod_dir, mod_file in mods:
            paths.append(Path(self.temp_dir.name) / mod_dir / mod_file)

        items = [ModSelectionItem(p) for p in paths]

        model = ModSelectionModel()
        model._items = items  # noqa PLW0212

        # Act
        result = model.find_item(self.temp_dir.name)

        # Assert
        self.assertIsNone(result)

    async def test_insert_item_should_insert_item_at_index_and_call_item_changed(self):
        # Arrange
        mods = [("ModDir0", "mod_file_0.usda"), ("ModDir1", "mod_file_1.usda"), ("ModDir2", "mod_file_2.usda")]
        paths = []
        for mod_dir, mod_file in mods:
            paths.append(Path(self.temp_dir.name) / mod_dir / mod_file)

        model = ModSelectionModel()

        # Act
        with patch.object(ModSelectionModel, "_item_changed") as mock:
            model.insert_item(str(paths[0]), -1)
            model.insert_item(str(paths[1]), -1)
            model.insert_item(str(paths[2]), 0)

        # Assert
        self.assertEqual(3, mock.call_count)

        expected_results = [paths[2], paths[0], paths[1]]

        for i, expected_result in enumerate(expected_results):
            self.assertEqual(str(expected_result), str(model._items[i]._path))  # noqa PLW0212

    async def test_remove_item_valid_item_should_find_item_remove_and_call_item_changed(self):
        await self.__run_test_remove_item(True)

    async def test_remove_item_invalid_item_should_quick_return(self):
        await self.__run_test_remove_item(False)

    async def test_get_item_children_should_return_items(self):
        # Arrange
        mods = [("ModDir0", "mod_file_0.usda"), ("ModDir1", "mod_file_1.usda"), ("ModDir2", "mod_file_2.usda")]
        paths = []
        for mod_dir, mod_file in mods:
            paths.append(Path(self.temp_dir.name) / mod_dir / mod_file)

        items = [ModSelectionItem(p) for p in paths]

        model = ModSelectionModel()
        model._items = items  # noqa PLW0212

        # Act
        items_result = model.get_item_children(None)
        item_children_result = model.get_item_children(items_result[0])

        # Assert
        self.assertEqual(3, len(items_result))
        self.assertEqual(0, len(item_children_result))

        for i, item in enumerate(items):
            self.assertEqual(item, items_result[i])

    async def test_get_item_value_model_count_should_return_1(self):
        # Arrange
        model = ModSelectionModel()

        # Act
        result = model.get_item_value_model_count(None)

        # Assert
        self.assertEqual(1, result)

    async def test_get_drag_mime_data_should_return_item_repr(self):
        # Arrange
        item = ModSelectionItem(Path(self.temp_dir.name) / "ModDir0" / "mod_file_0.usda")
        model = ModSelectionModel()

        # Act
        result = model.get_drag_mime_data(item)

        # Assert
        self.assertEqual(str(item._path), result)  # noqa PLW0212

    async def test_drop_accepted_should_return_item_source_exists(self):
        # Arrange
        item = ModSelectionItem(Path(self.temp_dir.name) / "ModDir0" / "mod_file_0.usda")
        model = ModSelectionModel()

        # Act
        result_1 = model.drop_accepted(None, item, -1)
        result_2 = model.drop_accepted(None, item, 0)
        result_3 = model.drop_accepted(item, item, -1)
        result_4 = model.drop_accepted(item, item, 0)

        result_5 = model.drop_accepted(item, None, -1)
        result_6 = model.drop_accepted(item, None, 0)

        # Assert
        self.assertTrue(result_1)
        self.assertTrue(result_2)
        self.assertTrue(result_3)
        self.assertTrue(result_4)

        self.assertFalse(result_5)
        self.assertFalse(result_6)

    async def test_drop_move_should_insert_and_remove_item_and_call_on_item_dropped_event(self):
        await self.__run_test_drop_move(True)
        await self.__run_test_drop_move(False)

    async def test_drop_add_should_insert_item_and_call_on_item_dropped_event(self):
        await self.__run_test_drop_add(True)
        await self.__run_test_drop_add(False)

    async def __run_test_remove_item(self, valid: bool):
        # Arrange
        mods = [("ModDir0", "mod_file_0.usda"), ("ModDir1", "mod_file_1.usda"), ("ModDir2", "mod_file_2.usda")]
        paths = []
        for mod_dir, mod_file in mods:
            paths.append(Path(self.temp_dir.name) / mod_dir / mod_file)

        items = [ModSelectionItem(p) for p in paths]

        model = ModSelectionModel()
        model._items = items  # noqa PLW0212

        # Act
        with patch.object(ModSelectionModel, "_item_changed") as mock:
            model.remove_item(str(paths[1]) if valid else self.temp_dir.name)

        # Assert
        self.assertEqual(1 if valid else 0, mock.call_count)
        self.assertEqual(2 if valid else 3, len(model._items))  # noqa PLW0212

        expected_results = [paths[0], paths[2]] if valid else paths

        for i, expected_result in enumerate(expected_results):
            self.assertEqual(str(expected_result), str(model._items[i]._path))  # noqa PLW0212

    async def __run_test_drop_move(self, is_item: bool):
        # Arrange
        mods = [("ModDir0", "mod_file_0.usda"), ("ModDir1", "mod_file_1.usda"), ("ModDir2", "mod_file_2.usda")]
        paths = []
        for mod_dir, mod_file in mods:
            paths.append(Path(self.temp_dir.name) / mod_dir / mod_file)

        items = [ModSelectionItem(p) for p in paths]

        model = ModSelectionModel()
        model._items = items  # noqa PLW0212

        # Act
        with patch.object(ModSelectionModel, "_item_changed") as mock:
            model.drop(None, items[2] if is_item else paths[2], 0)

        # Assert
        self.assertEqual(2, mock.call_count)
        self.assertEqual(3, len(model._items))  # noqa PLW0212

        expected_results = [paths[2], paths[0], paths[1]]

        for i, expected_result in enumerate(expected_results):
            self.assertEqual(str(expected_result), str(model._items[i]._path))  # noqa PLW0212

    async def __run_test_drop_add(self, is_item: bool):
        # Arrange
        mods = [("ModDir0", "mod_file_0.usda"), ("ModDir1", "mod_file_1.usda")]
        paths = []
        for mod_dir, mod_file in mods:
            paths.append(Path(self.temp_dir.name) / mod_dir / mod_file)

        items = [ModSelectionItem(p) for p in paths]

        model = ModSelectionModel()
        model._items = items  # noqa PLW0212

        item_0_path = Path(self.temp_dir.name) / "ExtraMod0" / "mod_file_0.usda"
        item_1_path = Path(self.temp_dir.name) / "ExtraMod1" / "mod_file_1.usda"

        item_0 = ModSelectionItem(item_0_path)
        item_1 = ModSelectionItem(item_1_path)

        # Act
        with patch.object(ModSelectionModel, "_item_changed") as mock:
            model.drop(None, item_0 if is_item else item_0_path, 1)
            model.drop(None, item_1 if is_item else item_1_path, -1)

        # Assert
        self.assertEqual(2, mock.call_count)
        self.assertEqual(4, len(model._items))  # noqa PLW0212

        expected_results = [paths[0], item_0_path, paths[1], item_1_path]

        for i, expected_result in enumerate(expected_results):
            self.assertEqual(str(expected_result), str(model._items[i]._path))  # noqa PLW0212
