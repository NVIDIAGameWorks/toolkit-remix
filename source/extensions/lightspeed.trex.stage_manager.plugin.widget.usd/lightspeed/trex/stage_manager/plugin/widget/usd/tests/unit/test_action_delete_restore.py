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

from unittest.mock import MagicMock, Mock, patch

import omni.kit.test
from lightspeed.trex.stage_manager.plugin.widget.usd import action_delete_restore
from lightspeed.trex.stage_manager.plugin.widget.usd.action_delete_restore import DeleteRestoreActionWidgetPlugin
from omni.kit.notification_manager import NotificationStatus

__all__ = ["TestDeleteRestoreActionWidgetPluginUnit"]


class TestDeleteRestoreActionWidgetPluginUnit(omni.kit.test.AsyncTestCase):
    """Test delete and notification orchestration without a real USD stage."""

    def _make_plugin(self, regular_paths: list[str], capture_paths: list[str]) -> DeleteRestoreActionWidgetPlugin:
        """Create a plugin with selection and deletion collaborators mocked."""
        plugin = object.__new__(DeleteRestoreActionWidgetPlugin)
        plugin._context_name = ""
        plugin._core = None
        plugin._layer_manager = None
        plugin._restore_context_menu = None
        plugin._get_selected_by_action = Mock(
            side_effect=lambda action: {
                plugin.ActionType.DELETE: regular_paths,
                plugin.ActionType.DELETECAPTURE: capture_paths,
            }[action]
        )
        plugin._delete_prim_cb = Mock()
        plugin._delete_capture_prim_cb = Mock()
        return plugin

    def _make_context(
        self, plugin: DeleteRestoreActionWidgetPlugin, action_types: list[DeleteRestoreActionWidgetPlugin.ActionType]
    ) -> MagicMock:
        """Create a USD context whose selected valid prims have the supplied action types."""
        paths = [f"/RootNode/Prim{index}" for index in range(len(action_types))]
        prims = [MagicMock() for _ in action_types]
        for prim in prims:
            prim.IsValid.return_value = True

        context = MagicMock()
        context.get_selection.return_value.get_selected_prim_paths.return_value = paths
        context.get_stage.return_value.GetPrimAtPath.side_effect = dict(zip(paths, prims, strict=True)).__getitem__
        plugin._get_prim_action_type = Mock(side_effect=dict(zip(prims, action_types, strict=True)).__getitem__)
        return context

    async def test_delete_selected_prims_with_regular_and_capture_paths_groups_callbacks(self):
        """Regular and capture selections are deleted inside one undo group."""
        # Arrange
        plugin = self._make_plugin(["/RootNode/Regular"], ["/RootNode/Capture"])

        # Act
        with patch.object(action_delete_restore.omni.kit.undo, "group") as undo_group:
            plugin.delete_selected_prims()

        # Assert
        undo_group.assert_called_once_with()
        plugin._delete_prim_cb.assert_called_once_with(paths=["/RootNode/Regular"], use_undo_group=False)
        plugin._delete_capture_prim_cb.assert_called_once_with(paths=["/RootNode/Capture"], use_undo_group=False)

    async def test_delete_selected_prims_without_actionable_paths_skips_undo_group(self):
        """An ineligible selection does not create an empty undo group."""
        # Arrange
        plugin = self._make_plugin([], [])

        # Act
        with patch.object(action_delete_restore.omni.kit.undo, "group") as undo_group:
            plugin.delete_selected_prims()

        # Assert
        undo_group.assert_not_called()
        plugin._delete_prim_cb.assert_not_called()
        plugin._delete_capture_prim_cb.assert_not_called()

    async def test_delete_selected_prims_with_one_ineligible_prim_posts_singular_warning(self):
        """One ineligible selected prim produces the singular warning."""
        # Arrange
        plugin = self._make_plugin([], [])
        context = self._make_context(plugin, [plugin.ActionType.RESTOREDISABLED])

        # Act
        with (
            patch.object(action_delete_restore.omni.usd, "get_context", return_value=context),
            patch.object(action_delete_restore, "post_notification") as post_notification,
        ):
            plugin.delete_selected_prims(notify_ineligible=True)

        # Assert
        post_notification.assert_called_once_with(
            "The selected asset can't be deleted.", status=NotificationStatus.WARNING
        )

    async def test_delete_selected_prims_with_multiple_ineligible_prims_posts_plural_warning(self):
        """Multiple ineligible selected prims produce the plural warning."""
        # Arrange
        plugin = self._make_plugin([], [])
        context = self._make_context(
            plugin,
            [plugin.ActionType.RESTOREDISABLED, plugin.ActionType.RESTOREDISABLED],
        )

        # Act
        with (
            patch.object(action_delete_restore.omni.usd, "get_context", return_value=context),
            patch.object(action_delete_restore, "post_notification") as post_notification,
        ):
            plugin.delete_selected_prims(notify_ineligible=True)

        # Assert
        post_notification.assert_called_once_with(
            "The selected assets can't be deleted.", status=NotificationStatus.WARNING
        )

    async def test_delete_selected_prims_with_mixed_selection_posts_partial_warning_and_deletes(self):
        """A mixed selection warns and still deletes its actionable prims."""
        # Arrange
        plugin = self._make_plugin(["/RootNode/Regular"], [])
        context = self._make_context(
            plugin,
            [plugin.ActionType.DELETE, plugin.ActionType.RESTOREDISABLED],
        )

        # Act
        with (
            patch.object(action_delete_restore.omni.usd, "get_context", return_value=context),
            patch.object(action_delete_restore, "post_notification") as post_notification,
            patch.object(action_delete_restore.omni.kit.undo, "group"),
        ):
            plugin.delete_selected_prims(notify_ineligible=True)

        # Assert
        post_notification.assert_called_once_with(
            "Some selected assets can't be deleted.", status=NotificationStatus.WARNING
        )
        plugin._delete_prim_cb.assert_called_once_with(paths=["/RootNode/Regular"], use_undo_group=False)
