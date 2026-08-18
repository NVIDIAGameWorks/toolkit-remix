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
from unittest.mock import AsyncMock, MagicMock, call, mock_open, patch, sentinel

from lightspeed.trex.utils.widget import quicklayout
from lightspeed.trex.utils.widget.quicklayout import load_layout
from omni.kit.test import AsyncTestCase


class TestQuickLayout(AsyncTestCase):
    """Test guarded scheduling of QuickLayout loading."""

    async def test_load_layout_returns_owned_task(self):
        """Loading a layout creates and returns one named owner task."""
        # Arrange
        task = MagicMock()
        load_layout_async = MagicMock(return_value=sentinel.layout_coroutine)

        with (
            patch("lightspeed.trex.utils.widget.quicklayout._load_layout_async", load_layout_async),
            patch("lightspeed.trex.utils.widget.quicklayout.asyncio.ensure_future", return_value=task) as ensure_future,
        ):
            # Act
            result = load_layout("layout.json")

        # Assert
        self.assertIs(result, task)
        load_layout_async.assert_called_once_with("layout.json")
        ensure_future.assert_called_once_with(sentinel.layout_coroutine)
        task.set_name.assert_called_once_with("QuickLayoutLoad")

    async def test_load_layout_rejects_empty_path_without_scheduling(self):
        """An empty layout path is rejected before filesystem or task access."""
        # Arrange
        with patch("lightspeed.trex.utils.widget.quicklayout.asyncio.ensure_future") as ensure_future:
            # Act
            result = load_layout("")

        # Assert
        self.assertIsNone(result)
        ensure_future.assert_not_called()

    async def test_load_layout_reports_missing_path_through_owned_task(self):
        """A missing configured layout reports its file error through the returned task."""
        # Arrange
        missing_path = "missing-quick-layout-for-unit-test.json"

        # Act
        task = load_layout(missing_path)

        # Assert
        with self.assertRaises(FileNotFoundError):
            await task

    async def test_load_layout_cancelled_during_window_initialization_restores_previous_visibility(self):
        """Cancellation before layout loading restores windows opened for initialization."""
        # Arrange
        layout_data = {
            "title": "Test Window",
            "visible": True,
            "selected_in_dock": True,
            "dock_tab_bar_visible": False,
            "dock_tab_bar_enabled": False,
        }
        window = MagicMock(
            visible=False,
            dock_tab_bar_visible=sentinel.previous_tab_bar_visible,
            dock_tab_bar_enabled=sentinel.previous_tab_bar_enabled,
        )
        initialization_started = asyncio.Event()

        async def next_update_async():
            initialization_started.set()
            await asyncio.Event().wait()

        app = MagicMock()
        app.next_update_async.side_effect = next_update_async
        with (
            patch("builtins.open", mock_open()),
            patch.object(quicklayout.json, "load", return_value=layout_data),
            patch.object(quicklayout.ui.Workspace, "get_window", return_value=window),
            patch.object(quicklayout.ui.Workspace, "show_window") as show_window,
            patch.object(quicklayout.omni.kit.app, "get_app", return_value=app),
            patch.object(quicklayout.QuickLayout, "load_file") as quick_layout_load_file,
        ):
            task = asyncio.create_task(quicklayout._load_layout_async("layout.json"))
            await initialization_started.wait()

            # Act
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        # Assert
        self.assertEqual(
            [call("Test Window", True), call("Test Window", False)],
            show_window.call_args_list,
        )
        quick_layout_load_file.assert_not_called()
        self.assertIs(window.dock_tab_bar_visible, sentinel.previous_tab_bar_visible)
        self.assertIs(window.dock_tab_bar_enabled, sentinel.previous_tab_bar_enabled)

    async def test_load_layout_cancelled_after_quicklayout_load_restores_target_tab_settings(self):
        """Cancellation after layout loading reapplies the target layout's tab settings."""
        # Arrange
        layout_data = {
            "title": "Test Window",
            "visible": True,
            "selected_in_dock": True,
            "dock_tab_bar_visible": False,
            "dock_tab_bar_enabled": False,
        }
        window = MagicMock(
            visible=False,
            dock_tab_bar_visible=sentinel.previous_tab_bar_visible,
            dock_tab_bar_enabled=sentinel.previous_tab_bar_enabled,
        )
        update_count = 0
        layout_update_started = asyncio.Event()
        release_layout_update = asyncio.Event()

        async def next_update_async():
            nonlocal update_count
            update_count += 1
            if update_count == 2:
                layout_update_started.set()
                await release_layout_update.wait()

        app = MagicMock()
        app.next_update_async.side_effect = next_update_async
        with (
            patch("builtins.open", mock_open()),
            patch.object(quicklayout.json, "load", return_value=layout_data),
            patch.object(quicklayout.ui.Workspace, "get_window", return_value=window),
            patch.object(quicklayout.ui.Workspace, "show_window") as show_window,
            patch.object(quicklayout.omni.kit.app, "get_app", return_value=app),
            patch.object(quicklayout.QuickLayout, "load_file") as quick_layout_load_file,
        ):
            task = asyncio.create_task(quicklayout._load_layout_async("layout.json"))
            await layout_update_started.wait()

            # Act
            task.cancel()
            self.assertIs(window.dock_tab_bar_visible, sentinel.previous_tab_bar_visible)
            release_layout_update.set()
            with self.assertRaises(asyncio.CancelledError):
                await task

        # Assert
        show_window.assert_called_once_with("Test Window", True)
        quick_layout_load_file.assert_called_once_with("layout.json")
        self.assertFalse(window.dock_tab_bar_visible)
        self.assertFalse(window.dock_tab_bar_enabled)

    async def test_post_load_failure_does_not_mask_cancellation(self):
        """A settling failure is logged while caller cancellation remains observable."""
        # Arrange
        layout_data = {"title": "Test Window", "visible": True}
        window = MagicMock(visible=True)
        update_started = asyncio.Event()
        release_update = asyncio.Event()

        async def next_update_async():
            update_started.set()
            await release_update.wait()

        app = MagicMock()
        app.next_update_async.side_effect = next_update_async
        settle_error = RuntimeError("post-load update failed")
        with (
            patch("builtins.open", mock_open()),
            patch.object(quicklayout.json, "load", return_value=layout_data),
            patch.object(quicklayout.ui.Workspace, "get_window", return_value=window),
            patch.object(quicklayout.omni.kit.app, "get_app", return_value=app),
            patch.object(quicklayout.QuickLayout, "load_file"),
            patch.object(quicklayout, "_finish_task", new=AsyncMock(side_effect=settle_error)),
            patch.object(quicklayout.carb, "log_error") as log_error,
        ):
            task = asyncio.create_task(quicklayout._load_layout_async("layout.json"))
            await update_started.wait()

            # Act
            task.cancel()
            release_update.set()
            with self.assertRaises(asyncio.CancelledError) as error_context:
                await task

        # Assert
        self.assertIsInstance(error_context.exception, asyncio.CancelledError)
        log_error.assert_called_once_with("Deferred layout update failed during cancellation: post-load update failed")

    async def test_load_layout_calls_the_layout_loaded_event_after_a_successful_load(self):
        """A successful layout load calls the layout-loaded event once."""
        # Arrange
        layout_data = {"title": "Test Window", "visible": True}
        window = MagicMock(visible=True)
        app = MagicMock()
        app.next_update_async = AsyncMock()
        callback = MagicMock()
        _subscription = quicklayout.subscribe_layout_loaded(callback)
        with (
            patch("builtins.open", mock_open()),
            patch.object(quicklayout.json, "load", return_value=layout_data),
            patch.object(quicklayout.ui.Workspace, "get_window", return_value=window),
            patch.object(quicklayout.omni.kit.app, "get_app", return_value=app),
            patch.object(quicklayout.QuickLayout, "load_file"),
        ):
            # Act
            await quicklayout._load_layout_async("layout.json")

        # Assert
        callback.assert_called_once_with()

    async def test_load_layout_does_not_call_the_event_when_the_load_fails(self):
        """A layout load that raises from QuickLayout.load_file calls no event."""
        # Arrange
        layout_data = {"title": "Test Window", "visible": True}
        window = MagicMock(visible=True)
        app = MagicMock()
        callback = MagicMock()
        _subscription = quicklayout.subscribe_layout_loaded(callback)
        with (
            patch("builtins.open", mock_open()),
            patch.object(quicklayout.json, "load", return_value=layout_data),
            patch.object(quicklayout.ui.Workspace, "get_window", return_value=window),
            patch.object(quicklayout.omni.kit.app, "get_app", return_value=app),
            patch.object(quicklayout.QuickLayout, "load_file", side_effect=RuntimeError("load failed")),
        ):
            # Act
            with self.assertRaises(RuntimeError):
                await quicklayout._load_layout_async("layout.json")

        # Assert
        callback.assert_not_called()

    async def test_load_layout_calls_the_event_when_cancelled_after_the_layout_loaded(self):
        """A load that the caller cancels after QuickLayout.load_file still calls the event.

        The layout already replaced the geometry of every window, so a window that owns a default size must
        still learn about the load.
        """
        # Arrange
        layout_data = {"title": "Test Window", "visible": True}
        window = MagicMock(visible=True)
        app = MagicMock()
        app.next_update_async = AsyncMock(side_effect=asyncio.CancelledError)
        callback = MagicMock()
        _subscription = quicklayout.subscribe_layout_loaded(callback)
        with (
            patch("builtins.open", mock_open()),
            patch.object(quicklayout.json, "load", return_value=layout_data),
            patch.object(quicklayout.ui.Workspace, "get_window", return_value=window),
            patch.object(quicklayout.omni.kit.app, "get_app", return_value=app),
            patch.object(quicklayout.QuickLayout, "load_file"),
        ):
            # Act
            with self.assertRaises(asyncio.CancelledError):
                await quicklayout._load_layout_async("layout.json")

        # Assert
        callback.assert_called_once_with()
