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

import asyncio

from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase as _WorkspaceWindowBase
from omni import ui

from .setup_ui import SetupUI as _SideBarSetupUI


class SideBarWindow(_WorkspaceWindowBase):
    """Side Bar window manager"""

    @property
    def title(self) -> str:
        return _WindowNames.SIDEBAR

    @property
    def flags(self) -> int:
        return (
            ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_TITLE_BAR
            | ui.WINDOW_FLAGS_NO_COLLAPSE
            | ui.WINDOW_FLAGS_NO_CLOSE
        )

    def menu_path(self) -> str | None:
        return None

    def _create_window(self) -> ui.ToolBar:
        """Create a ToolBar instead of Window for fixed-size behavior"""
        toolbar = ui.ToolBar(
            self.title, visible=False, flags=self.flags, axis=ui.ToolBarAxis.Y, padding_x=0, padding_y=0, noTabBar=True
        )
        return toolbar

    def _create_window_ui(self):
        return _SideBarSetupUI(self._window.frame)

    def _update_ui(self):
        super()._update_ui()
        self._window.dock_tab_bar_visible = False
        self._window.dock_tab_bar_enabled = False
        asyncio.ensure_future(self._dock_to_the_left())

    async def _dock_to_the_left(self, docked: bool = False):
        dock_space = ui.Workspace.get_window("DockSpace")
        self._window.dock_in(dock_space, ui.DockPosition.LEFT)
        self._window.dock_tab_bar_enabled = False
        self._window.dock_tab_bar_visible = False
