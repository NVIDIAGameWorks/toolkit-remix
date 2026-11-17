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
import omni.kit.app
import omni.kit.usd.layers as _layers
import omni.usd
from carb.eventdispatcher import get_eventdispatcher
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

_CONTEXT = "/exts/lightspeed.event.load_edit_target/context"


class EventLoadEditTargetCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_context_name": None,
            "_context": None,
            "_stage_event_sub": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        context_name = carb.settings.get_settings().get(_CONTEXT) or ""
        self._context = omni.usd.get_context(context_name)

    @property
    def name(self) -> str:
        """Name of the event"""
        return "LoadEditTarget"

    def _install(self):
        """Function that will create the behavior"""
        self._uninstall()

        self._stage_event_sub = get_eventdispatcher().observe_event(
            event_name=self._context.stage_event_name(omni.usd.StageEventType.OPENED),
            on_event=lambda _: asyncio.ensure_future(self.__load_edit_target_deferred()),
            observer_name="lightspeed.event.load_edit_target:EventLoadEditTargetCore.__load_edit_target_deferred",
        )

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._stage_event_sub = None

    async def __load_edit_target_deferred(self):
        # If we don't wait 1 frame the edit target gets overridden
        await omni.kit.app.get_app().next_update_async()
        _layers.LayerUtils.restore_authoring_layer_from_custom_data(self._context.get_stage())

    def destroy(self):
        _reset_default_attrs(self)
