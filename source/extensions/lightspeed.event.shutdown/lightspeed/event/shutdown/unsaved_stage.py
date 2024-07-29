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

import abc
from typing import Callable, Protocol

import carb
import omni.kit.app
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.trex.control.stagecraft import get_instance as _get_control_stagecraft
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.window.file import get_instance as get_window_ext_instance

TREX_IGNORE_UNSAVED_STAGE_ON_EXIT = "/app/file/trexIgnoreUnsavedOnExit"


class InterrupterClass(Protocol):

    @abc.abstractmethod
    def should_interrupt_shutdown(self) -> bool:
        """Check whether to interrupt shutdown"""

    @abc.abstractmethod
    def interrupt_shutdown(self, shutdown_callback: Callable[[], None]) -> None:
        """
        Give the interrupter the ability to run something and decide whether to call `shutdown_callback` to
        continue the shutdown.
        """


class EventUnsavedStageOnShutdown(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {"_shutdown_event_sub": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._app = omni.kit.app.get_app()
        self._ignore_unsaved_stage = carb.settings.get_settings().get(TREX_IGNORE_UNSAVED_STAGE_ON_EXIT) or False
        self.__skip_interrupters = False

        self._interrupters: list[InterrupterClass] = []
        self._currently_triggered_interrupters: list[InterrupterClass] = []

        # for now, we just register the instances here
        stagecraft_control = _get_control_stagecraft()
        self.register_interrupter(stagecraft_control)

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

    def register_interrupter(self, interrupter: InterrupterClass):
        """Register an interrupter that will be consulted before shutdown"""
        self._interrupters.append(interrupter)

    def __shutdown(self):
        # make sure we don't ask interrupters anymore
        self.__skip_interrupters = True
        self._app.post_quit()
        # likely won't get called, but reset in case post_quit does not shut things down.
        self.__skip_interrupters = False

    def __shutdown_callback(self, interrupter):
        """
        Receive callback from an interruptor.
        """
        self._currently_triggered_interrupters.remove(interrupter)
        if not self._currently_triggered_interrupters:
            self.__shutdown()

    # Note: This method adapted from omni.kit.window.file.FileWindowExtension().close()
    def __on_shutdown_event(self, event):
        if event.type != omni.kit.app.POST_QUIT_EVENT_TYPE:
            return

        if self._ignore_unsaved_stage:
            return

        if self.__skip_interrupters:
            return

        self._currently_triggered_interrupters = []
        for interrupter in self._interrupters:
            if interrupter.should_interrupt_shutdown():
                self._currently_triggered_interrupters.append(interrupter)

        if self._currently_triggered_interrupters:
            self._app.try_cancel_shutdown("Interrupting shutdown...")
            window_extension = get_window_ext_instance()  # type: omni.kit.window.file.FileWindowExtension
            window_extension.stop_timeline()

        for interrupter in self._currently_triggered_interrupters:
            interrupter.interrupt_shutdown(self.__shutdown_callback)

    def destroy(self):
        self._interrupters = []
        self._currently_triggered_interrupters = []
        _reset_default_attrs(self)
