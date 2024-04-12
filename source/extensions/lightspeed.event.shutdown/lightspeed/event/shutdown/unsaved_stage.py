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
import omni.kit.app
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.trex.control.stagecraft import get_instance as _get_control_stagecraft
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

TREX_IGNORE_UNSAVED_STAGE_ON_EXIT = "/app/file/trexIgnoreUnsavedOnExit"


class EventUnsavedStageOnShutdown(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {"_shutdown_event_sub": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._app = omni.kit.app.get_app()
        self._ignore_unsaved_stage = carb.settings.get_settings().get(TREX_IGNORE_UNSAVED_STAGE_ON_EXIT) or False

    @property
    def name(self) -> str:
        """Name of the event"""
        return "Event Unsaved On Shutdown"

    def _install(self):
        """Function that will create the behavior"""
        self._uninstall()

        self._shutdown_event_sub = self._app.get_shutdown_event_stream().create_subscription_to_pop(
            self.__on_shutdown_event, name="lightspeed.event.shutdown hook", order=0
        )

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._shutdown_event_sub = None

    def __on_shutdown_event(self, event):
        if event.type != omni.kit.app.POST_QUIT_EVENT_TYPE:
            return

        if self._ignore_unsaved_stage:
            return

        stagecraft_control = _get_control_stagecraft()
        usd_context = stagecraft_control.context
        if usd_context.can_close_stage() and usd_context.has_pending_edit():
            self._app.try_cancel_shutdown("Interrupting shutdown - closing stage first")
            stagecraft_control.on_close_with_unsaved_project(lambda *args: self._app.post_quit())

    def destroy(self):
        _reset_default_attrs(self)
