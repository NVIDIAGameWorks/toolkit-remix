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

__all__ = ("AIToolsWorkspace",)

import asyncio

import lightspeed.trex.sidebar as sidebar
import omni.kit.app
import omni.usd
from lightspeed.common.constants import LayoutFiles, WindowNames
from lightspeed.trex.utils.widget.quicklayout import load_layout
from lightspeed.trex.utils.widget.workspace import WorkspaceWindowBase
from omni import ui
from omni.flux.utils.widget.resources import get_quicklayout_config

from .widget import AIToolsWidget


class AIToolsWorkspace(WorkspaceWindowBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__sub_sidebar_items = None
        self.__sub_stage_event = None

        self.__register_sidebar_items()
        self.__subscribe_stage_events()

    @property
    def title(self) -> str:
        return WindowNames.AI_TOOLS

    def menu_path(self) -> str | None:
        return f"AI Tools/{self.title}"

    @property
    def flags(self) -> int:
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE

    def _create_window_ui(self):
        return AIToolsWidget(context_name=self._usd_context_name or "")

    def __del__(self):
        self.cleanup()

    def cleanup(self):
        self.__sub_sidebar_items = None
        self.__sub_stage_event = None
        super().cleanup()

    def __register_sidebar_items(self):
        self.__sub_sidebar_items = sidebar.register_items(
            [
                sidebar.ItemDescriptor(
                    name="AITools",
                    tooltip="AI Tools (Experimental)",
                    disabled_tooltip="AI Tools (Experimental) is only available if a project is opened.",
                    group=sidebar.Groups.LAYOUTS,
                    mouse_released_fn=self.__open_layout,
                    sort_index=11,
                    enabled=False,
                )
            ]
        )
        self.__update_button_state()

    def __subscribe_stage_events(self):
        context = omni.usd.get_context(self._usd_context_name or "")
        self.__sub_stage_event = context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_stage_event, name="AIToolsStageEvent"
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
        load_layout(get_quicklayout_config(LayoutFiles.AI_TOOLS))
