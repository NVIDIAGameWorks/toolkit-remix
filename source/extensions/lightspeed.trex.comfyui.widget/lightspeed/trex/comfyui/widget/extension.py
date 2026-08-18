"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["ComfyUIWidgetExtension"]

from contextlib import ExitStack

import carb
from lightspeed.trex.contexts.setup import Contexts
from omni.flux.job_queue.widget import get_display_adapter_registry
from omni.ext import IExt
from omni.ui import Workspace

from .display_adapter import ComfyUIDisplayAdapter
from .workspace import ComfySetupWorkspace, WorkflowSetupWorkspace


class ComfyUIWidgetExtension(IExt):
    """Register ComfyUI workspace windows and job-queue presentation."""

    def __init__(self):
        """Initialize workspace references before extension startup."""
        super().__init__()

        self._comfy_setup_workspace: ComfySetupWorkspace | None = None
        self._workflow_setup_workspace: WorkflowSetupWorkspace | None = None
        self._adapter_registered = False
        self._started = False

    def on_startup(self, ext_id: str) -> None:
        """Initialize the extension and create the workspace windows.

        Args:
            ext_id: Identifier assigned to this extension instance by Kit.
        """
        carb.log_info("[lightspeed.trex.comfyui.widget] Startup")
        if self._started:
            return

        registry = get_display_adapter_registry()
        registry.register(ComfyUIDisplayAdapter)
        self._adapter_registered = True
        try:
            context_name = Contexts.STAGE_CRAFT.value
            self._comfy_setup_workspace = ComfySetupWorkspace(context_name)
            self._workflow_setup_workspace = WorkflowSetupWorkspace(context_name)
            ComfyUIDisplayAdapter.set_workspaces(self._comfy_setup_workspace, self._workflow_setup_workspace)

            self._comfy_setup_workspace.create_window()
            self._workflow_setup_workspace.create_window()

            Workspace.set_show_window_fn(self._comfy_setup_workspace.title, self._comfy_setup_workspace.show_window_fn)
            Workspace.set_show_window_fn(
                self._workflow_setup_workspace.title, self._workflow_setup_workspace.show_window_fn
            )
            self._started = True
        except Exception as startup_error:
            try:
                self._cleanup()
            except Exception as cleanup_error:
                raise startup_error from cleanup_error
            raise

    def on_shutdown(self) -> None:
        """Clean up resources and close the workspace windows."""
        carb.log_info("[lightspeed.trex.comfyui.widget] Shutdown")
        self._cleanup()

    def _cleanup(self) -> None:
        """Unregister the adapter and release any workspaces created during startup."""

        registry = get_display_adapter_registry()
        setup_workspace = self._comfy_setup_workspace
        workflow_workspace = self._workflow_setup_workspace
        cleanup = ExitStack()
        if self._adapter_registered:
            cleanup.callback(registry.unregister, ComfyUIDisplayAdapter)
        cleanup.callback(ComfyUIDisplayAdapter.set_workspaces, None, None)
        if setup_workspace:
            cleanup.callback(Workspace.set_show_window_fn, setup_workspace.title, lambda *_: None)
            cleanup.callback(setup_workspace.cleanup)
        if workflow_workspace:
            cleanup.callback(Workspace.set_show_window_fn, workflow_workspace.title, lambda *_: None)
            cleanup.callback(workflow_workspace.cleanup)
        cleanup.close()
        self._comfy_setup_workspace = None
        self._workflow_setup_workspace = None
        self._adapter_registered = False
        self._started = False
