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
import math

import carb
import omni.appwindow
import omni.kit
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase as _WorkspaceWindowBase
from omni import ui

from .setup_ui import SetupUI as _SideBarSetupUI


class SideBarWindow(_WorkspaceWindowBase):
    """Side Bar window manager"""

    __SIDEBAR_WIDTH = 56

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

    def _create_window_ui(self):
        return _SideBarSetupUI(self._window.frame)

    def _update_ui(self):
        super()._update_ui()

        self._window.padding_x = 0
        self._window.padding_y = 0
        self._window.dock_tab_bar_visible = False
        self._window.dock_tab_bar_enabled = False
        asyncio.ensure_future(self._dock_to_the_left())

    def _on_window_resized(self, value: float):
        asyncio.ensure_future(self._size_changed(value))

    async def _size_changed(self, new_size: float = 0):
        """Rubberbands the SideBar window width back to 56 pixels and updates dock state"""
        dockspace_window = ui.Workspace.get_window("DockSpace")
        padding_size = 5.0
        is_same_height = math.isclose(dockspace_window.height, self._window.height, abs_tol=padding_size)
        is_docked_on_the_left = self._window.position_x == 0 and self._window.position_y > 0
        if not is_same_height or not is_docked_on_the_left:
            await self._dock_to_the_left()

        mouse = omni.appwindow.get_default_app_window().get_mouse()
        input_interface = carb.input.acquire_input_interface()
        mouse_value = input_interface.get_mouse_value(mouse, carb.input.MouseInput.LEFT_BUTTON)
        if mouse_value > 0:
            # Hacky workaround since Kit can't listen to docking resize events or mouse state events at all here.
            await omni.kit.app.get_app().next_update_async()
            asyncio.ensure_future(self._size_changed(new_size))

        elif not math.isclose(new_size, self.__SIDEBAR_WIDTH, abs_tol=0.1):
            await self._dock_to_the_left()
            await omni.kit.app.get_app().next_update_async()
            ui.Workspace.set_dock_id_width(self._window.dock_id, self.__SIDEBAR_WIDTH)

    async def _dock_to_the_left(self, docked: bool = False):
        dock_space = ui.Workspace.get_window("DockSpace")
        self._window.dock_in(dock_space, ui.DockPosition.LEFT)
        self._window.dock_tab_bar_enabled = False
        self._window.dock_tab_bar_visible = False
