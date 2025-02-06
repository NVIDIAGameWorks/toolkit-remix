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

from unittest.mock import Mock

from omni.flux.custom_tags.window.selection_tree import TagsEditItem, TagsSelectionItem
from omni.kit.test import AsyncTestCase
from pxr import Sdf


class TestTagsSelectionItem(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        pass

    # After running each test
    async def tearDown(self):
        pass

    async def test_path_returns_item_path(self):
        # Arrange
        expected_path = Sdf.Path("/Test/Tag.collection:Test_Tag")
        item = TagsSelectionItem(expected_path)

        # Act
        value = item.path

        # Assert
        self.assertEqual(value, expected_path)

    async def test_title_returns_tag_name(self):
        # Arrange
        for test_data in [
            ("/Test/Tag.collection:Test_Tag", "Test_Tag"),
            ("/Random/Path/Prim", None),
            ("/Material_Prim/Shader.inputs:color", "color"),
        ]:
            input_path, expected_name = test_data
            with self.subTest(name=f"input_path_{input_path}_expected_name_{expected_name}"):
                item = TagsSelectionItem(Sdf.Path(input_path))

                # Act
                value = item.title

                # Assert
                self.assertEqual(value, expected_name)

    async def test_stringify_returns_item_path(self):
        # Arrange
        expected_path = "/Test/Tag.collection:Test_Tag"
        item = TagsSelectionItem(Sdf.Path(expected_path))

        # Act
        value = str(item)

        # Assert
        self.assertEqual(value, expected_path)


class TestTagsEditItem(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        pass

    # After running each test
    async def tearDown(self):
        pass

    async def test_original_item_returns_original_item(self):
        # Arrange
        for has_original_item in [True, False]:
            with self.subTest(name=f"has_original_item_{has_original_item}"):
                if has_original_item:
                    original_item = Mock()
                    original_item.title = "Test_Tag"
                else:
                    original_item = None

                item = TagsEditItem(original_item=original_item)

                # Act
                value = item.original_item

                # Assert
                self.assertEqual(value, original_item)

    async def test_value_returns_title_or_default_value(self):
        # Arrange
        for has_original_item in [True, False]:
            with self.subTest(name=f"has_original_item_{has_original_item}"):
                expected_value = "Test_Tag" if has_original_item else "New_Tag"
                if has_original_item:
                    original_item = Mock()
                    original_item.title = "Test_Tag"
                else:
                    original_item = None

                item = TagsEditItem(original_item=original_item)

                # Act
                value = item.value

                # Assert
                self.assertEqual(value, expected_value)
