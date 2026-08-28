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

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import omni.kit.test

from lightspeed.trex.ingestcraft.widget import workspace as _workspace_module


def _make_window(stagecraft_enabled):
    manager = MagicMock()
    manager.is_extension_enabled.return_value = stagecraft_enabled
    app = MagicMock()
    app.get_extension_manager.return_value = manager
    subscription = MagicMock()
    with (
        patch.object(_workspace_module._WorkspaceWindowBase, "__init__", autospec=True, return_value=None) as mock_init,
        patch.object(_workspace_module._sidebar, "register_items", return_value=subscription) as register_items,
        patch.object(_workspace_module.omni.kit.app, "get_app", return_value=app),
    ):
        window = _workspace_module.IngestCraftWindow()
    return window, subscription, mock_init, register_items


class TestIngestCraftWindow(omni.kit.test.AsyncTestCase):
    """Tests IngestCraft sidebar ownership."""

    async def test_register_sidebar_item_when_stagecraft_control_disabled_registers_ingestion(self) -> None:
        """Register Ingestion navigation in the standalone IngestCraft application."""
        # Arrange
        # Act
        window, subscription, mock_init, mock_register_items = _make_window(False)

        # Assert
        mock_init.assert_called_once_with(window)
        mock_register_items.assert_called_once()
        self.assertIs(window._sidebar_subscription, subscription)
        item = mock_register_items.call_args.args[0][0]
        self.assertEqual(item.name, "Ingestion")
        self.assertEqual(item.tooltip, "Asset Import/Ingestion")
        self.assertEqual(item.group, _workspace_module._sidebar.Groups.LAYOUTS)
        self.assertEqual(item.sort_index, 10)
        self.assertTrue(callable(item.mouse_released_fn))

    async def test_register_sidebar_item_when_stagecraft_control_enabled_does_not_register_ingestion(self) -> None:
        """Leave Ingestion navigation to StageCraft in the combined application."""
        # Arrange
        # Act
        window, _, mock_init, mock_register_items = _make_window(True)

        # Assert
        mock_init.assert_called_once_with(window)
        mock_register_items.assert_not_called()
        self.assertIsNone(window._sidebar_subscription)

    async def test_refresh_docking_releases_completed_task(self) -> None:
        """Release the owned docking task after the workspace is docked."""
        # Arrange
        window = _workspace_module.IngestCraftWindow.__new__(_workspace_module.IngestCraftWindow)
        window._window = MagicMock()
        window._refresh_docking_task = asyncio.current_task()
        app = MagicMock()
        app.next_update_async = AsyncMock()

        with (
            patch.object(_workspace_module.omni.kit.app, "get_app", return_value=app),
            patch.object(_workspace_module.ui.Workspace, "get_window", return_value=MagicMock()),
        ):
            # Act
            await window._refresh_docking()

        # Assert
        window._window.dock_in.assert_called_once()
        self.assertIsNone(window._refresh_docking_task)
