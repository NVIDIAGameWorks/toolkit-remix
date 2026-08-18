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

import omni.kit.test
from lightspeed.common.constants import WindowNames
from omni import ui
from omni.kit import ui_test

__all__ = ("TestJobQueueWorkspace",)


class TestJobQueueWorkspace(omni.kit.test.AsyncTestCase):
    """Exercise the registered queue workspace windows through Kit UI."""

    async def test_extension_registers_and_renders_workspace_windows(self) -> None:
        """Both queue windows are registered and render their primary controls."""
        queue_title = WindowNames.JOB_QUEUE.value
        details_title = WindowNames.JOB_DETAILS.value
        queue_window = ui.Workspace.get_window(queue_title)
        details_window = ui.Workspace.get_window(details_title)

        try:
            # Open both registered workspaces through Kit and allow their real UI to render.
            ui.Workspace.show_window(details_title, True)
            ui.Workspace.show_window(queue_title, True)
            await ui_test.wait_n_updates(3)

            # Confirm each window exposes the primary control for its empty state.
            self.assertIsNotNone(queue_window)
            self.assertIsNotNone(details_window)
            self.assertTrue(queue_window.visible)
            self.assertTrue(details_window.visible)
            self.assertIsNotNone(ui_test.find(f"{queue_title}//Frame/**/Image[*].name=='Start'"))
            self.assertIsNotNone(ui_test.find(f"{details_title}//Frame/**/Label[*].name=='QueueDetailEmptyLabel'"))
        finally:
            # Close both workspaces so the next E2E scenario starts from a clean layout.
            ui.Workspace.show_window(queue_title, False)
            ui.Workspace.show_window(details_title, False)
            await ui_test.wait_n_updates(2)
