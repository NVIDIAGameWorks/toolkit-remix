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

__all__ = ["TestAssignCategoryActionWidgetPlugin"]

from unittest.mock import Mock, patch

import omni.kit.test

from ... import action_assign_category
from ...action_assign_category import AssignCategoryActionWidgetPlugin


class TestAssignCategoryActionWidgetPlugin(omni.kit.test.AsyncTestCase):
    """Test category action-image construction for supported row types."""

    async def test_build_icon_ui_without_item_data_builds_disabled_placeholder(self):
        """A data-less row builds only the passive category placeholder."""
        # Arrange
        plugin = AssignCategoryActionWidgetPlugin()
        model = Mock()
        item = Mock()
        item.data = None

        # Act
        with (
            patch.object(action_assign_category.ui, "Image") as image,
            patch.object(AssignCategoryActionWidgetPlugin, "make_action_image") as make_action_image,
        ):
            plugin.build_icon_ui(model, item, 0, False)

        # Assert
        image.assert_called_once()
        self.assertEqual(image.call_args.kwargs["name"], "CategoriesDisabled")
        self.assertEqual(
            image.call_args.kwargs["tooltip"],
            "Render Categories can only be assigned to mesh prims.",
        )
        make_action_image.assert_not_called()

    async def test_build_icon_ui_with_eligible_item_forwards_action_callback(self):
        """An eligible row forwards its context and release callback to the action factory."""
        # Arrange
        plugin = AssignCategoryActionWidgetPlugin()
        model = Mock()
        item = Mock()
        item.data.GetTypeName.return_value = "Mesh"

        # Act
        with patch.object(AssignCategoryActionWidgetPlugin, "make_action_image") as make_action_image:
            plugin.build_icon_ui(model, item, 0, False)

        # Assert
        make_action_image.assert_called_once()
        arguments = make_action_image.call_args.kwargs
        self.assertIs(arguments["model"], model)
        self.assertIs(arguments["item"], item)
        self.assertEqual(arguments["name"], "CategoriesWhite")
        self.assertEqual(arguments["tooltip"], "Assign Render Categories to prim")
        self.assertTrue(callable(arguments["mouse_released_fn"]))

    async def test_build_icon_ui_with_ineligible_item_forwards_no_action_callback(self):
        """An ineligible row forwards a disabled image without a release callback."""
        # Arrange
        plugin = AssignCategoryActionWidgetPlugin()
        model = Mock()
        item = Mock()
        item.data.GetTypeName.return_value = "Xform"

        # Act
        with patch.object(AssignCategoryActionWidgetPlugin, "make_action_image") as make_action_image:
            plugin.build_icon_ui(model, item, 0, False)

        # Assert
        make_action_image.assert_called_once_with(
            model=model,
            item=item,
            name="CategoriesDisabled",
            tooltip="Render Categories can only be assigned to mesh prims.",
            mouse_released_fn=None,
        )
