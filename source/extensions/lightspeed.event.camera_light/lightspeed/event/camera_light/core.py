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

import asyncio

import carb
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

_CONTEXT = "/exts/lightspeed.event.camera_light/context"
# The different fallback lighting modes.
# 'Never' will never create a fallback light
# 'NoLightsPresent' will create a fallback light only when no lights are provided
# 'Always' will always create a fallback light
_FALLBACK_MODES = {"Never": "0", "NoLightsPresent": "1", "Always": "2"}
# The different fallback types
_FALLBACK_TYPES = {"Distant": "0", "Sphere": "1"}


# Keep HdRemix imports lazy so the optional renderer dependency is only loaded when this event writes configvars.
def _hdremix_set_configvar(key: str, value: str) -> None:
    from lightspeed.hydra.remix.core import hdremix_set_configvar  # noqa: PLC0415

    hdremix_set_configvar(key, value)


async def _hdremix_set_configvar_async(key: str, value: str) -> None:
    from lightspeed.hydra.remix.core import hdremix_set_configvar_async  # noqa: PLC0415

    await hdremix_set_configvar_async(key, value)


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

    @omni.usd.handle_exception
    async def __set_configvars_async(self, configvars: list[tuple[str, str]], message: str):
        for key, value in configvars:
            await _hdremix_set_configvar_async(key, value)
        carb.log_info(message)

    def __set_configvars(self, configvars: list[tuple[str, str]], message: str):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            for key, value in configvars:
                _hdremix_set_configvar(key, value)
            carb.log_info(message)
            return

        asyncio.ensure_future(self.__set_configvars_async(configvars, message))

    def _set_camera_light(self):
        self.__set_configvars(
            [
                ("rtx.fallbackLightMode", _FALLBACK_MODES["Always"]),
                ("rtx.fallbackLightType", _FALLBACK_TYPES["Sphere"]),
                ("rtx.fallbackLightRadiance", "50, 50, 50"),
            ],
            "Camera light set...",
        )

    def _reset_camera_light(self):
        self.__set_configvars(
            [
                ("rtx.fallbackLightMode", _FALLBACK_MODES["Never"]),
                ("rtx.fallbackLightRadiance", "0, 0, 0"),
            ],
            "Camera light reset...",
        )

    def __on_camera_light_event(self, *args, **kwargs):
        render_settings = self._settings.get("/rtx/useViewLightingMode")
        if render_settings:
            self._set_camera_light()
        else:
            self._reset_camera_light()

    def destroy(self):
        _reset_default_attrs(self)
