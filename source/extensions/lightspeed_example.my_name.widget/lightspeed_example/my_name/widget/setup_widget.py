"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.ui as ui


class _SetupWidget:
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

    def __init__(self):
        """Example widget"""

        self._default_attr = {"_button1": None, "_button2": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self.__create_ui()

        self.__on_button1_clicked = self._Event()
        self.__on_button2_clicked = self._Event()

    def _button1_clicked(self):
        """Call the event object that has the list of functions"""
        self.__on_button1_clicked()

    def subscribe_button1_clicked(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_button1_clicked, fn)

    def _button2_clicked(self):
        """Call the event object that has the list of functions"""
        self.__on_button2_clicked()

    def subscribe_button2_clicked(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_button2_clicked, fn)

    def __create_ui(self):
        """Create the widget
        When someone clicks on the buttons, it will fired the subscriptions
        """
        with ui.VStack():
            self._button1 = ui.Button("Button1", clicked_fn=self._button1_clicked, name="Button1")
            self._button2 = ui.Button("Button2", clicked_fn=self._button2_clicked, name="Button2")

    def destroy(self):
        for attr, value in self._default_attr.items():
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


def create_widget():
    return _SetupWidget()
