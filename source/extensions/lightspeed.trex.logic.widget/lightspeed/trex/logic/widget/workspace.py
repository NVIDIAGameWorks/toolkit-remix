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

__all__ = ["RemixLogicGraphWorkspaceWindow"]


import asyncio

import lightspeed.trex.sidebar as sidebar
import omni.kit.app
import omni.usd
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.utils.widget.quicklayout import load_layout
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase as _WorkspaceWindowBase
from omni import ui
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config

from .graph_window import RemixLogicGraphWindow


class RemixLogicGraphWorkspaceWindow(_WorkspaceWindowBase):
    """Remix Logic Graph window manager"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__sub_sidebar_items = None
        self.__sub_stage_event = None
        self.__register_sidebar_items()
        self.__subscribe_stage_events()

    @property
    def title(self) -> str:
        return _WindowNames.REMIX_LOGIC_GRAPH

    def menu_path(self) -> str:
        return f"Editor/{self.title}"

    @property
    def flags(self) -> int:
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def _create_window(self) -> ui.Window:
        return RemixLogicGraphWindow(title=self.title, width=1000, height=800)

    # overrides for updating content, leave that to omni graph window
    def _update_ui(self):
        pass

    # overrides for updating content, leave that to omni graph window
    def _create_window_ui(self) -> ui.Widget:
        raise NotImplementedError("Should never be called.")

    def __register_sidebar_items(self):
        self.__sub_sidebar_items = sidebar.register_items(
            [
                sidebar.ItemDescriptor(
                    name="LogicGraph",
                    tooltip="Logic Graph",
                    disabled_tooltip="Logic Graph (Only available if there are projects open).",
                    group=sidebar.Groups.LAYOUTS,
                    mouse_released_fn=self.__open_layout,
                    sort_index=5,
                    enabled=False,
                )
            ]
        )
        self.__update_button_state()

    def __subscribe_stage_events(self):
        context = omni.usd.get_context(self._usd_context_name or "")
        self.__sub_stage_event = context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_stage_event, name="LogicGraphStageEvent"
        )

    def __on_stage_event(self, event):
        if event.type in [
            int(omni.usd.StageEventType.OPENED),
            int(omni.usd.StageEventType.CLOSING),
        ]:
            asyncio.ensure_future(self.__update_button_state_deferred())

    async def __update_button_state_deferred(self):
        await omni.kit.app.get_app().next_update_async()
        self.__update_button_state()

    def __update_button_state(self):
        if not self.__sub_sidebar_items:
            return
        context = omni.usd.get_context(self._usd_context_name or "")
        stage = context.get_stage()
        if not stage:
            self.__sub_sidebar_items.set_enabled(False)
            return
        root_layer = stage.GetRootLayer()
        has_project = root_layer and not bool(root_layer.anonymous)
        self.__sub_sidebar_items.set_enabled(bool(has_project))

    def __open_layout(self, x, y, b, m):
        if b != 0:
            return
        load_layout(_get_quicklayout_config(_LayoutFiles.LOGIC_GRAPH))
