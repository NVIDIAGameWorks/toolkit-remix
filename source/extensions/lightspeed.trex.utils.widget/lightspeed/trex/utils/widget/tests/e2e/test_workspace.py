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

__all__ = ["TestWorkspaceLifecycle"]

import asyncio

from lightspeed.trex.utils.widget import WorkspaceWindowBase
from omni import ui
from omni.kit.test import AsyncTestCase


class _Workspace(WorkspaceWindowBase):
    """Provide a real workspace window for cleanup before its first frame."""

    title = "Workspace Lifecycle Test"
    flags = ui.WINDOW_FLAGS_NONE

    def menu_path(self) -> str | None:
        """Omit the menu entry so cleanup does not depend on application startup."""
        return None

    def _create_window_ui(self):
        """Create minimal content for the real window lifecycle."""
        ui.Label("Workspace content")


class TestWorkspaceLifecycle(AsyncTestCase):
    """Test cleanup of a real workspace window before its deferred size change."""

    async def test_cleanup_before_first_frame_cancels_default_sizing(self):
        """Cancel the deferred size change when cleanup occurs before the window's first frame."""
        # Open a real window so its first visibility callback schedules the default size change.
        workspace = _Workspace()
        self.addCleanup(workspace.cleanup)
        workspace.create_window()
        workspace.show_window_fn()
        task = workspace._WorkspaceWindowBase__default_size_task
        # Clean the window before any frame so the deferred task cannot access a destroyed window.
        workspace.cleanup()
        self.assertIsNone(workspace._WorkspaceWindowBase__default_size_task)
        # Await the original task and expect cancellation rather than a deferred size change.
        with self.assertRaises(asyncio.CancelledError):
            await task
