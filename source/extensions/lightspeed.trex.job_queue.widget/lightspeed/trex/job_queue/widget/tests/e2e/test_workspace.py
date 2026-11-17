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

import omni.ext
import omni.kit.app
import omni.kit.test
from lightspeed.common.constants import WindowNames
from lightspeed.trex.job_queue.widget.display_adapter import DISPLAY_ADAPTERS
from lightspeed.trex.job_queue.widget.extension import JobQueueWidgetExtension
from lightspeed.trex.job_queue.widget.usage_provider import get_usage_snapshot
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase
from omni import ui
from omni.flux.job_queue.core import get_job_queue
from omni.flux.job_queue.widget import get_display_adapter_registry
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
            self.assertFalse(details_window.docked)
            self.assertEqual(
                (details_window.width, details_window.height),
                (WorkspaceWindowBase._DEFAULT_WIDTH, WorkspaceWindowBase._DEFAULT_HEIGHT),
            )
        finally:
            # Close both workspaces so the next E2E scenario starts from a clean layout.
            ui.Workspace.show_window(queue_title, False)
            ui.Workspace.show_window(details_title, False)
            await ui_test.wait_n_updates(2)

    async def test_extension_restart_releases_and_registers_usage_provider(self):
        """Repeated lifecycle calls release owned registrations and restore them after restart."""
        # Find the active extension instance so lifecycle callbacks use its existing registrations.
        extension_id = (
            omni.kit.app.get_app().get_extension_manager().get_enabled_extension_id("lightspeed.trex.job_queue.widget")
        )
        # Keep the loaded modules unchanged because other tests import their classes.
        extension = next(
            instance
            for instance, _ in omni.ext._internal._extensions[extension_id]._started_extensions
            if isinstance(instance, JobQueueWidgetExtension)
        )
        queue = get_job_queue()
        registry = get_display_adapter_registry()
        self.assertIs(queue.usage_snapshot_provider, get_usage_snapshot)
        try:
            # Repeat startup, then shutdown twice, and expect all owned registrations to be absent.
            extension.on_startup(extension_id)
            extension.on_shutdown()
            extension.on_shutdown()
            self.assertIsNone(queue.usage_snapshot_provider)
            for adapter in DISPLAY_ADAPTERS:
                self.assertIsNone(registry.get_plugin_from_name(adapter.name))
            # Restart the same instance and expect its provider and every adapter to be registered again.
            extension.on_startup(extension_id)
            self.assertIs(queue.usage_snapshot_provider, get_usage_snapshot)
            for adapter in DISPLAY_ADAPTERS:
                self.assertIs(registry.get_plugin_from_name(adapter.name), adapter)
        finally:
            # Restore startup state even if an assertion fails so later workflows retain their registrations.
            extension.on_startup(extension_id)
