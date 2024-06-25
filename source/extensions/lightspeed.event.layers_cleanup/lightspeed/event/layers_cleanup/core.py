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

from typing import List

import carb
import omni.client
import omni.kit.app
import omni.kit.notification_manager as _nm
import omni.kit.usd.layers as _layers
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf

_CONTEXT = "/exts/lightspeed.event.layers_cleanup/context"


class EventLayersCleanupCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_context_name": None,
            "_context": None,
            "_notification_manager": None,
            "_stage_event_sub": None,
            "_layer_event_sub": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        settings = carb.settings.get_settings()
        self._context_name = settings.get(_CONTEXT) or ""
        self._context = omni.usd.get_context(self._context_name)

        self._notification_manager = _nm.manager.NotificationManager()
        self._notification_manager.on_startup()

        self.__current_notification = None

    @property
    def name(self) -> str:
        """Name of the event"""
        return "LayersCleanup"

    def _install(self):
        """Function that will create the behavior"""
        self._uninstall()

        self._stage_event_sub = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_stage_event, name="StageEventListener"
        )

        layers = _layers.get_layers()
        self._layer_event_sub = layers.get_event_stream().create_subscription_to_pop(
            self.__on_layer_event, name="LayerEventListener"
        )

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._stage_event_sub = None
        self._layer_event_sub = None

    def __on_stage_event(self, event):
        if event.type in [int(omni.usd.StageEventType.OPENED)]:
            self.__cleaup_layers()

    def __on_layer_event(self, event):
        payload = _layers.get_layer_event_payload(event)
        if payload.event_type == _layers.LayerEventType.SUBLAYERS_CHANGED:
            self.__cleaup_layers()

    def __cleaup_layers(self):
        root_layer = self._context.get_stage().GetRootLayer()
        sublayer_paths = root_layer.subLayerPaths.copy()

        invalid_paths = []
        for sublayer_path in sublayer_paths:
            # Make sure the sublayer path is pointing to a valid layer file
            sublayer = Sdf.Layer.FindOrOpenRelativeToLayer(root_layer, sublayer_path)
            if not sublayer:
                invalid_paths.append(sublayer_path)

        for invalid_path in invalid_paths:
            sublayer_paths.remove(invalid_path)

        root_layer.subLayerPaths = sublayer_paths

        self._post_notification(invalid_paths)

    def _post_notification(self, invalid_paths: List[str]):
        if not invalid_paths:
            return

        if self.__current_notification:
            self._notification_manager.remove_notification(self.__current_notification)
            self.__current_notification.dismiss()

        message_details = "\n".join([f"- {p}" for p in invalid_paths])
        if len(invalid_paths) > 1:
            message = f"The following sublayer paths are invalid and were cleaned up:\n{message_details}"
        else:
            message = f"The following sublayer path is invalid and was cleaned up:\n{message_details}"

        notification = _nm.notification_info.NotificationInfo(
            message, hide_after_timeout=False, status=_nm.NotificationStatus.WARNING
        )
        self.__current_notification = self._notification_manager.post_notification(notification)
        carb.log_warn(message)

    def destroy(self):
        _reset_default_attrs(self)
