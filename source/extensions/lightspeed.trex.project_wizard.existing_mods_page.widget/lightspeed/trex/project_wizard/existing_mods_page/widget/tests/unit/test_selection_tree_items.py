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

import omni.kit.test
from lightspeed.trex.project_wizard.existing_mods_page.widget.selection_tree.items import ModSelectionItem


class TestSelectionTreeItems(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        self.temp_dir.cleanup()
        self.temp_dir = None

    async def test_path_returns_path(self):
        # Arrange
        mod_dir = "ModDir"
        mod_file = "mod_file.usda"
        path = Path(self.temp_dir.name) / mod_dir / mod_file

        item = ModSelectionItem(path)

        # Act
        pass

        # Assert
        self.assertEqual(path, item.path)

    async def test_title_returns_parent_folder_and_mod_name_string(self):
        # Arrange
        mod_dir = "ModDir"
        mod_file = "mod_file.usda"
        path = Path(self.temp_dir.name) / mod_dir / mod_file

        item = ModSelectionItem(path)

        # Act
        pass

        # Assert
        self.assertEqual(str(Path(mod_dir) / mod_file), item.title)

    async def test_repr_returns_path_string(self):
        # Arrange
        mod_dir = "ModDir"
        mod_file = "mod_file.usda"
        path = Path(self.temp_dir.name) / mod_dir / mod_file

        item = ModSelectionItem(path)

        # Act
        pass

        # Assert
        self.assertEqual(str(path), str(item))
