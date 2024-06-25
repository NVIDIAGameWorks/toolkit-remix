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

import carb.settings
import omni.kit.usd.layers as _layers
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator

_CONTEXT = "/exts/lightspeed.event.save_global_muteness/context"


class EventLayersSaveCustomDataCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {"_subscription_layer": None, "_subscription_stage": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        settings = carb.settings.get_settings()
        self._context_name = settings.get(_CONTEXT) or ""
        self._context = omni.usd.get_context(self._context_name)

    @property
    def name(self) -> str:
        """Name of the event"""
        return "LayerGlobalMuteness"

    def _install(self):
        """Function that will create the behavior"""
        self._install_layer_listener()

    def _install_layer_listener(self):
        self._uninstall_layer_listener()
        self._subscription_stage = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_load_event, name="Recent file loaded"
        )
        layers = _layers.get_layers()
        self._subscription_layer = layers.get_event_stream().create_subscription_to_pop(
            self.__on_layer_event, name="LayerChange"
        )

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._uninstall_layer_listener()

    def _uninstall_layer_listener(self):
        self._subscription_layer = None
        self._subscription_stage = None

    def __on_load_event(self, event):
        if event.type in [int(omni.usd.StageEventType.OPENED)]:
            layers = _layers.get_layers()
            layers_state = layers.get_layers_state()
            # by default, we want to save the muteness into the stage
            layers_state.set_muteness_scope(True)

    @_ignore_function_decorator(attrs=["_ignore_on_event"])
    def __on_layer_event(self, event):
        payload = _layers.get_layer_event_payload(event)
        if not payload:
            return
        if payload.event_type == _layers.LayerEventType.MUTENESS_STATE_CHANGED:
            # because we are in a global muteness scope, we need to save the root layer to save the state of the
            # muteness. Kit doesn't detect by default when we changed the scope + muted a layer. So we set the stage
            # as pending edit.
            self._context.set_pending_edit(True)

    def destroy(self):
        self._uninstall()
        _reset_default_attrs(self)
