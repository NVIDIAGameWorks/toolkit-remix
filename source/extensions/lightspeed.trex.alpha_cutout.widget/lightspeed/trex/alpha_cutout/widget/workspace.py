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

__all__ = ["AlphaCutoutWindow"]

import asyncio

import omni.kit.app
import omni.usd
from lightspeed.common.constants import WindowNames
from lightspeed.trex.utils.widget import WorkspaceWindowBase
from omni import ui

from .setup_ui import AlphaCutoutPane


class AlphaCutoutWindow(WorkspaceWindowBase):
    """Dockable window that hosts the alpha cutout conversion form."""

    _DEFAULT_WIDTH = 520
    _DEFAULT_HEIGHT = 800
    _DOCK_RATIO = 0.3

    def __init__(self, usd_context_name: str = ""):
        super().__init__(usd_context_name)
        self._dock_task: asyncio.Task | None = None

    @property
    def title(self) -> str:
        """Return the window title registered with the workspace.

        Returns:
            The alpha cutout window name.
        """
        return WindowNames.ALPHA_CUTOUT.value

    def menu_path(self) -> str | None:
        """Return the Window menu path of this window.

        Returns:
            Path under an Experimental submenu.
        """
        return f"Experimental/{self.title}"

    @property
    def flags(self) -> int:
        """Return window flags that delegate scrolling to the pane.

        Returns:
            Combined no-scrollbar and no-collapse flags.
        """
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_COLLAPSE

    def _update_ui(self):
        super()._update_ui()
        if self._dock_task:
            self._dock_task.cancel()
        self._dock_task = asyncio.ensure_future(self._dock_beside_viewport())

    @omni.usd.handle_exception
    async def _dock_beside_viewport(self):
        """Dock the window right of the viewport on its first show, unless the layout already placed it."""
        task = asyncio.current_task()
        try:
            await omni.kit.app.get_app().next_update_async()
            viewport = ui.Workspace.get_window(WindowNames.VIEWPORT.value)
            if self._window and not self._window.docked and viewport and viewport.docked:
                self._window.dock_in(viewport, ui.DockPosition.RIGHT, self._DOCK_RATIO)
        finally:
            if self._dock_task is task:
                self._dock_task = None

    def cleanup(self):
        if self._dock_task:
            self._dock_task.cancel()
            self._dock_task = None
        super().cleanup()

    def _create_window_ui(self) -> AlphaCutoutPane:
        """Create the conversion form bound to the window's USD context.

        Returns:
            The pane.
        """
        return AlphaCutoutPane(self._usd_context_name)

    def open_with_meshes(self, prim_paths: list[str], context_name: str) -> None:
        """Show the window with the first convertible prim up for conversion.

        Args:
            prim_paths: Selected prim paths; the first one that resolves to a target is used.
            context_name: USD context the paths belong to.
        """
        if context_name != self._usd_context_name:
            if self._content:
                self._content.destroy()
                self._content = None
            if self._window:
                self._window.frame.clear()
            self._usd_context_name = context_name
        self.show_window_fn(True)
        if self._window:
            self._window.focus()
        if self._content:
            self._content.set_from_prim_paths(prim_paths)
