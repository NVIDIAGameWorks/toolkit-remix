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

import lightspeed.trex.sidebar as sidebar
import omni.kit.app
import omni.usd
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.utils.widget.workspace import (
    WorkspaceWindowBase as _WorkspaceWindowBase,
)
from lightspeed.trex.utils.widget.quicklayout import load_layout
from omni import ui
from omni.flux.utils.widget.resources import (
    get_quicklayout_config as _get_quicklayout_config,
)

from .setup_ui import PackagingPane as _PackagingPane


class PackagingWindow(_WorkspaceWindowBase):
    """Mod Packaging window manager"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__sub_sidebar_items = None  # noqa PLW0238
        self.__sub_stage_event = None  # noqa PLW0238
        self.__register_sidebar_items()
        self.__subscribe_stage_events()

    @property
    def title(self) -> str:
        return _WindowNames.MOD_PACKAGING

    def menu_path(self) -> str | None:
        return f"Packaging/{self.title}"

    @property
    def flags(self) -> int:
        return ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_COLLAPSE

    def _create_window_ui(self):
        return _PackagingPane(self._usd_context_name)

    def __register_sidebar_items(self):
        self.__sub_sidebar_items = sidebar.register_items(  # noqa PLW0238
            [
                sidebar.ItemDescriptor(
                    name="PackageMod",
                    tooltip="Package Mod for Release",
                    disabled_tooltip="Package Mod for Release (Only available if there are projects open).",
                    group=sidebar.Groups.LAYOUTS,
                    mouse_released_fn=self.__open_layout,
                    sort_index=20,
                    enabled=False,
                )
            ]
        )
        self.__update_packaging_button_state()

    def __subscribe_stage_events(self):
        context = omni.usd.get_context(self._usd_context_name)
        self.__sub_stage_event = context.get_stage_event_stream().create_subscription_to_pop(  # noqa: PLW0238
            self.__on_stage_event, name="ModPackagingStageEvent"
        )

    def __open_layout(self, x, y, b, m):
        if b != 0:
            return
        load_layout(_get_quicklayout_config(_LayoutFiles.PACKAGING))

    def __on_stage_event(self, event):
        if event.type in [
            int(omni.usd.StageEventType.OPENED),
            int(omni.usd.StageEventType.CLOSING),
        ]:
            asyncio.ensure_future(self.__update_packaging_button_state_deferred())

    async def __update_packaging_button_state_deferred(self):
        await omni.kit.app.get_app().next_update_async()
        self.__update_packaging_button_state()

    def __update_packaging_button_state(self):
        if not self.__sub_sidebar_items:
            return
        context = omni.usd.get_context(self._usd_context_name)
        stage = context.get_stage()
        if not stage:
            self.__sub_sidebar_items.set_enabled(False)
            return
        root_layer = stage.GetRootLayer()
        has_project = root_layer and not bool(root_layer.anonymous)
        self.__sub_sidebar_items.set_enabled(bool(has_project))
