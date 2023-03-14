"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import typing
from typing import List, Optional

from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

if typing.TYPE_CHECKING:
    from .i_ds_event import ILSSEvent

EVENTS_MANAGER_INSTANCE = None


class EventsManagerCore:
    """Manage events"""

    def __init__(self, extension_path):
        self.default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self.__ds_events = []

        self.__on_event_registered = _Event()
        self.__on_event_unregistered = _Event()

        global EVENTS_MANAGER_INSTANCE
        EVENTS_MANAGER_INSTANCE = self

    def _event_registered(self):
        """Call the event object that has the list of functions"""
        self.__on_event_registered(self.__ds_events[-1])

    def subscribe_event_registered(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_event_registered, fn)

    def _event_unregistered(self, ds_event: "ILSSEvent"):
        """Call the event object that has the list of functions"""
        self.__on_event_unregistered(ds_event)

    def subscribe_event_unregistered(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_event_unregistered, fn)

    def register_event(self, ds_event: "ILSSEvent"):
        """
        Register a new event
        """
        self.__ds_events.append(ds_event)
        ds_event.install()
        self._event_registered()

    def get_registered_events(self) -> List:
        return self.__ds_events

    def get_registered_event(self, name: str) -> Optional["ILSSEvent"]:
        for event in self.__ds_events:
            if event.name == name:
                return event
        return None

    def unregister_event(self, ds_event: "ILSSEvent"):
        """
        Unregister a ILSSEvent
        """
        ds_event.uninstall()
        self._event_unregistered(ds_event)
        self.__ds_events.remove(ds_event)

    def destroy(self):
        for event in self.__ds_events:
            event.uninstall()
        self.__ds_events = []
        _reset_default_attrs(self)
        global EVENTS_MANAGER_INSTANCE
        EVENTS_MANAGER_INSTANCE = None
