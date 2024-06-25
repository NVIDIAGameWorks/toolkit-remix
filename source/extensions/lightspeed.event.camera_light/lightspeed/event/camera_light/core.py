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

import carb
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.hydra.remix.core import hdremix_set_configvar as _hdremix_set_configvar
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

_CONTEXT = "/exts/lightspeed.event.camera_light/context"
# The different fallback lighting modes.
# 'Never' will never create a fallback light
# 'NoLightsPresent' will create a fallback light only when no lights are provided
# 'Always' will always create a fallback light
_FALLBACK_MODES = {"Never": "0", "NoLightsPresent": "1", "Always": "2"}
# The different fallback types
_FALLBACK_TYPES = {"Distant": "0", "Sphere": "1"}


class EventCameraLightCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._settings = carb.settings.get_settings()

    @property
    def name(self) -> str:
        """Name of the event"""
        return "CameraLight"

    def _install(self):
        """Function that will create the behavior"""
        self._uninstall()

        self._settings.subscribe_to_node_change_events("/rtx/useViewLightingMode", self.__on_camera_light_event)

    def _uninstall(self):
        """Function that will remove the behavior"""
        self._settings.subscribe_to_node_change_events("/rtx/useViewLightingMode", None)

    def _set_camera_light(self):
        _hdremix_set_configvar("rtx.fallbackLightMode", _FALLBACK_MODES["Always"])
        _hdremix_set_configvar("rtx.fallbackLightType", _FALLBACK_TYPES["Sphere"])
        _hdremix_set_configvar("rtx.fallbackLightRadiance", "50, 50, 50")
        carb.log_info("Camera light set...")

    def _reset_camera_light(self):
        _hdremix_set_configvar("rtx.fallbackLightMode", _FALLBACK_MODES["Never"])
        _hdremix_set_configvar("rtx.fallbackLightRadiance", "0, 0, 0")
        carb.log_info("Camera light reset...")

    def __on_camera_light_event(self, *args, **kwargs):
        render_settings = self._settings.get("/rtx/useViewLightingMode")
        if render_settings:
            self._set_camera_light()
        else:
            self._reset_camera_light()

    def destroy(self):
        _reset_default_attrs(self)
