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
            copy: if True, it will execute callback(s) from a copy of the set. Why? It can happen that we have a
                circular pattern where an event execute a callback that will re-create/delete the event itself.
                For example, imagine a button that sets an event when we click on it. And the event is that this is
                re-creating the button itself (and the event).
                As a result, you could have an error like `RuntimeError: Set changed size during iteration`.
                We don't set this to True by default to force the dev to be aware of the pattern he is doing.
            **kwargs: any kwargs
        """
        super().__init__(*args, **kwargs)
        self.__copy = copy

    def __call__(self, *args, **kwargs):
        """Called when the instance is “called” as a function"""
        # Call all the saved functions
        if self.__copy:
            for function in self.copy():
                function(*args, **kwargs)
        else:
            for function in self:
                function(*args, **kwargs)

    def __repr__(self):
        """
        Called by the repr() built-in function to compute the “official”
        string representation of an object.
        """
        return f"Event({set.__repr__(self)})"


class EventSubscription:
    """
    Event subscription.

    _Event has callback while this object exists.
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
