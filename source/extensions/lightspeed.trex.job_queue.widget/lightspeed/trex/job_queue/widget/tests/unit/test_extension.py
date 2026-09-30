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

from unittest.mock import MagicMock, call, patch

from lightspeed.trex.asset_pipeline.core.jobs import MeshOptimizationJob, PrepareOptimizationJob, TextureOptimizationJob
from lightspeed.trex.job_queue.widget.display_adapter import DISPLAY_ADAPTERS
from lightspeed.trex.job_queue.widget.extension import JobQueueWidgetExtension
from omni.kit.test import AsyncTestCase

from ... import extension as extension_module


class TestJobQueueWidgetExtension(AsyncTestCase):
    """Test shared adapter registration through the product queue lifecycle."""

    async def test_registers_an_adapter_for_every_asset_optimization_job(self):
        """Startup registers one adapter per asset optimization job, so no stage shows an Unknown source."""
        # Arrange
        extension = JobQueueWidgetExtension()
        registry = MagicMock()

        with (
            patch(
                "lightspeed.trex.job_queue.widget.extension.get_display_adapter_registry",
                return_value=registry,
            ),
            patch("lightspeed.trex.job_queue.widget.extension.JobDetailsWindow"),
            patch("lightspeed.trex.job_queue.widget.extension.JobQueueWorkspace"),
            patch("lightspeed.trex.job_queue.widget.extension.omni.ui.Workspace.set_show_window_fn"),
        ):
            # Act
            extension.on_startup("lightspeed.trex.job_queue.widget")

        # Assert
        registered = [registered_call.args[0] for registered_call in registry.register.call_args_list]
        self.assertEqual(
            {adapter.job_type for adapter in registered},
            {PrepareOptimizationJob, TextureOptimizationJob, MeshOptimizationJob},
        )

    async def test_repeated_lifecycle_owns_one_adapter_and_workspace_pair(self):
        """Repeated lifecycle calls create and release one exact set of resources."""
        # Arrange
        extension = JobQueueWidgetExtension()
        registry = MagicMock()
        details_workspace = MagicMock(title="Job Details")
        queue_workspace = MagicMock(title="Job Queue")

        with (
            patch(
                "lightspeed.trex.job_queue.widget.extension.get_display_adapter_registry",
                return_value=registry,
            ),
            patch(
                "lightspeed.trex.job_queue.widget.extension.JobDetailsWindow",
                return_value=details_workspace,
            ),
            patch(
                "lightspeed.trex.job_queue.widget.extension.JobQueueWorkspace",
                return_value=queue_workspace,
            ),
            patch("lightspeed.trex.job_queue.widget.extension.omni.ui.Workspace.set_show_window_fn"),
        ):
            # Act
            extension.on_startup("lightspeed.trex.job_queue.widget")
            extension.on_startup("lightspeed.trex.job_queue.widget")
            extension.on_shutdown()
            extension.on_shutdown()

        # Assert
        self.assertEqual(registry.register.call_args_list, [call(adapter) for adapter in DISPLAY_ADAPTERS])
        self.assertCountEqual(registry.unregister.call_args_list, [call(adapter) for adapter in DISPLAY_ADAPTERS])
        details_workspace.create_window.assert_called_once_with()
        queue_workspace.create_window.assert_called_once_with()
        details_workspace.cleanup.assert_called_once_with()
        queue_workspace.cleanup.assert_called_once_with()

    async def test_second_registration_failure_releases_only_acquired_adapter(self):
        """Release the first adapter without removing the conflicting registration."""
        # Arrange
        extension = JobQueueWidgetExtension()
        registry = MagicMock()
        registry.register.side_effect = [None, ValueError("adapter conflict")]

        with patch.object(extension_module, "get_display_adapter_registry", return_value=registry):
            # Act
            with self.assertRaisesRegex(ValueError, "adapter conflict"):
                extension.on_startup("lightspeed.trex.job_queue.widget")
            # Assert
            self.assertEqual(registry.register.call_args_list, [call(adapter) for adapter in DISPLAY_ADAPTERS[:2]])
            registry.unregister.assert_called_once_with(DISPLAY_ADAPTERS[0])
            extension.on_shutdown()
            registry.unregister.assert_called_once_with(DISPLAY_ADAPTERS[0])

    async def test_startup_failure_rolls_back_adapter_and_created_workspaces(self):
        """A queue window failure cannot leave stale adapter or workspace state."""
        # Arrange
        extension = JobQueueWidgetExtension()
        registry = MagicMock()
        details_workspace = MagicMock(title="Job Details")
        queue_workspace = MagicMock(title="Job Queue")
        queue_workspace.create_window.side_effect = RuntimeError("queue window failed")

        # Act
        with (
            patch(
                "lightspeed.trex.job_queue.widget.extension.get_display_adapter_registry",
                return_value=registry,
            ),
            patch(
                "lightspeed.trex.job_queue.widget.extension.JobDetailsWindow",
                return_value=details_workspace,
            ),
            patch(
                "lightspeed.trex.job_queue.widget.extension.JobQueueWorkspace",
                return_value=queue_workspace,
            ),
            patch("lightspeed.trex.job_queue.widget.extension.omni.ui.Workspace.set_show_window_fn"),
        ):
            with self.assertRaisesRegex(RuntimeError, "queue window failed"):
                extension.on_startup("lightspeed.trex.job_queue.widget")

        # Assert
        self.assertCountEqual(registry.unregister.call_args_list, [call(adapter) for adapter in DISPLAY_ADAPTERS])
        details_workspace.cleanup.assert_called_once_with()
        queue_workspace.cleanup.assert_called_once_with()
        self.assertIsNone(extension._job_details_workspace)
        self.assertIsNone(extension._job_queue_workspace)
