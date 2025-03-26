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
import omni.client
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.layer_manager.core import LSS_LAYER_GAME_NAME, LayerManagerCore, LayerType
from lightspeed.trex.recent_projects.core import RecentProjectsCore
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

_CONTEXT = "/exts/lightspeed.event.save_recent/context"


class EventSaveRecentCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {"_context_name": None, "_context": None, "_subscription": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._context_name = carb.settings.get_settings().get(_CONTEXT) or ""
        self._context = omni.usd.get_context(self._context_name)

        self.__project_core = RecentProjectsCore()
        self.__layer_manager = LayerManagerCore(context_name=self._context_name)

    @property
    def name(self) -> str:
        """Name of the event"""
        return "SaveRecent"

    def _install(self):
        """Function that will create the behavior"""
        self._subscription = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_save_event, name="Recent file saved"
        )

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._subscription = None

    def __on_save_event(self, event):
        if event.type in [int(omni.usd.StageEventType.SAVED), int(omni.usd.StageEventType.OPENED)]:
            layer_capture = self.__layer_manager.get_layer(LayerType.capture)
            # we only save stage that have a capture layer
            if not layer_capture:
                carb.log_verbose("Can't find the capture layer in the current stage")
                return
            layer_replacement = self.__layer_manager.get_layer(LayerType.replacement)
            # we only save stage that have a replacement layer
            if not layer_replacement:
                carb.log_verbose("Can't find the replacement layer in the current stage")
                return
            stage = self._context.get_stage()
            if layer_replacement.anonymous or layer_capture.anonymous or (stage and stage.GetRootLayer().anonymous):
                carb.log_verbose("Anonymous layer(s) can't be in the recent list")
                return
            path = self._context.get_stage_url()
            self.__project_core.append_path_to_recent_file(
                omni.client.normalize_url(path),
                layer_replacement.customLayerData.get(LSS_LAYER_GAME_NAME),
                omni.client.normalize_url(layer_capture.realPath),
            )

    def destroy(self):
        _reset_default_attrs(self)
