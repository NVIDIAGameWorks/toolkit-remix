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

__all__ = ["ComfySetupWorkspace", "WorkflowSetupWorkspace"]

from lightspeed.common.constants import WindowNames
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase
from omni import ui

from .setup.widget import ComfySetupAdvancedWidget
from .workflow.widget import WorkflowSetupWidget


class ComfySetupWorkspace(WorkspaceWindowBase):
    """Host the AI Tools ComfyUI instance setup workspace."""

    def set_context_name(self, context_name: str) -> None:
        """Rebuild setup content when routing the window to another context.

        Args:
            context_name: USD context that the rebuilt setup widget should control.
        """
        if context_name == self._usd_context_name:
            return
        if self._content:
            self._content.destroy()
            self._content = None
        if self._window:
            self._window.frame.clear()
        self._usd_context_name = context_name
        if self._window and self._window.visible:
            self._update_ui()

    @property
    def title(self) -> str:
        """Return the setup workspace title.

        Returns:
            Registered ComfyUI setup window name.
        """
        return WindowNames.COMFYUI_SETUP.value

    def menu_path(self) -> str | None:
        """Return the setup workspace menu path.

        Returns:
            AI Tools menu path used to show the setup window.
        """
        return f"AI Tools/{self.title}"

    @property
    def flags(self) -> int:
        """Return window flags that delegate scrolling to child widgets.

        Returns:
            Combined no-scrollbar and no-mouse-scroll window flags.
        """
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def _create_window_ui(self):
        """Create the external-server setup widget.

        Returns:
            Setup widget bound to the workspace's current USD context.
        """
        return ComfySetupAdvancedWidget(context_name=self._usd_context_name)


class WorkflowSetupWorkspace(WorkspaceWindowBase):
    """Host the AI Tools ComfyUI workflow workspace."""

    def set_context_name(self, context_name: str) -> None:
        """Rebuild workflow content when routing the window to another context.

        Args:
            context_name: USD context that the rebuilt workflow widget should control.
        """
        if context_name == self._usd_context_name:
            return
        if self._content:
            self._content.destroy()
            self._content = None
        if self._window:
            self._window.frame.clear()
        self._usd_context_name = context_name
        if self._window and self._window.visible:
            self._update_ui()

    @property
    def title(self) -> str:
        """Return the workflow workspace title.

        Returns:
            Registered ComfyUI workflow window name.
        """
        return WindowNames.COMFYUI_WORKFLOW.value

    def menu_path(self) -> str | None:
        """Return the workflow workspace menu path.

        Returns:
            AI Tools menu path used to show the workflow window.
        """
        return f"AI Tools/{self.title}"

    @property
    def flags(self) -> int:
        """Return window flags that delegate scrolling to child widgets.

        Returns:
            Combined no-scrollbar and no-mouse-scroll window flags.
        """
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def _create_window_ui(self):
        """Create the context-aware workflow setup widget.

        Returns:
            Workflow widget bound to the workspace's current USD context.
        """
        return WorkflowSetupWidget(context_name=self._usd_context_name)
