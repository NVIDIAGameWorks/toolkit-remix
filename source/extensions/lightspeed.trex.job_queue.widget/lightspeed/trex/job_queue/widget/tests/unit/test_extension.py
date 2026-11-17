"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from lightspeed.trex.job_queue.widget import extension
from lightspeed.trex.job_queue.widget.display_adapter import DISPLAY_ADAPTERS
from lightspeed.trex.job_queue.widget.extension import JobQueueWidgetExtension
from lightspeed.trex.job_queue.widget.usage_provider import get_usage_snapshot
from omni.kit.test import AsyncTestCase


class TestJobQueueWidgetExtension(AsyncTestCase):
    """Check provider ownership and resource cleanup after partial startup."""

    async def test_secondary_shutdown_preserves_active_usage_provider(self):
        """Shutdown of a secondary instance preserves the active provider."""
        # Arrange
        queue = SimpleNamespace(usage_snapshot_provider=get_usage_snapshot)
        secondary = JobQueueWidgetExtension()
        with (
            patch.object(extension, "get_job_queue", return_value=queue),
            patch.object(extension, "get_display_adapter_registry") as registry,
        ):
            # Act
            secondary.on_shutdown()

        # Assert
        self.assertIs(queue.usage_snapshot_provider, get_usage_snapshot)
        registry.return_value.unregister.assert_not_called()

    async def test_secondary_startup_is_rejected_and_preserves_active_usage_provider(self):
        """Rejected startup of a secondary instance preserves the active provider."""
        # Arrange
        queue = SimpleNamespace(usage_snapshot_provider=get_usage_snapshot)
        secondary = JobQueueWidgetExtension()
        with (
            patch.object(extension, "get_job_queue", return_value=queue),
            patch.object(extension, "get_display_adapter_registry") as registry,
        ):
            try:
                # Act
                with self.assertRaisesRegex(RuntimeError, "already has a usage snapshot provider"):
                    secondary.on_startup("lightspeed.trex.job_queue.widget")
            finally:
                secondary.on_shutdown()

        # Assert
        self.assertIs(queue.usage_snapshot_provider, get_usage_snapshot)
        registry.return_value.register.assert_not_called()
        registry.return_value.unregister.assert_not_called()

    async def test_second_registration_failure_releases_only_acquired_adapter(self):
        """An adapter conflict releases only the adapter that this instance registered."""
        # Arrange
        queue = SimpleNamespace(usage_snapshot_provider=None)
        widget_extension = JobQueueWidgetExtension()
        registry = MagicMock()
        registry.register.side_effect = [None, ValueError("adapter conflict")]
        with (
            patch.object(extension, "get_job_queue", return_value=queue),
            patch.object(extension, "get_display_adapter_registry", return_value=registry),
        ):
            try:
                # Act
                with self.assertRaisesRegex(ValueError, "adapter conflict"):
                    widget_extension.on_startup("lightspeed.trex.job_queue.widget")

                # Assert
                self.assertEqual(registry.register.call_args_list, [call(adapter) for adapter in DISPLAY_ADAPTERS[:2]])
                registry.unregister.assert_called_once_with(DISPLAY_ADAPTERS[0])
                self.assertIsNone(queue.usage_snapshot_provider)
            finally:
                widget_extension.on_shutdown()

    async def test_queue_window_failure_releases_adapters_and_created_workspaces(self):
        """A queue window failure releases all acquired adapters and both workspaces."""
        # Arrange
        queue = SimpleNamespace(usage_snapshot_provider=None)
        widget_extension = JobQueueWidgetExtension()
        registry = MagicMock()
        details_workspace = MagicMock(title="Job Details")
        queue_workspace = MagicMock(title="Job Queue")
        queue_workspace.create_window.side_effect = RuntimeError("queue window failed")
        with (
            patch.object(extension, "get_job_queue", return_value=queue),
            patch.object(extension, "get_display_adapter_registry", return_value=registry),
            patch.object(extension, "JobDetailsWindow", return_value=details_workspace),
            patch.object(extension, "JobQueueWorkspace", return_value=queue_workspace),
            patch.object(extension.omni.ui.Workspace, "set_show_window_fn"),
        ):
            try:
                # Act
                with self.assertRaisesRegex(RuntimeError, "queue window failed"):
                    widget_extension.on_startup("lightspeed.trex.job_queue.widget")

                # Assert
                self.assertEqual(registry.register.call_args_list, [call(adapter) for adapter in DISPLAY_ADAPTERS])
                self.assertCountEqual(
                    registry.unregister.call_args_list, [call(adapter) for adapter in DISPLAY_ADAPTERS]
                )
                details_workspace.cleanup.assert_called_once_with()
                queue_workspace.cleanup.assert_called_once_with()
                self.assertIsNone(widget_extension._job_details_workspace)
                self.assertIsNone(widget_extension._job_queue_workspace)
                self.assertIsNone(queue.usage_snapshot_provider)
            finally:
                widget_extension.on_shutdown()
