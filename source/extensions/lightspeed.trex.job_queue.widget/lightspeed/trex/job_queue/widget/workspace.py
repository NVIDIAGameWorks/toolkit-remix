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

__all__ = ("JobQueueWorkspace",)

from collections.abc import Callable

from lightspeed.common.constants import WindowNames
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase
from omni import ui
from omni.flux.job_queue.core import get_job_queue, handlers
from omni.flux.job_queue.widget.model import QueueModel
from omni.flux.job_queue.widget.widget import QueueWidget


class JobQueueWorkspace(WorkspaceWindowBase):
    """Workspace window that wires the Flux queue widget to RTX Remix apply handling."""

    def __init__(
        self,
        usd_context_name: str,
        on_model_ready: Callable[[QueueModel], None] | None = None,
    ) -> None:
        """Initialize the window with the queue's USD context and model callback.

        Args:
            usd_context_name: Name of the USD context used by queue operations.
            on_model_ready: Callback invoked with the queue model after the widget is created. Defaults to None.
        """
        self.__on_model_ready = on_model_ready
        super().__init__(usd_context_name)

    @property
    def title(self) -> str:
        """Return the registered workspace window title.

        Returns:
            Workspace title used to register the Job Queue window.
        """
        return WindowNames.JOB_QUEUE.value

    def menu_path(self) -> str | None:
        """Return the Window menu path for the queue.

        Returns:
            Nested menu path for opening the Job Queue window.
        """
        return f"Jobs/{self.title}"

    @property
    def flags(self) -> int:
        """Return window flags owned by the embedded queue widget.

        Returns:
            Bit mask that disables scrolling on the workspace window.
        """
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def _create_window_ui(self) -> QueueWidget:
        """Create the shared Flux queue widget.

        Returns:
            The queue widget bound to the shared Flux queue.
        """
        interface = get_job_queue()
        apply_executor = handlers.get_apply_executor()

        queue_widget = QueueWidget(
            interface=interface,
            apply_executor=apply_executor,
            context_name=self._usd_context_name,
        )

        if self.__on_model_ready is not None:
            self.__on_model_ready(queue_widget.model)

        return queue_widget
