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

from unittest.mock import MagicMock, patch

from omni.kit.test import AsyncTestCase

from lightspeed.trex.skeleton_replacements.widget.joint_tree.model import JointTreeModel


class TestJointTreeModel(AsyncTestCase):
    async def test_column_count_should_return_three_columns(self):
        # Arrange
        model = JointTreeModel()

        # Act
        result = model.column_count

        # Assert
        self.assertEqual(3, result)

    async def test_refresh_with_no_replacement_should_clear_items(self):
        # Arrange
        model = JointTreeModel()

        # Act
        model.refresh(None)

        # Assert
        self.assertEqual([], model.get_item_children())

    async def test_refresh_with_replacement_should_build_joint_hierarchy(self):
        # Arrange
        model = JointTreeModel()
        skel_replacement = MagicMock()
        skel_replacement.get_mesh_joints.return_value = ["/root", "/root/spine", "/root/spine/head"]
        skel_replacement.get_captured_joints.return_value = ["/root", "/root/spine", "/root/spine/head"]
        skel_replacement.get_joint_map.return_value = [0, 1, 2]

        # Act
        model.refresh(skel_replacement)

        # Assert
        root_items = model.get_item_children()
        self.assertEqual(1, len(root_items))
        self.assertEqual("/root", root_items[0].name_model().get_value_as_string())
        self.assertEqual(1, len(root_items[0].children))
        self.assertEqual("/root/spine", root_items[0].children[0].name_model().get_value_as_string())

    async def test_item_count_after_refresh_should_count_nested_items(self):
        # Arrange
        model = JointTreeModel()
        skel_replacement = MagicMock()
        skel_replacement.get_mesh_joints.return_value = ["/root", "/root/spine", "/root/spine/head"]
        skel_replacement.get_captured_joints.return_value = ["/root", "/root/spine", "/root/spine/head"]
        skel_replacement.get_joint_map.return_value = [0, 1, 2]
        model.refresh(skel_replacement)

        # Act
        result = model.item_count

        # Assert
        self.assertEqual(3, result)

    async def test_get_joint_map_should_return_item_indices_in_mesh_order(self):
        # Arrange
        model = JointTreeModel()
        skel_replacement = MagicMock()
        skel_replacement.get_mesh_joints.return_value = ["/root", "/root/spine", "/root/spine/head"]
        skel_replacement.get_captured_joints.return_value = ["/root", "/root/spine", "/root/spine/head"]
        skel_replacement.get_joint_map.return_value = [2, 1, 0]
        model.refresh(skel_replacement)

        # Act
        result = model.get_joint_map()

        # Assert
        self.assertEqual([2, 1, 0], result)

    async def test_apply_joint_map_should_update_item_indices(self):
        # Arrange
        model = JointTreeModel()
        skel_replacement = MagicMock()
        skel_replacement.get_mesh_joints.return_value = ["/root", "/root/spine", "/root/spine/head"]
        skel_replacement.get_captured_joints.return_value = ["/root", "/root/spine", "/root/spine/head"]
        skel_replacement.get_joint_map.return_value = [0, 0, 0]
        model.refresh(skel_replacement)

        # Act
        model.apply_joint_map([2, 1, 0])

        # Assert
        self.assertEqual([2, 1, 0], model.get_joint_map())

    async def test_get_item_value_model_for_name_column_should_return_name_model(self):
        # Arrange
        model = JointTreeModel()
        skel_replacement = MagicMock()
        skel_replacement.get_mesh_joints.return_value = ["/root"]
        skel_replacement.get_captured_joints.return_value = ["/root"]
        skel_replacement.get_joint_map.return_value = [0]
        model.refresh(skel_replacement)
        item = model.get_item_children()[0]

        # Act
        result = model.get_item_value_model(item, 0)

        # Assert
        self.assertEqual("/root", result.get_value_as_string())

    async def test_get_item_value_model_for_separator_column_should_return_none(self):
        # Arrange
        model = JointTreeModel()
        skel_replacement = MagicMock()
        skel_replacement.get_mesh_joints.return_value = ["/root"]
        skel_replacement.get_captured_joints.return_value = ["/root"]
        skel_replacement.get_joint_map.return_value = [0]
        model.refresh(skel_replacement)
        item = model.get_item_children()[0]

        # Act
        result = model.get_item_value_model(item, 1)

        # Assert
        self.assertIsNone(result)

    async def test_get_item_value_model_for_remap_column_should_return_remap_model(self):
        # Arrange
        model = JointTreeModel()
        skel_replacement = MagicMock()
        skel_replacement.get_mesh_joints.return_value = ["/root"]
        skel_replacement.get_captured_joints.return_value = ["/root"]
        skel_replacement.get_joint_map.return_value = [0]
        model.refresh(skel_replacement)
        item = model.get_item_children()[0]

        # Act
        result = model.get_item_value_model(item, 2)

        # Assert
        self.assertEqual(0, result.get_value_as_int())

    async def test_get_item_value_model_with_invalid_column_should_raise_error(self):
        # Arrange
        model = JointTreeModel()
        skel_replacement = MagicMock()
        skel_replacement.get_mesh_joints.return_value = ["/root"]
        skel_replacement.get_captured_joints.return_value = ["/root"]
        skel_replacement.get_joint_map.return_value = [0]
        model.refresh(skel_replacement)
        item = model.get_item_children()[0]

        # Act
        with self.assertRaises(ValueError) as raised:
            model.get_item_value_model(item, 3)

        # Assert
        self.assertEqual("invalid column_id", str(raised.exception))

    async def test_refresh_should_notify_item_changed(self):
        # Arrange
        model = JointTreeModel()

        # Act
        with patch.object(model, "_item_changed") as item_changed_mock:
            model.refresh(None)

        # Assert
        item_changed_mock.assert_called_once_with(None)
