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

from typing import TYPE_CHECKING

from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

if TYPE_CHECKING:
    from .items import WizardPage


class WizardModel:
    def __init__(self, root_item: "WizardPage"):
        """
        The model responsible for driving a WizardWidget

        Args:
            root_item: The first item (WizardPage) the model should display.
        """

        self._default_attr = {
            "_root_item": None,
            "_active_item": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._root_item = root_item
        self._active_item = self._root_item

        self.__on_items_completed = _Event()
        self.__on_active_item_changed = _Event()

    def get_active_item(self) -> "WizardPage":
        """
        Get the currently active page
        """
        return self._active_item

    def reset_active_item(self) -> None:
        """
        Reset the active page to the original page
        """
        self._active_item = self._root_item
        self.on_active_item_changed()

    def go_next(self) -> None:
        """
        Go to the item's next page or complete the wizard if there are no next pages
        """
        if self._active_item.next_page:
            self._active_item = self._active_item.next_page
            self.on_active_item_changed()
        else:
            self.on_items_completed()

    def go_previous(self) -> None:
        """
        Go to the item's previous page
        """
        if self._active_item.previous_page:
            self._active_item = self._active_item.previous_page
        self.on_active_item_changed()

    def on_items_completed(self):
        """
        Trigger the on_items_completed event
        """
        self.__on_items_completed(self.get_active_item().payload)

    def subscribe_on_items_completed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when the wizard is completed.
        """
        return _EventSubscription(self.__on_items_completed, function)

    def on_active_item_changed(self):
        """
        Trigger the "__on_active_item_changed" event
        """
        # Make sure the new active item has the right request functions set
        self._active_item.set_request_next_fn(self.go_next)
        self._active_item.set_request_previous_fn(self.go_previous)

        self.__on_active_item_changed()

    def subscribe_on_active_item_changed(self, function):
        """
        Return an object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_active_item_changed, function)

    def destroy(self):
        """Destroy."""
        _reset_default_attrs(self)
