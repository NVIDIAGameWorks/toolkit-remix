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

from __future__ import annotations

__all__ = ("JobDetailsWindow",)

from lightspeed.common.constants import WindowNames
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase
from omni import ui
from omni.flux.job_queue.widget.details import JobDetailsPanel
from omni.flux.job_queue.widget.model import QueueModel


class JobDetailsWindow(WorkspaceWindowBase):
    """Dockable workspace window that shows details for the selected job in the Job Queue."""

    def __init__(self, model: QueueModel | None = None) -> None:
        """Initialize the window with an optional shared queue model.

        Args:
            model: Queue model whose selected job the panel displays. Defaults to None until a model is assigned.
        """
        super().__init__()
        self._model = model
        self._content_widget: JobDetailsPanel | None = None

    def set_model(self, model: QueueModel) -> None:
        """Set the queue model observed by the details panel.

        Args:
            model: Queue model shared with the job queue workspace.
        """
        self._model = model
        if self._content_widget is not None:
            self._content_widget.set_model(model)

    @property
    def title(self) -> str:
        """Return the registered workspace window title.

        Returns:
            Workspace title used to register the Job Details window.
        """
        return WindowNames.JOB_DETAILS.value

    def menu_path(self) -> str | None:
        """Return the Window menu path for the details panel.

        Returns:
            Nested menu path for opening the Job Details window.
        """
        return f"Jobs/{self.title}"

    @property
    def flags(self) -> int:
        """Return window flags owned by the embedded details panel.

        Returns:
            Bit mask that disables scrolling on the workspace window.
        """
        return ui.WINDOW_FLAGS_NO_SCROLLBAR

    def _create_window_ui(self) -> JobDetailsPanel:
        """Create the details panel.

        Returns:
            The details panel bound to the current queue model.
        """
        self._content_widget = JobDetailsPanel(model=self._model)
        return self._content_widget
