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
import omni.kit.notification_manager as nm
import omni.kit.undo
import omni.kit.usd.layers as _layers
import omni.usd
from lightspeed.common.constants import REMIX_CAPTURE_FOLDER, REMIX_DEPENDENCIES_FOLDER, REMIX_FOLDER
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl
from omni.kit import commands

_CONTEXT = "/exts/lightspeed.event.validate_project/context"


class EventValidateProjectCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_context_name": None,
            "_context": None,
            "_stage_event_sub": None,
            "_layer_event_sub": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._context_name = carb.settings.get_settings().get(_CONTEXT) or ""
        self._context = omni.usd.get_context(self._context_name)

        self.__layer_manager = LayerManagerCore(self._context_name)

        self.__notification_manager = nm.manager.NotificationManager()
        self.__notification_manager.on_startup()

        self.__current_notification = None

    @property
    def name(self) -> str:
        """Name of the event"""
        return "ValidateProject"

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
        if event.type in [int(omni.usd.StageEventType.OPENED), int(omni.usd.StageEventType.SAVED)]:
            self.__validate_project()

    def __on_layer_event(self, event):
        payload = _layers.get_layer_event_payload(event)
        if payload.event_type in [
            _layers.LayerEventType.LOCK_STATE_CHANGED,
            _layers.LayerEventType.MUTENESS_SCOPE_CHANGED,
            _layers.LayerEventType.MUTENESS_STATE_CHANGED,
            _layers.LayerEventType.SUBLAYERS_CHANGED,
        ]:
            self.__validate_project()

    def __show_message(self, message):
        if self.__current_notification:
            self.__notification_manager.remove_notification(self.__current_notification)
            self.__current_notification.dismiss()

        ok_button = nm.NotificationButtonInfo("OK")
        ni = nm.notification_info.NotificationInfo(message, False, 3, nm.NotificationStatus.WARNING, [ok_button])

        self.__current_notification = self.__notification_manager.post_notification(ni)
        carb.log_warn(message)

    def __validate_project(self):
        project_layer = self.__layer_manager.get_layer(LayerType.workfile)
        if not project_layer:
            carb.log_warn("Could not validate project. No project layer was found.")
            return

        capture_layer = self.__layer_manager.get_layer(LayerType.capture)
        if not capture_layer:
            carb.log_warn("Could not validate project. No capture layer was found.")
            return

        mod_layer = self.__layer_manager.get_layer(LayerType.replacement)
        if not mod_layer:
            carb.log_warn("Could not validate project. No mod layer was found.")
            return

        # Mod layer should be the strongest layer
        mod_layer_position = _layers.LayerUtils.get_sublayer_position_in_parent(
            project_layer.identifier, mod_layer.identifier
        )
        if mod_layer_position != 0:
            self.__show_message("Re-arranging sublayers so the mod layer is the most powerful sublayer.")
            mod_layer_path = project_layer.subLayerPaths[mod_layer_position]
            del project_layer.subLayerPaths[mod_layer_position]
            project_layer.subLayerPaths.insert(0, mod_layer_path)

        # Capture layer should be the weakest layer
        capture_layer_position = _layers.LayerUtils.get_sublayer_position_in_parent(
            project_layer.identifier, capture_layer.identifier
        )
        if capture_layer_position != len(project_layer.subLayerPaths) - 1:
            self.__show_message("Re-arranging sublayers so the capture layer is the weakest sublayer.")
            capture_layer_path = project_layer.subLayerPaths[capture_layer_position]
            del project_layer.subLayerPaths[capture_layer_position]
            project_layer.subLayerPaths.append(capture_layer_path)

        # Capture should use the ./deps/captures path
        capture_sublayer_path = project_layer.subLayerPaths[-1]
        expected_relative_path = (
            f"./{REMIX_DEPENDENCIES_FOLDER}/{REMIX_CAPTURE_FOLDER}/{OmniUrl(capture_sublayer_path).name}"
        )
        if capture_sublayer_path != expected_relative_path:
            # If the capture sublayer path doesn't start with ./deps/captures, try to find it through that path
            capture_url = OmniUrl(OmniUrl(project_layer.realPath).parent_url) / expected_relative_path
            if capture_url.exists:
                project_layer.subLayerPaths[-1] = expected_relative_path
            else:
                self.__show_message(
                    f'The current capture layer does not exist in: "{expected_relative_path}".\n\n'
                    f'The captures should be located within the linked "{REMIX_FOLDER}" directory.\n\n'
                    f"Removing the capture layer from the project."
                )
                del project_layer.subLayerPaths[-1]

        # The project layer should not be muted or locked
        self.__update_layer_state(project_layer.identifier, False, False)

        # The mod layer should not be muted or locked
        self.__update_layer_state(mod_layer.identifier, False, False)

        # The capture layer should not be muted but should be locked
        self.__update_layer_state(capture_layer.identifier, True, False)

    def __update_layer_state(self, layer_identifier: str, should_be_locked: bool, should_be_muted: bool):
        state = _layers.get_layers(self._context).get_layers_state()

        with omni.kit.undo.group():
            if state.is_layer_locked(layer_identifier) != should_be_locked:
                commands.execute(
                    "LockLayer",
                    layer_identifier=layer_identifier,
                    locked=should_be_locked,
                    usd_context=self._context_name,
                )

            if (
                state.is_layer_locally_muted(layer_identifier)
                or state.is_layer_globally_muted(layer_identifier) != should_be_muted
            ):
                omni.kit.commands.execute(
                    "SetLayerMuteness",
                    layer_identifier=layer_identifier,
                    muted=should_be_muted,
                    usd_context=self._context_name,
                )

    def destroy(self):
        _reset_default_attrs(self)
