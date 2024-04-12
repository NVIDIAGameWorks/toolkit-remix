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
import omni.kit.usd.layers as _layers
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

_CONTEXT = "/exts/lightspeed.event.save_root_mod/context"


class EventSaveRootModCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_context": None,
            "_layer_event_sub": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        context_name = carb.settings.get_settings().get(_CONTEXT) or ""
        self._context = omni.usd.get_context(context_name)
        self.__layer_manager = LayerManagerCore(context_name)

    @property
    def name(self) -> str:
        """Name of the event"""
        return "SaveRootMod"

    def _install(self):
        """Function that will create the behavior"""
        self._uninstall()
        layers = _layers.get_layers()
        self._layer_event_sub = layers.get_event_stream().create_subscription_to_pop(
            self.__on_layer_event, name="LayerEvent"
        )

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._layer_event_sub = None

    def __on_layer_event(self, event):
        payload = _layers.get_layer_event_payload(event)

        if payload.event_type != _layers.LayerEventType.DIRTY_STATE_CHANGED:
            return

        replacement_layer = self.__layer_manager.get_layer(LayerType.replacement)
        # If there is no replacement layer there's nothing to save
        if not replacement_layer:
            carb.log_verbose("EventSaveRootModCore: Mod layer doesn't exist!")
            return

        subidentifiers = payload.identifiers_or_spec_paths
        dirty_subidentifiers = _layers.get_layers_state().get_dirty_layer_identifiers()

        for subidentifier in subidentifiers:
            # A sublayer other than the root mod was saved
            if subidentifier != replacement_layer.identifier and subidentifier not in dirty_subidentifiers:
                # Force save the root replacement layer
                replacement_layer.Save(True)
                break

    def destroy(self):
        _reset_default_attrs(self)
