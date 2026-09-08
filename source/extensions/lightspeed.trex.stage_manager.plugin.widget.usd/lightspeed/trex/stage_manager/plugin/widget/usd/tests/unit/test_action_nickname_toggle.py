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

__all__ = ["TestNicknameToggleActionWidgetPlugin"]

from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem

from ... import action_nickname_toggle
from ...action_nickname_toggle import NicknameToggleActionWidgetPlugin


class TestNicknameToggleActionWidgetPlugin(omni.kit.test.AsyncTestCase):
    """Test row nickname-toggle input handling."""

    async def test_build_overview_ui_release_forwards_button_without_argument_shifting(self):
        """Overview releases forward the mouse button and modifiers to the toggle callback."""
        for title, button, modifiers in (
            ("left_button_with_modifiers", 0, 8),
            ("right_button", 1, 0),
        ):
            with self.subTest(title=title):
                # Arrange
                plugin = NicknameToggleActionWidgetPlugin()
                model = Mock()
                with (
                    patch.object(action_nickname_toggle.ui, "HStack"),
                    patch.object(action_nickname_toggle.ui, "Image") as image,
                    patch.object(NicknameToggleActionWidgetPlugin, "_toggle_nickname") as toggle_nickname,
                ):
                    plugin.build_overview_ui(model)
                    mouse_released_fn = image.call_args.kwargs["mouse_released_fn"]

                    # Act
                    mouse_released_fn(12, 34, button, modifiers)

                    # Assert
                    toggle_nickname.assert_called_once_with(model, None, 12, 34, button, modifiers)

    async def test_toggle_nickname_with_non_left_button_ignores_release(self):
        """A non-left release leaves the row nickname state unchanged and unnotified."""
        # Arrange
        model = Mock()
        item = Mock(spec=StageManagerTreeItem)
        item.nickname_field = Mock()
        item.nickname_field.force_prim_name = False

        # Act
        NicknameToggleActionWidgetPlugin._toggle_nickname(model, item, button=1)

        # Assert
        self.assertFalse(item.nickname_field.force_prim_name)
        model.notify_item_changed.assert_not_called()
