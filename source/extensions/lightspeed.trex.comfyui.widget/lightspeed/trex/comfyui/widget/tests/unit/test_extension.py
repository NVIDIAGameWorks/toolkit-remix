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
from lightspeed.trex.comfyui.widget.display_adapter import ComfyUIDisplayAdapter
from lightspeed.trex.comfyui.widget.extension import ComfyUIWidgetExtension


class TestComfyUIWidgetExtension(AsyncTestCase):
    """Test ComfyUI widget extension lifecycle and integration behavior."""

    async def test_startup_uses_app_context_for_both_workspaces(self):
        """Startup creates both workspaces with the shared application context."""
        # Arrange
        extension = ComfyUIWidgetExtension()
        registry = MagicMock()

        # Act
        with (
            patch("lightspeed.trex.comfyui.widget.extension.get_display_adapter_registry", return_value=registry),
            patch("lightspeed.trex.comfyui.widget.extension.ComfySetupWorkspace") as setup_workspace,
            patch("lightspeed.trex.comfyui.widget.extension.WorkflowSetupWorkspace") as workflow_workspace,
            patch("lightspeed.trex.comfyui.widget.extension.Workspace.set_show_window_fn"),
            patch.object(ComfyUIDisplayAdapter, "set_workspaces", create=True) as set_workspaces,
        ):
            extension.on_startup("lightspeed.trex.comfyui.widget")

        # Assert
        setup_workspace.assert_called_once_with("")
        workflow_workspace.assert_called_once_with("")
        registry.register.assert_called_once_with(ComfyUIDisplayAdapter)
        set_workspaces.assert_called_once_with(setup_workspace.return_value, workflow_workspace.return_value)

    async def test_shutdown_cleans_and_releases_both_workspaces(self):
        """Shutdown cleans both workspaces and releases their references."""
        # Arrange
        extension = ComfyUIWidgetExtension()
        registry = MagicMock()
        setup_workspace = MagicMock(title="ComfyUI Setup")
        workflow_workspace = MagicMock(title="Workflow Setup")

        # Act
        with (
            patch("lightspeed.trex.comfyui.widget.extension.get_display_adapter_registry", return_value=registry),
            patch("lightspeed.trex.comfyui.widget.extension.ComfySetupWorkspace", return_value=setup_workspace),
            patch("lightspeed.trex.comfyui.widget.extension.WorkflowSetupWorkspace", return_value=workflow_workspace),
            patch("lightspeed.trex.comfyui.widget.extension.Workspace.set_show_window_fn") as set_show_window_fn,
            patch.object(ComfyUIDisplayAdapter, "set_workspaces", create=True) as set_workspaces,
        ):
            extension.on_startup("lightspeed.trex.comfyui.widget")
            extension.on_shutdown()

        # Assert
        registry.unregister.assert_called_once_with(ComfyUIDisplayAdapter)
        setup_workspace.cleanup.assert_called_once_with()
        workflow_workspace.cleanup.assert_called_once_with()
        self.assertEqual(set_show_window_fn.call_count, 4)
        self.assertEqual(set_workspaces.call_args_list[-1].args, (None, None))
        self.assertIsNone(extension._comfy_setup_workspace)
        self.assertIsNone(extension._workflow_setup_workspace)

    async def test_startup_failure_rolls_back_adapter_and_both_workspaces(self):
        """A window creation failure cannot leave stale adapter or workspace state."""
        # Arrange
        extension = ComfyUIWidgetExtension()
        registry = MagicMock()
        setup_workspace = MagicMock(title="ComfyUI Setup")
        workflow_workspace = MagicMock(title="Workflow Setup")
        workflow_workspace.create_window.side_effect = RuntimeError("window failed")

        # Act
        with (
            patch("lightspeed.trex.comfyui.widget.extension.get_display_adapter_registry", return_value=registry),
            patch("lightspeed.trex.comfyui.widget.extension.ComfySetupWorkspace", return_value=setup_workspace),
            patch("lightspeed.trex.comfyui.widget.extension.WorkflowSetupWorkspace", return_value=workflow_workspace),
            patch("lightspeed.trex.comfyui.widget.extension.Workspace.set_show_window_fn"),
            patch.object(ComfyUIDisplayAdapter, "set_workspaces") as set_workspaces,
        ):
            with self.assertRaisesRegex(RuntimeError, "window failed"):
                extension.on_startup("lightspeed.trex.comfyui.widget")

        # Assert
        registry.unregister.assert_called_once_with(ComfyUIDisplayAdapter)
        setup_workspace.cleanup.assert_called_once_with()
        workflow_workspace.cleanup.assert_called_once_with()
        self.assertEqual(set_workspaces.call_args_list[-1].args, (None, None))
        self.assertIsNone(extension._comfy_setup_workspace)
        self.assertIsNone(extension._workflow_setup_workspace)

    async def test_repeated_lifecycle_retains_one_workspace_pair(self):
        """Repeated startup and shutdown create and clean one workspace pair."""
        # Arrange
        extension = ComfyUIWidgetExtension()
        registry = MagicMock()
        setup_workspace = MagicMock(title="ComfyUI Setup")
        workflow_workspace = MagicMock(title="ComfyUI Workflow")

        with (
            patch("lightspeed.trex.comfyui.widget.extension.get_display_adapter_registry", return_value=registry),
            patch("lightspeed.trex.comfyui.widget.extension.ComfySetupWorkspace", return_value=setup_workspace),
            patch("lightspeed.trex.comfyui.widget.extension.WorkflowSetupWorkspace", return_value=workflow_workspace),
            patch("lightspeed.trex.comfyui.widget.extension.Workspace.set_show_window_fn"),
            patch.object(ComfyUIDisplayAdapter, "set_workspaces"),
        ):
            # Act
            extension.on_startup("lightspeed.trex.comfyui.widget")
            extension.on_startup("lightspeed.trex.comfyui.widget")
            extension.on_shutdown()
            extension.on_shutdown()

        # Assert
        registry.register.assert_called_once_with(ComfyUIDisplayAdapter)
        registry.unregister.assert_called_once_with(ComfyUIDisplayAdapter)
        setup_workspace.create_window.assert_called_once_with()
        workflow_workspace.create_window.assert_called_once_with()
        setup_workspace.cleanup.assert_called_once_with()
        workflow_workspace.cleanup.assert_called_once_with()

    async def test_startup_failure_remains_primary_when_cleanup_also_fails(self):
        """Cleanup diagnostics cannot replace the startup error shown to the owner."""
        # Arrange
        extension = ComfyUIWidgetExtension()
        registry = MagicMock()
        setup_workspace = MagicMock(title="ComfyUI Setup")
        workflow_workspace = MagicMock(title="ComfyUI Workflow")
        startup_error = RuntimeError("window failed")
        cleanup_error = RuntimeError("cleanup failed")
        workflow_workspace.create_window.side_effect = startup_error
        workflow_workspace.cleanup.side_effect = cleanup_error

        with (
            patch("lightspeed.trex.comfyui.widget.extension.get_display_adapter_registry", return_value=registry),
            patch("lightspeed.trex.comfyui.widget.extension.ComfySetupWorkspace", return_value=setup_workspace),
            patch("lightspeed.trex.comfyui.widget.extension.WorkflowSetupWorkspace", return_value=workflow_workspace),
            patch("lightspeed.trex.comfyui.widget.extension.Workspace.set_show_window_fn"),
            patch.object(ComfyUIDisplayAdapter, "set_workspaces"),
        ):
            # Act
            with self.assertRaises(RuntimeError) as error_context:
                extension.on_startup("lightspeed.trex.comfyui.widget")

        # Assert
        self.assertIs(error_context.exception, startup_error)
        self.assertIs(error_context.exception.__cause__, cleanup_error)
        self.assertIs(extension._workflow_setup_workspace, workflow_workspace)
        self.assertTrue(extension._adapter_registered)
