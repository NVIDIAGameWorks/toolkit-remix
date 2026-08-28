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

import lightspeed.trex.sidebar as _sidebar
import omni.kit.app
import omni.usd
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.utils.widget.quicklayout import load_layout
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase as _WorkspaceWindowBase
from omni import ui
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config

from .setup_ui import SetupUI as _IngestCraftUI

_STAGECRAFT_CONTROL_EXT = "lightspeed.trex.control.stagecraft"


class IngestCraftWindow(_WorkspaceWindowBase):
    """Manage the IngestCraft workspace window."""

    def __init__(self, *args, **kwargs):
        """Initialize IngestCraft navigation and window state."""
        super().__init__(*args, **kwargs)
        self._refresh_docking_task = None
        self._sidebar_subscription = None
        self.__register_sidebar_item()

    @property
    def title(self) -> str:
        return _WindowNames.INGESTCRAFT

    def menu_path(self) -> str | None:
        return f"Modding/{self.title}"

    @property
    def flags(self) -> int:
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_COLLAPSE | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def _create_window_ui(self):
        return _IngestCraftUI()

    def _update_ui(self):
        super()._update_ui()
        self._window.dock_tab_bar_visible = False
        self._window.dock_tab_bar_enabled = False

        # TODO: There is a bug where windows won't spawn docked on first call.
        if self._refresh_docking_task:
            self._refresh_docking_task.cancel()
        self._refresh_docking_task = asyncio.ensure_future(self._refresh_docking())

    @omni.usd.handle_exception
    async def _refresh_docking(self):
        """Dock IngestCraft with the workspace after the window updates."""
        task = asyncio.current_task()
        try:
            await omni.kit.app.get_app().next_update_async()
            dock_space = ui.Workspace.get_window("DockSpace")
            self._window.dock_in(dock_space, ui.DockPosition.SAME)
        finally:
            if self._refresh_docking_task is task:
                self._refresh_docking_task = None

    def cleanup(self):
        """Release standalone navigation and cancel deferred docking."""
        if self._refresh_docking_task:
            self._refresh_docking_task.cancel()
        self._refresh_docking_task = None
        self._sidebar_subscription = None
        super().cleanup()

    def __register_sidebar_item(self):
        manager = omni.kit.app.get_app().get_extension_manager()
        if manager.is_extension_enabled(_STAGECRAFT_CONTROL_EXT):
            return
        self._sidebar_subscription = _sidebar.register_items(
            [
                _sidebar.ItemDescriptor(
                    name="Ingestion",
                    tooltip="Asset Import/Ingestion",
                    group=_sidebar.Groups.LAYOUTS,
                    mouse_released_fn=self.__open_layout,
                    sort_index=10,
                )
            ]
        )

    def __open_layout(self, x, y, button, modifier):
        if button != 0:
            return
        load_layout(_get_quicklayout_config(_LayoutFiles.INGESTCRAFT))
