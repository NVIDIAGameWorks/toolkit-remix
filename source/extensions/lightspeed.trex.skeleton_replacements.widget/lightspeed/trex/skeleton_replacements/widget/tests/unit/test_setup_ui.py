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

from lightspeed.trex.skeleton_replacements.widget import setup_ui as _setup_ui
from lightspeed.trex.skeleton_replacements.widget.setup_ui import SkeletonRemappingWidget


class TestSkeletonRemappingWidget(AsyncTestCase):
    async def test_clear_should_apply_root_joint_map_to_all_mesh_joints(self):
        # Arrange
        widget = SkeletonRemappingWidget.__new__(SkeletonRemappingWidget)
        widget._skel_replacement = MagicMock()
        widget._skel_replacement.get_mesh_joints.return_value = ["root", "spine", "head"]
        widget._tree_model = MagicMock()

        # Act
        widget.clear()

        # Assert
        widget._tree_model.apply_joint_map.assert_called_once_with([0, 0, 0])

    async def test_auto_remap_should_apply_generated_joint_map(self):
        # Arrange
        widget = SkeletonRemappingWidget.__new__(SkeletonRemappingWidget)
        widget._skel_replacement = MagicMock()
        widget._skel_replacement.get_mesh_joints.return_value = ["root", "spine"]
        widget._skel_replacement.get_captured_joints.return_value = ["root", "spine"]
        widget._skel_replacement.generate_joint_map.return_value = [0, 1]
        widget._tree_model = MagicMock()

        # Act
        widget.auto_remap()

        # Assert
        widget._skel_replacement.generate_joint_map.assert_called_once_with(
            ["root", "spine"], ["root", "spine"], fallback=True
        )
        widget._tree_model.apply_joint_map.assert_called_once_with([0, 1])

    async def test_repair_scale_with_repairable_replacement_should_show_repair_count(self):
        # Arrange
        widget = SkeletonRemappingWidget.__new__(SkeletonRemappingWidget)
        widget._skel_replacement = MagicMock()
        widget._skel_replacement.repair_scale.return_value = 2

        # Act
        with patch.object(_setup_ui, "TrexMessageDialog") as dialog_mock:
            widget.repair_scale()

        # Assert
        widget._skel_replacement.repair_scale.assert_called_once_with()
        dialog_mock.assert_called_once_with(
            message="Repaired 2 skinned replacement scale overrides.",
            title="Repair Complete",
            disable_cancel_button=True,
        )

    async def test_repair_scale_without_repairable_replacement_should_show_noop_message(self):
        # Arrange
        widget = SkeletonRemappingWidget.__new__(SkeletonRemappingWidget)
        widget._skel_replacement = None

        # Act
        with patch.object(_setup_ui, "TrexMessageDialog") as dialog_mock:
            widget.repair_scale()

        # Assert
        dialog_mock.assert_called_once_with(
            message="No skinned replacement scale repair was needed.",
            title="Repair Complete",
            disable_cancel_button=True,
        )

    async def test_accept_should_apply_current_joint_map_and_show_confirmation(self):
        # Arrange
        widget = SkeletonRemappingWidget.__new__(SkeletonRemappingWidget)
        widget._skel_replacement = MagicMock()
        widget._tree_model = MagicMock()
        widget._tree_model.get_joint_map.return_value = [0, 1]

        # Act
        with patch.object(_setup_ui, "TrexMessageDialog") as dialog_mock:
            widget.accept()

        # Assert
        widget._skel_replacement.apply.assert_called_once_with([0, 1])
        dialog_mock.assert_called_once_with(
            message="Joint influences have been remapped.",
            title="Applied!",
            disable_cancel_button=True,
        )

    async def test_refresh_should_update_model_and_expand_tree(self):
        # Arrange
        widget = SkeletonRemappingWidget.__new__(SkeletonRemappingWidget)
        widget._tree_model = MagicMock()
        widget._tree = MagicMock()
        skel_replacement = MagicMock()

        # Act
        widget.refresh(skel_replacement)

        # Assert
        self.assertEqual(skel_replacement, widget._skel_replacement)
        widget._tree_model.refresh.assert_called_once_with(skel_replacement)
        widget._tree.set_expanded.assert_called_once_with(None, True, True)
