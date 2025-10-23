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

from typing import Any


class Event(set):
    """
    A list of callable objects. Calling an instance of this will cause a
    call to each item in the list in ascending order by index.
    """

    def __init__(self, *args, copy: bool = False, **kwargs):
        """
        Init of a set function

        Args:
            *args: any args
            copy: Make a copy of the iterated subscribers list/set if it might change while the event is being triggered
                I.e: A button that dynamically adds/deletes callbacks as it gets clicked.
            **kwargs: any kwargs
        """
        super().__init__(*args, **kwargs)
        self.__copy = copy

    def __call__(self, *args, **kwargs) -> list[Any]:
        """Calls all subscribed callees and returns their results"""
        # Call all the saved functions
        obj = self.copy() if self.__copy else self
        return [function(*args, **kwargs) for function in obj]

    def __repr__(self):
        """
        Called by the repr() built-in function to compute the “official”
        string representation of an object.
        """
        return f"Event({set.__repr__(self)})"


class EventSubscription:
    """
    Holds an Event subscription, auto-unsubscribed when no longer referenced and gets destroyed by GC.

    Event holds the callback while this object exists.
    """

    def __init__(self, event, function):
        """
        Save the function, the event, and add the function to the event.
        """
        self._fn = function
        self._event = event
        event.add(self._fn)

    def __del__(self):
        """Called by GC."""
        self._event.remove(self._fn)
