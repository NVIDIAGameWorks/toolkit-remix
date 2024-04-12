"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
__all__ = ["ViewportStatsLayer"]

import time
from typing import Optional, Sequence

import carb
from omni import ui

from ..interface.i_layer_item import LayerItem as _LayerItem
from .items import (
    ViewportDeviceStat,
    ViewportFPS,
    ViewportHostStat,
    ViewportMessage,
    ViewportProgress,
    ViewportResolution,
    ViewportSpeed,
    ViewportStatsGroup,
)
from .settings import *  # noqa
from .utils import resolve_hud_visibility

try:
    from omni.hydra.engine.stats import get_device_info
except ImportError:
    get_device_info = None


class ViewportStatsLayer(_LayerItem):
    def __init__(self, desc: dict):
        settings = carb.settings.get_settings()
        settings.set_default(LOW_MEMORY_SETTING_PATH, 0.2)
        settings.set_default(MEMORY_CHECK_FREQUENCY, 1.0)

        self.__viewport_api = desc.get("viewport_api")
        self.__frame_changed_sub = None
        self.__disable_ui_sub: Optional[carb.SubscriptionId] = None
        self.__setting_key, visible = resolve_hud_visibility(self.__viewport_api, None, settings)

        self.__last_time = time.time()
        self.__frequencies = {}
        for key in [MEMORY_CHECK_FREQUENCY]:
            value = settings.get(key)
            self.__frequencies[key] = [value, value]

        self.__groups: Sequence[ViewportStatsGroup] = None
        self.__root: ui.Frame = ui.Frame(horizontal_clipping=True, content_clipping=1, opaque_for_mouse_events=True)
        self.__root.visible = visible
        self.__build_stats_hud(self.__viewport_api)

        self.__disable_ui_sub = settings.subscribe_to_node_change_events(
            self.__setting_key, self.__stats_visiblity_changed
        )
        self.__stats_visiblity_changed(None, carb.settings.ChangeEventType.CHANGED)

    def __destroy_all_stats(self, value=None):
        if self.__groups:
            for group in self.__groups:
                group.destroy()
        self.__groups = value

    def __build_stats_hud(self, viewport_api):
        if self.__root:
            self.__root.clear()
        self.__destroy_all_stats([])

        right_stat_factories = [ViewportFPS, ViewportHostStat, ViewportProgress, ViewportResolution]

        # Optional omni.hydra.engine.stats dependency
        if get_device_info:
            right_stat_factories.insert(1, ViewportDeviceStat)

        # XXX: Need menu-bar height
        hud_top = 20 if hasattr(ui.constant, "viewport_menubar_height") else 0
        with ui.VStack():
            ui.Spacer(name="Spacer", style_type_name_override="ViewportStats")
            with ui.HStack(height=hud_top):
                self.__groups.append(
                    ViewportStatsGroup([ViewportSpeed], "Viewport Speed", ui.Alignment.LEFT, self.__viewport_api)
                )
                self.__groups.append(
                    ViewportStatsGroup([ViewportMessage], "Viewport Message", ui.Alignment.LEFT, self.__viewport_api)
                )
        with ui.VStack():
            ui.Spacer(name="Spacer", style_type_name_override="ViewportStats")
            with ui.HStack(height=hud_top):
                ui.Spacer(name="LeftRightSpacer", style_type_name_override="ViewportStats")
                self.__groups.append(
                    ViewportStatsGroup(right_stat_factories, "Viewport HUD", ui.Alignment.RIGHT, self.__viewport_api)
                )

    def __stats_visiblity_changed(self, item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType):
        if event_type == carb.settings.ChangeEventType.CHANGED:
            self.visible = bool(carb.settings.get_settings().get(self.__setting_key))

    def __set_stats_enabled(self, enabled: bool):
        if enabled:
            viewport_api = self.__viewport_api
            if self.__frame_changed_sub is None:
                self.__frame_changed_sub = viewport_api.subscribe_to_frame_change(self.__update_stats)

            self.__update_stats(viewport_api)
        else:
            if self.__frame_changed_sub:
                self.__frame_changed_sub.destroy()
                self.__frame_changed_sub = None
        self.__root.visible = enabled

    def __make_update_info(self, viewport_api):
        now = time.time()
        elapsed_time, self.__last_time = now - self.__last_time, now

        settings = carb.settings.get_settings()
        update_info = {
            "elapsed_time": elapsed_time,
            "low_mem_fraction": settings.get(LOW_MEMORY_SETTING_PATH),
            "viewport_api": viewport_api,
            "alpha": 1,
        }

        for key, value in self.__frequencies.items():
            value[0] += elapsed_time
            value[1] = settings.get(key)
            if value[0] >= value[1]:
                value[0] = 0
                update_info[key] = False
            else:
                update_info[key] = True

        return update_info

    def __update_stats(self, viewport_api):
        if self.__groups:
            update_info = self.__make_update_info(viewport_api)
            for group in self.__groups:
                group.update_stats(update_info)

    def destroy(self):
        if self.__disable_ui_sub is not None:
            carb.settings.get_settings().unsubscribe_to_change_events(self.__disable_ui_sub)
            self.__disable_ui_sub = None
        self.__set_stats_enabled(False)
        self.__destroy_all_stats()
        if self.__root:
            self.__root.clear()
            self.__root = None

    @property
    def layers(self):
        yield from self.__groups

    @property
    def visible(self):
        return self.__root.visible

    @visible.setter
    def visible(self, value):
        self.__set_stats_enabled(value)
        self.__root.visible = value

    @property
    def categories(self):
        return ("stats",)

    @property
    def name(self):
        return "All Stats"
