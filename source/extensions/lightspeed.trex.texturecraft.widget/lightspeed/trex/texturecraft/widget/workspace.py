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
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex import sidebar
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase as _WorkspaceWindowBase
from omni import ui
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config
from omni.kit.quicklayout import QuickLayout as _QuickLayout

from .setup_ui import SetupUI as _TextureCraftUI


class TextureCraftWindow(_WorkspaceWindowBase):
    """TextureCraft window manager"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__register_sidebar_items()

    @property
    def title(self) -> str:
        return _WindowNames.TEXTURECRAFT

    def menu_path(self) -> str | None:
        return f"Modding/{self.title}"

    @property
    def flags(self) -> int:
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_COLLAPSE | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def _create_window_ui(self):
        return _TextureCraftUI()

    def _update_ui(self):
        super()._update_ui()
        self._window.dock_tab_bar_visible = False
        self._window.dock_tab_bar_enabled = False

        # TODO: There is a bug where windows won't spawn docked on first call.
        asyncio.ensure_future(self._refresh_docking())

    async def _refresh_docking(self):
        await omni.kit.app.get_app().next_update_async()
        dock_space = ui.Workspace.get_window("DockSpace")
        self._window.dock_in(dock_space, ui.DockPosition.SAME)

    def __register_sidebar_items(self):
        self.__sub_sidebar_items = sidebar.register_items(  # noqa PLW0238
            [
                sidebar.ItemDescriptor(
                    name="AITools",
                    tooltip="AI Tools",
                    group=sidebar.Groups.LAYOUTS,
                    mouse_released_fn=self.__open_layout,
                    sort_index=11,
                )
            ]
        )

    def __open_layout(self, x, y, b, m):
        if b != 0:
            return
        _QuickLayout.load_file(_get_quicklayout_config(_LayoutFiles.TEXTURECRAFT))
