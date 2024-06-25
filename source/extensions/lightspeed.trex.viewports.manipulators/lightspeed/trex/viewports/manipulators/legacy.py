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

from typing import Any, Dict

import carb
import omni.usd
from pxr import UsdGeom

from .interface.i_manipulator import IManipulator


class LegacyGridScene(IManipulator):
    def __init__(self, viewport_api):
        carb.settings.get_settings().set_default("/app/viewport/grid/enabled", True)
        self.__usd_context_name = viewport_api.usd_context_name
        self.__persp_grid = "XZ"
        self.__last_grid = None
        self.__on_stage_opened(self.stage)
        self.__stage_sub = self.usd_context.get_stage_event_stream().create_subscription_to_pop(  # noqa PLW0238
            self.__on_usd_context_event, name="LegacyGridScene StageUp watcher"
        )

        self.__vc_change = None
        if viewport_api:
            self.__vc_change = viewport_api.subscribe_to_view_change(self.__view_changed)
        super().__init__(viewport_api)

    def _create_manipulator(self):
        pass

    def _model_changed(self, model, item):
        pass

    @property
    def usd_context(self):
        return omni.usd.get_context(self.__usd_context_name)

    @property
    def stage(self):
        return self.usd_context.get_stage()

    def __on_usd_context_event(self, event: carb.events.IEvent):
        if event.type == int(omni.usd.StageEventType.OPENED):
            self.__on_stage_opened(self.stage)

    def __set_grid(self, grid: str):
        if self.__last_grid != grid:
            self.__last_grid = grid
            carb.settings.get_settings().set("/app/viewport/grid/plane", grid)

    def __on_stage_opened(self, stage):
        up = UsdGeom.GetStageUpAxis(stage) if stage else None
        if up == UsdGeom.Tokens.x:
            self.__persp_grid = "YZ"
        elif up == UsdGeom.Tokens.z:
            self.__persp_grid = "XY"
        else:
            self.__persp_grid = "XZ"

    def __view_changed(self, viewport_api):
        is_ortho = viewport_api.projection[3][3] == 1
        if is_ortho:
            ortho_dir = viewport_api.transform.TransformDir((0, 0, 1))
            ortho_dir = [abs(v) for v in ortho_dir]
            if ortho_dir[1] > ortho_dir[0] and ortho_dir[1] > ortho_dir[2]:
                self.__set_grid("XZ")
            elif ortho_dir[2] > ortho_dir[0] and ortho_dir[2] > ortho_dir[1]:
                self.__set_grid("XY")
            else:
                self.__set_grid("YZ")
        else:
            self.__on_stage_opened(viewport_api.stage)
            self.__set_grid(self.__persp_grid)

    @property
    def name(self):
        return "Grid (legacy)"

    @property
    def categories(self):
        return ["reference"]

    @property
    def visible(self):
        return carb.settings.get_settings().get("/app/viewport/grid/enabled")

    @visible.setter
    def visible(self, value):
        carb.settings.get_settings().set("/app/viewport/grid/enabled", bool(value))

    def destroy(self):
        self.__stage_sub = None  # noqa PLW0238
        if self.__vc_change:
            self.__vc_change.destroy()
            self.__vc_change = None
        super().destroy()


class LegacyLightScene(IManipulator):
    def __init__(self, viewport_api):
        carb.settings.get_settings().set_default("/app/viewport/show/lights", True)
        super().__init__(viewport_api)

    def _create_manipulator(self):
        pass

    def _model_changed(self, model, item):
        pass

    @property
    def name(self):
        return "Lights (legacy)"

    @property
    def categories(self):
        return ["scene"]

    @property
    def visible(self):
        return carb.settings.get_settings().get("/app/viewport/show/lights")

    @visible.setter
    def visible(self, value):
        carb.settings.get_settings().set("/app/viewport/show/lights", bool(value))


class LegacyAudioScene(IManipulator):
    def __init__(self, viewport_api):
        carb.settings.get_settings().set_default("/app/viewport/show/audio", True)
        super().__init__(viewport_api)

    def _create_manipulator(self):
        pass

    def _model_changed(self, model, item):
        pass

    @property
    def name(self):
        return "Audio (legacy)"

    @property
    def categories(self):
        return ["scene"]

    @property
    def visible(self):
        return carb.settings.get_settings().get("/app/viewport/show/audio")

    @visible.setter
    def visible(self, value):
        carb.settings.get_settings().set("/app/viewport/show/audio", bool(value))


def grid_default_factory(desc: Dict[str, Any]):
    manip = LegacyGridScene(desc.get("viewport_api"))
    return manip


def light_factory(desc: Dict[str, Any]):
    manip = LegacyLightScene(desc.get("viewport_api"))
    return manip


def audio_factory(desc: Dict[str, Any]):
    manip = LegacyAudioScene(desc.get("viewport_api"))
    return manip
