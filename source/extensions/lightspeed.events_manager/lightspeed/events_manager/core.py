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

import typing
from typing import Any, Callable, List, Optional

import carb
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription

if typing.TYPE_CHECKING:  # pragma: no cover
    from .i_ds_event import ILSSEvent as _ILSSEvent


class EventsManagerCore:
    """Manage events"""

    def __init__(self):
        self.__ds_events = []
        self.__global_custom_events = {}

        self.__on_event_registered = _Event()
        self.__on_event_unregistered = _Event()

        self.__on_global_custom_event_registered = _Event()
        self.__on_global_custom_event_unregistered = _Event()

    def get_registered_global_event_names(self) -> List[str]:
        """
        Get a list of registered event(s) name(s)

        Returns:
            The list of event names
        """
        return list(self.__global_custom_events.keys())

    def register_global_custom_event(self, name: str, show_warning: bool = False):
        """
        Register a global custom event

        Args:
            name: the name of your event you want to register
            show_warning: show a warning or not if an event with the same name already exist
        """
        if name in self.__global_custom_events:
            if show_warning:
                carb.log_warn(f"Custom event {name} already exist")
            return
        self.__global_custom_events[name] = _Event()
        self.__on_global_custom_event_registered(name)

    def unregister_global_custom_event(self, name: str):
        """
        Unregister an event

        Args:
            name: the name of the event you want to unregister
        """
        if name in self.__global_custom_events:
            del self.__global_custom_events[name]
            self.__on_global_custom_event_unregistered(name)

    def subscribe_global_custom_event(self, name: str, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        if name not in self.__global_custom_events:
            message = f"Custom event {name} doesn't exist"
            carb.log_error(message)
            raise ValueError(message)
        return _EventSubscription(self.__global_custom_events[name], fn)

    def subscribe_global_custom_event_register(self, fn: Callable[[str], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_global_custom_event_registered, fn)

    def subscribe_global_custom_event_unregister(self, fn: Callable[[str], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_global_custom_event_unregistered, fn)

    def call_global_custom_event(self, name: str, *args, **kwargs):
        """
        Call the registered event

        Args:
            name: the name of the event to call
            *args: args that will be passed to the callbacks
            **kwargs: kwargs that will be passed to the callbacks
        """
        if name not in self.__global_custom_events:
            message = f"Custom event {name} doesn't exist"
            carb.log_error(message)
            raise ValueError(message)
        self.__global_custom_events[name](*args, **kwargs)

    def _event_registered(self):
        """Call the event object that has the list of functions"""
        self.__on_event_registered(self.__ds_events[-1])

    def subscribe_event_registered(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_event_registered, fn)

    def _event_unregistered(self, ds_event: "_ILSSEvent"):
        """Call the event object that has the list of functions"""
        self.__on_event_unregistered(ds_event)

    def subscribe_event_unregistered(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_event_unregistered, fn)

    def register_event(self, ds_event: "_ILSSEvent"):
        """
        Register a new event
        """
        self.__ds_events.append(ds_event)
        ds_event.install()
        self._event_registered()

    def get_registered_events(self) -> List:
        return self.__ds_events

    def get_registered_event(self, name: str) -> Optional["_ILSSEvent"]:
        for event in self.__ds_events:
            if event.name == name:
                return event
        return None

    def unregister_event(self, ds_event: "_ILSSEvent"):
        """
        Unregister a _ILSSEvent
        """
        if ds_event in self.__ds_events:
            ds_event.uninstall()
            self._event_unregistered(ds_event)
            self.__ds_events.remove(ds_event)
        else:
            carb.log_warn(f"Event {ds_event} was never registered")

    def destroy(self):
        for event in self.__ds_events:
            event.uninstall()
        self.__ds_events = []
        self.__global_custom_events = {}
