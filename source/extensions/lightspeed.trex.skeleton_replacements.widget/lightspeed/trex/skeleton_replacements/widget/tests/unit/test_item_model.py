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

from omni.kit.test import AsyncTestCase

from lightspeed.trex.skeleton_replacements.widget.joint_tree.item_model import (
    ComboListModel,
    Item,
    JointItem,
    RemappedJointModel,
)


class TestJointItemModel(AsyncTestCase):
    async def test_item_repr_should_wrap_text_in_quotes(self):
        # Arrange
        item = Item("joint")

        # Act
        result = repr(item)

        # Assert
        self.assertEqual('"joint"', result)

    async def test_combo_list_model_with_default_index_should_select_current_item(self):
        # Arrange
        model = ComboListModel(["root", "spine"], default_index=1)

        # Act
        result = model.get_current_string()

        # Assert
        self.assertEqual("spine", result)

    async def test_combo_list_model_with_invalid_default_index_should_raise_error(self):
        # Arrange
        item_list = ["root"]

        # Act
        with self.assertRaises(ValueError) as raised:
            ComboListModel(item_list, default_index=1)

        # Assert
        self.assertEqual("Invalid default index", str(raised.exception))

    async def test_combo_list_model_set_current_index_should_update_selection(self):
        # Arrange
        model = ComboListModel(["root", "spine"], default_index=0)

        # Act
        model.set_current_index(1)

        # Assert
        self.assertEqual(1, model.get_current_index())

    async def test_combo_list_model_get_item_children_should_return_items(self):
        # Arrange
        model = ComboListModel(["root", "spine"], default_index=0)

        # Act
        result = model.get_item_children(None)

        # Assert
        self.assertEqual(["root", "spine"], [item.text for item in result])

    async def test_combo_list_model_get_item_value_model_with_item_should_return_string_model(self):
        # Arrange
        model = ComboListModel(["root"], default_index=0)
        item = model.get_item_children(None)[0]

        # Act
        result = model.get_item_value_model(item)

        # Assert
        self.assertEqual("root", result.get_value_as_string())

    async def test_combo_list_model_get_item_value_model_count_with_item_should_return_one(self):
        # Arrange
        model = ComboListModel(["root"], default_index=0)
        item = model.get_item_children(None)[0]

        # Act
        result = model.get_item_value_model_count(item)

        # Assert
        self.assertEqual(1, result)

    async def test_remapped_joint_model_with_missing_default_should_select_last_joint(self):
        # Arrange
        model = RemappedJointModel(["root", "spine", "head"], default_index=-1)

        # Act
        result = model.get_current_string()

        # Assert
        self.assertEqual("head", result)

    async def test_joint_item_with_children_should_report_can_have_children(self):
        # Arrange
        parent = JointItem("/root", 0, ["/root"], remapped_index=0)
        child = JointItem("/root/spine", 1, ["/root"], remapped_index=0)

        # Act
        child.parent = parent

        # Assert
        self.assertTrue(parent.can_have_children)

    async def test_joint_item_remap_model_should_use_requested_default(self):
        # Arrange
        item = JointItem("/root/spine", 1, ["/root", "/root/spine"], remapped_index=1)

        # Act
        result = item.remap_model().get_current_index()

        # Assert
        self.assertEqual(1, result)
