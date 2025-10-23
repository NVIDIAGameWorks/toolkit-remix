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

import omni.kit
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase as _WorkspaceWindowBase
from omni import ui

from .home_widget import HomePageWidget as _HomePageWidget


class HomePageWindow(_WorkspaceWindowBase):
    """Home Page window manager"""

    @property
    def title(self) -> str:
        return _WindowNames.HOME_PAGE

    @property
    def flags(self) -> int:
        return (
            ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_COLLAPSE
            | ui.WINDOW_FLAGS_NO_TITLE_BAR
            | ui.WINDOW_FLAGS_NO_CLOSE
        )

    def menu_path(self) -> str:
        return None

    def _create_window_ui(self):
        return _HomePageWidget(self._usd_context_name)

    def _update_ui(self):
        super()._update_ui()
        self._content.refresh()

        # TODO: There is a bug where windows won't spawn docked on first call.
        asyncio.ensure_future(self._refresh_docking())

    def _on_visibility_changed(self, visible: bool):
        super()._on_visibility_changed(visible)
        self._content.on_visibility_change(visible)

    async def _refresh_docking(self):
        if not self._window.docked:
            await omni.kit.app.get_app().next_update_async()
            dock_space = ui.Workspace.get_window("DockSpace")
            self._window.dock_in(dock_space, ui.DockPosition.SAME)
