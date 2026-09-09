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

from lightspeed.trex.home.widget.recent_tree import RecentProjectDelegate


class TestRecentProjectDelegate(AsyncTestCase):
    """Test recent-project context-menu actions."""

    async def test_open_project_with_capture_action_requests_capture_workflow(self):
        """Route the capture menu action through the dedicated open event."""
        # Arrange
        delegate = RecentProjectDelegate()
        item = MagicMock()
        item.path = "/project/mod.usda"
        item.exists = True
        item.invalid = []
        callback = MagicMock()
        subscription = delegate.subscribe_item_open_project_with_capture(callback)
        menu_items = {}

        def _record_menu_item(label, **kwargs):
            menu_items[label] = kwargs

        menu = MagicMock()
        menu.__enter__.return_value = menu
        with (
            patch("lightspeed.trex.home.widget.recent_tree.delegate.ui.Menu", return_value=menu),
            patch("lightspeed.trex.home.widget.recent_tree.delegate.ui.MenuItem", side_effect=_record_menu_item),
            patch("lightspeed.trex.home.widget.recent_tree.delegate.ui.Separator"),
        ):
            delegate._context_menu_shown(MagicMock(), item)

        # Act
        menu_items["Open Project with Capture..."]["triggered_fn"]()

        # Assert
        callback.assert_called_once_with("/project/mod.usda")
        self.assertIsNotNone(subscription)
