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

from __future__ import annotations

import abc

from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class WizardPage:
    def __init__(
        self,
        previous_page: WizardPage | None = None,
        next_page: WizardPage | None = None,
        next_text: str = "Next",
        previous_text: str = "Previous",
        done_text: str = "Done",
        blocked: bool = False,
        hide_navigation: bool = False,
    ):
        """
        The items used by the WizardModel. An item is a page and is rendered inside the wizard.
        The `create_ui` method should be implemented to determine what the page will look like.

        Args:
            previous_page: A reference to the page to render when going to the previous page.
                           If None, the "Previous" button will be disabled.
            next_page: A reference to the page to render when going to the next page.
                       If None, the "Next" button will become the "Done" button.
            next_text: Text to use for the "Next" button
            previous_text: Text to use for the "Previous" button
            done_text: Text to use for the "Done" button
            blocked: Whether the widget navigation should be blocked or not
            hide_navigation: Whether the widget navigation bar should be visible or not
        """

        # Do not include self._previous_page as a default attribute to avoid recursive deletion of pages
        # - Current -> previous -> next == current. Only delete pages forward
        self._default_attr = {
            # "_previous_page": None,
            "_next_page": None,
            "_next_text": None,
            "_previous_text": None,
            "_done_text": None,
            "_blocked": None,
            "_hide_navigation": None,
            "_payload": None,
            "_request_next_fn": None,
            "_request_previous_fn": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._previous_page = previous_page
        self._next_page = next_page
        self._next_text = next_text
        self._previous_text = previous_text
        self._done_text = done_text
        self._blocked = blocked
        self._hide_navigation = hide_navigation

        self._payload = {}
        self._request_next_fn = None
        self._request_previous_fn = None

        self.__on_blocked_changed = _Event()

    @property
    def previous_page(self) -> WizardPage | None:
        """
        The page that precedes this one
        """
        return self._previous_page

    @property
    def next_page(self) -> WizardPage | None:
        """
        The page that follows this one. This can be dynamically adjusted in the `create_ui` method.
        """
        return self._next_page

    @next_page.setter
    def next_page(self, value: WizardPage) -> None:
        """
        The page that follows this one. This can be dynamically adjusted in the `create_ui` method.
        """
        self._next_page = value

    @property
    def previous_text(self) -> str:
        """
        Text displayed in the "previous" button of the wizard
        """
        return self._previous_text

    @property
    def next_text(self) -> str:
        """
        Text displayed in the "next" button of the wizard
        """
        return self._next_text

    @property
    def done_text(self) -> str:
        """
        Text displayed in the "done" button of the wizard
        """
        return self._done_text

    @property
    def blocked(self) -> bool:
        """
        Whether the page is blocked or is allowed move on to the next page
        """
        return self._blocked

    @blocked.setter
    def blocked(self, value: bool) -> None:
        """
        Whether the page is blocked or is allowed move on to the next page
        """
        value_changed = self._blocked != value
        self._blocked = value
        if value_changed:
            self.on_blocked_changed()

    @property
    def hide_navigation(self) -> bool:
        """
        Whether the page should hide the navigation buttons in the wizard or not
        """
        return self._hide_navigation

    @property
    def payload(self) -> dict:
        """
        The payload includes data from all previous pages.
        """
        payload = self._payload
        if self._previous_page:
            payload.update(self._previous_page.payload)
        return payload

    @payload.setter
    def payload(self, value: dict) -> None:
        """
        Non-destructively insert data in the page's payload
        """
        self._payload.update(value)

    @abc.abstractmethod
    def create_ui(self):
        """
        The UI displayed in the Wizard should be defined in this method.
        """
        pass

    def on_blocked_changed(self):
        """
        Trigger the "on_blocked_changed" event
        """
        self.__on_blocked_changed()

    def subscribe_on_blocked_changed(self, function):
        """
        Return an object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_blocked_changed, function)

    def set_request_next_fn(self, function):
        """
        Set a function to be called whenever the items requests to go next
        """
        self._request_next_fn = function

    def set_request_previous_fn(self, function):
        """
        Set a function to be called whenever the items requests to go previous
        """
        self._request_previous_fn = function

    def request_next(self):
        """
        Request the model to go next. The model must set the request_next_fn
        """
        if not self._request_next_fn:
            raise NotImplementedError("The request_next function must be set before it's called")
        self._request_next_fn()

    def request_previous(self):
        """
        Request the model to go previous. The model must set the request_previous_fn
        """
        if not self._request_previous_fn:
            raise NotImplementedError("The request_previous function must be set before it's called")
        self._request_previous_fn()

    def destroy(self):
        """Destroy."""
        self._previous_page = None  # Prevent recursive destroy by only deleting pages forward
        _reset_default_attrs(self)
