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

import omni.kit.menu.utils as omni_utils
from omni.kit.menu.utils import MenuItemDescription


class _SetupMenu:
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

        self._default_attr = {"_menus": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self.__create_menu()

        self.__on_menu1_clicked = self._Event()
        self.__on_menu2_clicked = self._Event()

    def _menu1_clicked(self):
        """Call the event object that has the list of functions"""
        self.__on_menu1_clicked()

    def subscribe_menu1_clicked(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_menu1_clicked, fn)

    def _menu2_clicked(self):
        """Call the event object that has the list of functions"""
        self.__on_menu2_clicked()

    def subscribe_menu2_clicked(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_menu2_clicked, fn)

    def __create_menu(self):
        """Create the menu to Save scenario"""
        self._menus = [
            MenuItemDescription(
                name="Lightspeed Example Menu1", onclick_fn=self._menu1_clicked, glyph="none.svg", appear_after="Save"
            ),
            MenuItemDescription(
                name="Lightspeed Example Menu2",
                onclick_fn=self._menu2_clicked,
                glyph="none.svg",
                appear_after="Lightspeed Example Menu1",
            ),
        ]
        omni_utils.add_menu_items(self._menus, "File")

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
                del m_attr  # noqa PLW4701
                setattr(self, attr, value)


def create_menu():
    return _SetupMenu()
