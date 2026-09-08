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

__all__ = ["TestRemapSkeletonActionWidgetPlugin"]

from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.stage_manager.plugin.tree.usd.skeleton_groups import SkeletonBoundMeshItem

from ...action_remap_skeleton import RemapSkeletonActionWidgetPlugin


class TestRemapSkeletonActionWidgetPlugin(omni.kit.test.AsyncTestCase):
    """Test remap action-image construction for compatible skeleton rows."""

    async def test_build_icon_ui_with_incompatible_item_builds_nothing(self):
        """An incompatible row does not build a remap action image."""
        # Arrange
        plugin = RemapSkeletonActionWidgetPlugin()
        model = Mock()
        item = Mock()

        # Act
        with patch.object(RemapSkeletonActionWidgetPlugin, "make_action_image") as make_action_image:
            plugin.build_icon_ui(model, item, 0, False)

        # Assert
        make_action_image.assert_not_called()

    async def test_build_icon_ui_with_disabled_compatible_item_forwards_no_action_callback(self):
        """A compatible row without a bound skeleton forwards no release callback."""
        # Arrange
        plugin = RemapSkeletonActionWidgetPlugin()
        model = Mock()
        item = Mock(spec=SkeletonBoundMeshItem)
        item.skel_prim = None
        item.skel_root = Mock()

        # Act
        with patch.object(RemapSkeletonActionWidgetPlugin, "make_action_image") as make_action_image:
            plugin.build_icon_ui(model, item, 0, False)

        # Assert
        make_action_image.assert_called_once_with(
            model=model,
            item=item,
            name="RemapSkeletonDisabled",
            tooltip="Cannot Remap Joint Indices because bound skeleton can not be found.",
            mouse_released_fn=None,
        )

    async def test_build_icon_ui_with_enabled_compatible_item_forwards_action_callback(self):
        """A compatible replacement skeleton forwards its row context and release callback."""
        # Arrange
        plugin = RemapSkeletonActionWidgetPlugin()
        model = Mock()
        item = Mock(spec=SkeletonBoundMeshItem)
        item.skel_prim = Mock()
        item.skel_prim.GetName.return_value = "ReplacementSkeleton"
        item.skel_root = Mock()
        replacement = Mock()
        replacement.captured_skeleton = object()
        replacement.original_skeleton = Mock()
        replacement.original_skeleton.GetPrim.return_value.GetName.return_value = "CapturedSkeleton"

        # Act
        with (
            patch.object(RemapSkeletonActionWidgetPlugin, "get_skel_replacement", return_value=replacement),
            patch.object(RemapSkeletonActionWidgetPlugin, "make_action_image") as make_action_image,
        ):
            plugin.build_icon_ui(model, item, 0, False)

        # Assert
        make_action_image.assert_called_once()
        arguments = make_action_image.call_args.kwargs
        self.assertIs(arguments["model"], model)
        self.assertIs(arguments["item"], item)
        self.assertEqual(arguments["name"], "RemapSkeleton")
        self.assertTrue(callable(arguments["mouse_released_fn"]))
