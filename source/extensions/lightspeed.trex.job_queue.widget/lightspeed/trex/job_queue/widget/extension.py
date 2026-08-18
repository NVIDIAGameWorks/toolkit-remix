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

__all__ = ("JobQueueWidgetExtension",)

from contextlib import ExitStack

import carb
import omni.ext
import omni.ui
from lightspeed.trex.contexts.setup import Contexts
from omni.flux.job_queue.widget import get_display_adapter_registry
from omni.flux.job_queue.widget.model import QueueModel

from .details_workspace import JobDetailsWindow
from .display_adapter import TextureProcessingDisplayAdapter
from .workspace import JobQueueWorkspace


class JobQueueWidgetExtension(omni.ext.IExt):
    """Creates the RTX Remix job queue workspace windows."""

    def __init__(self) -> None:
        super().__init__()

        self._job_queue_workspace: JobQueueWorkspace | None = None
        self._job_details_workspace: JobDetailsWindow | None = None
        self._adapter_registered = False
        self._started = False

    def on_startup(self, _ext_id: str) -> None:
        """Create the workspace windows.

        Args:
            _ext_id: Kit extension identifier.
        """
        carb.log_info("[lightspeed.trex.job_queue.widget] Startup")
        if self._started:
            return
        registry = get_display_adapter_registry()
        registry.register(TextureProcessingDisplayAdapter)
        self._adapter_registered = True
        try:
            # Details must exist before the queue publishes its model.
            self._job_details_workspace = JobDetailsWindow()
            self._job_details_workspace.create_window()
            omni.ui.Workspace.set_show_window_fn(
                self._job_details_workspace.title, self._job_details_workspace.show_window_fn
            )

            self._job_queue_workspace = JobQueueWorkspace(
                Contexts.STAGE_CRAFT.value,
                on_model_ready=self._on_model_ready,
            )
            self._job_queue_workspace.create_window()
            omni.ui.Workspace.set_show_window_fn(
                self._job_queue_workspace.title, self._job_queue_workspace.show_window_fn
            )
            self._started = True
        except Exception:
            self._cleanup()
            raise

    def _on_model_ready(self, model: QueueModel) -> None:
        """Connect the details window to the queue model.

        Args:
            model: Queue model created by the queue workspace.
        """
        if self._job_details_workspace is not None:
            self._job_details_workspace.set_model(model)

    def on_shutdown(self) -> None:
        """Close the workspace windows."""
        carb.log_info("[lightspeed.trex.job_queue.widget] Shutdown")
        self._cleanup()

    def _cleanup(self) -> None:
        """Unregister the adapter and release any workspace objects created during startup."""

        registry = get_display_adapter_registry()
        details_workspace = self._job_details_workspace
        queue_workspace = self._job_queue_workspace
        self._job_details_workspace = None
        self._job_queue_workspace = None
        self._started = False
        cleanup = ExitStack()
        if self._adapter_registered:
            self._adapter_registered = False
            cleanup.callback(registry.unregister, TextureProcessingDisplayAdapter)
        if details_workspace:
            cleanup.callback(omni.ui.Workspace.set_show_window_fn, details_workspace.title, lambda *_: None)
            cleanup.callback(details_workspace.cleanup)
        if queue_workspace:
            cleanup.callback(omni.ui.Workspace.set_show_window_fn, queue_workspace.title, lambda *_: None)
            cleanup.callback(queue_workspace.cleanup)
        cleanup.close()
