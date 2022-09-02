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
from typing import List

if typing.TYPE_CHECKING:
    from .i_ds_event import ILSSEvent

EVENTS_MANAGER_INSTANCE = None


class EventsManagerCore:
    """Manage events"""

    class _Event(set):
        """
        A list of callable objects. Calling an instance of this will cause a
        call to each item in the list in ascending order by index.
        """

        def __call__(self, *args, **kwargs):
            """Called when the instance is “called” as a function"""
            # Call all the saved functions
            for f in self:
                f(*args, **kwargs)

        def __repr__(self):
            """
            Called by the repr() built-in function to compute the “official”
            string representation of an object.
            """
            return f"Event({set.__repr__(self)})"

    class _EventSubscription:
        """
        Event subscription.

        _Event has callback while this object exists.
        """

        def __init__(self, event, fn):
            """
            Save the function, the event, and add the function to the event.
            """
            self._fn = fn
            self._event = event
            event.add(self._fn)

        def __del__(self):
            """Called by GC."""
            self._event.remove(self._fn)

    def __init__(self, extension_path):
        self.default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self.__ds_events = []

        self.__on_event_registered = self._Event()
        self.__on_event_unregistered = self._Event()

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
        return self._EventSubscription(self.__on_event_registered, fn)

    def _event_unregistered(self, ds_event: "ILSSEvent"):
        """Call the event object that has the list of functions"""
        self.__on_event_unregistered(ds_event)

    def subscribe_event_unregistered(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return self._EventSubscription(self.__on_event_unregistered, fn)

    def register_event(self, ds_event: "ILSSEvent"):
        """
        Register a new event
        """
        self.__ds_events.append(ds_event)
        ds_event.install()
        self._event_registered()

    def get_registered_events(self) -> List:
        return self.__ds_events

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
        for attr, value in self.default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()
                del m_attr
                setattr(self, attr, value)
        global EVENTS_MANAGER_INSTANCE
        EVENTS_MANAGER_INSTANCE = None
