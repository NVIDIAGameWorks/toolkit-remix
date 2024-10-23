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

from typing import Callable

from lightspeed.event.shutdown_base import EventOnShutdownBase as _EventOnShutdownBase
from lightspeed.event.shutdown_base import InterrupterBase as _InterrupterBase
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.sentry_manager.core import get_instance as _get_sentry_manager


class SentryShutdownInterrupter(_InterrupterBase):
    def __init__(self, *args, **kwargs):
        self._callback = None

    def should_interrupt_shutdown(self):
        if self._callback:
            self._callback()
        return False

    def interrupt_shutdown(self, shutdown_callback: Callable[[], None]) -> None:
        """Don't need to interrupt shutdown, but it's abstract in the superclass"""
        pass

    def set_callback(self, callback):
        self._callback = callback


class EventSentryManagerOnShutdown(_EventOnShutdownBase):
    def __init__(self):
        super().__init__()
        self.interrupter = SentryShutdownInterrupter()
        self.register_interrupter(self.interrupter)
        # Need to call this here to start the app timer in Sentry
        self.interrupter.set_callback(self.shutdown_callback)
        _get_event_manager_instance().register_event(self)

    def shutdown_callback(self):
        _get_sentry_manager().app_closing()
        # Only need to fire once
        _get_event_manager_instance().unregister_event(self)

    @property
    def name(self) -> str:
        """Name of the event"""
        return "Sentry On Shutdown"
