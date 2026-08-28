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

from omni.kit.test import AsyncTestCase

from ...workspace import HomePageWindow


class TestHomePageWindow(AsyncTestCase):
    async def test_refresh_docking_when_quicklayout_docks_during_update_skips_dock_in(self):
        """Do not dock Home again when QuickLayout completes docking during the awaited update."""
        # Arrange
        workspace = HomePageWindow.__new__(HomePageWindow)
        workspace._window = MagicMock(docked=False, visible=True)
        workspace._refresh_docking_task = asyncio.current_task()
        update_count = 0

        async def next_update():
            nonlocal update_count
            update_count += 1
            if update_count == 1:
                workspace._window.docked = True

        app = MagicMock()
        app.next_update_async = AsyncMock(side_effect=next_update)

        with (
            patch("lightspeed.trex.home.widget.workspace.omni.kit.app.get_app", return_value=app),
            patch("lightspeed.trex.home.widget.workspace.ui.Workspace.get_window") as get_window_mock,
            patch("lightspeed.trex.home.widget.workspace.mark_home_interactive") as ready_mock,
        ):
            # Act
            await workspace._refresh_docking()

        # Assert
        workspace._window.dock_in.assert_not_called()
        get_window_mock.assert_not_called()
        self.assertEqual(2, update_count)
        ready_mock.assert_called_once_with()

    async def test_refresh_docking_reports_visible_home_after_final_update(self):
        """Report Home readiness after docking and the final application update."""
        # Arrange
        order = []
        workspace = HomePageWindow.__new__(HomePageWindow)
        workspace._window = MagicMock(docked=False, visible=True)
        workspace._refresh_docking_task = asyncio.current_task()
        workspace._window.dock_in.side_effect = lambda *_: order.append("dock")
        app = MagicMock()
        app.next_update_async = AsyncMock(side_effect=lambda: order.append("update"))

        with (
            patch("lightspeed.trex.home.widget.workspace.omni.kit.app.get_app", return_value=app),
            patch("lightspeed.trex.home.widget.workspace.ui.Workspace.get_window", return_value=MagicMock()),
            patch(
                "lightspeed.trex.home.widget.workspace.mark_home_interactive",
                side_effect=lambda: order.append("ready"),
            ) as ready_mock,
        ):
            # Act
            await workspace._refresh_docking()

        # Assert
        self.assertEqual(order, ["update", "dock", "update", "ready"])
        ready_mock.assert_called_once_with()
        self.assertIsNone(workspace._refresh_docking_task)

    async def test_refresh_docking_does_not_report_hidden_home(self):
        """Do not report Home readiness while the Home window is hidden."""
        # Arrange
        workspace = HomePageWindow.__new__(HomePageWindow)
        workspace._window = MagicMock(docked=True, visible=False)
        workspace._refresh_docking_task = None
        app = MagicMock()
        app.next_update_async = AsyncMock()

        with (
            patch("lightspeed.trex.home.widget.workspace.omni.kit.app.get_app", return_value=app),
            patch("lightspeed.trex.home.widget.workspace.mark_home_interactive") as ready_mock,
        ):
            # Act
            await workspace._refresh_docking()

        # Assert
        app.next_update_async.assert_awaited_once_with()
        ready_mock.assert_not_called()
