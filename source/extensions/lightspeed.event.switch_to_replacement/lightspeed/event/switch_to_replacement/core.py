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
import omni.kit.notification_manager as nm
import omni.usd
from carb.eventdispatcher import Event, get_eventdispatcher
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.usd.layers import LayerEventType, get_layers, layer_event_name
from pxr import Sdf

from .edit_context import should_disable_switch as _should_disable_switch

_CONTEXT = "/exts/lightspeed.event.switch_to_replacement/context"


class SwitchToReplacementCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_context": None,
            "_layer_manager": None,
            "_notification_manager": None,
            "_current_notification": None,
            "_stage_event_subscription": None,
            "_layer_event_subscription": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        context_name = carb.settings.get_settings().get(_CONTEXT) or ""
        self._context = omni.usd.get_context(context_name)
        self._layer_manager = LayerManagerCore(context_name)

        self._notification_manager = nm.manager.NotificationManager()
        self._notification_manager.on_startup()
        self._current_notification = None

    @property
    def name(self) -> str:
        """Name of the event"""
        return "SwitchToReplacement"

    def _install(self):
        """Function that will create the behavior"""
        layers = get_layers()
        self._stage_event_subscription = [
            get_eventdispatcher().observe_event(
                event_name=self._context.stage_event_name(event_type),
                on_event=lambda _: self.__check_current_edit_layer(),
                observer_name="lightspeed.event.switch_to_replacement:SwitchToReplacementCore.__check_current_edit_layer",
            )
            for event_type in (omni.usd.StageEventType.SAVING, omni.usd.StageEventType.OPENED)
        ]
        self._layer_event_subscription = [
            get_eventdispatcher().observe_event(
                event_name=layer_event_name(event_type),
                on_event=self.__on_layer_event,
                filter=layers.get_event_key(),
                observer_name="lightspeed.event.switch_to_replacement:SwitchToReplacementCore.__on_layer_event",
            )
            for event_type in (
                LayerEventType.EDIT_MODE_CHANGED,
                LayerEventType.EDIT_TARGET_CHANGED,
                LayerEventType.LOCK_STATE_CHANGED,
                LayerEventType.MUTENESS_SCOPE_CHANGED,
                LayerEventType.MUTENESS_STATE_CHANGED,
                LayerEventType.SUBLAYERS_CHANGED,
            )
        ]

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._stage_event_subscription = None
        self._layer_event_subscription = None

    def __on_layer_event(self, _event: Event):
        if _should_disable_switch():
            return
        self.__check_current_edit_layer()

    def __show_message(self, message):
        if self._current_notification:
            self._notification_manager.remove_notification(self._current_notification)
            self._current_notification.dismiss()
        ok_button = nm.NotificationButtonInfo("OK")
        ni = nm.notification_info.NotificationInfo(message, False, 3, nm.NotificationStatus.WARNING, [ok_button])
        self._current_notification = self._notification_manager.post_notification(ni)
        carb.log_warn(message)

    def __check_current_edit_layer(self):
        def get_sublayers(layer):
            sublayers = []
            submods = []
            for sublayer_path in layer.subLayerPaths:
                sublayer = Sdf.Layer.FindOrOpenRelativeToLayer(layer, sublayer_path)
                if not sublayer:
                    continue
                if self._layer_manager.get_custom_data_layer_type(sublayer) == LayerType.replacement.value:
                    submods.append(sublayer.identifier)
                else:
                    sublayers.append(sublayer.identifier)

                child_sublayers, child_submods = get_sublayers(sublayer)
                sublayers.extend(child_sublayers)
                submods.extend(child_submods)
            return sublayers, submods

        layer_replacement = self._layer_manager.get_layer_of_type(LayerType.replacement)
        # we only save stage that have a replacement layer
        if not layer_replacement:
            # this can be ok when the user works on asset(s)
            # checking is there is a capture layer. If there is one, we need a replacement layer. If not, we don't care
            layer_capture = self._layer_manager.get_layer_of_type(LayerType.capture)
            if layer_capture:
                self.__show_message("Can't find the mod layer in the current stage")
                return
            return

        sublayers, submods = get_sublayers(layer_replacement)

        valid_layer_identifiers = [layer_replacement.identifier]
        valid_layer_identifiers.extend(sublayers)

        stage = self._context.get_stage()
        stage_edit_target = stage.GetEditTarget().GetLayer().identifier

        # if the current edit target is not part of the valid layers, switch it to the replacement layer
        if stage_edit_target not in valid_layer_identifiers:
            if stage_edit_target in submods:
                self.__show_message("Cannot set a sub-mod as the edit target layer. Switching to the mod layer.")
            else:
                carb.log_warn("The current edit target layer is not valid. Switching to the mod layer.")
            stage.SetEditTarget(layer_replacement)

    def destroy(self):
        self._current_notification = None
        self._notification_manager.on_shutdown()

        _reset_default_attrs(self)
