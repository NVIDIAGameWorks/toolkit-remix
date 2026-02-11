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

import abc
from typing import Any
from collections.abc import Callable

from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription

from .item_model import SelectionHistoryItem


class SelectionHistoryModel(ui.AbstractItemModel):
    MAX_LIST_LENGTH = 200

    def __init__(self):
        super().__init__()
        self.__items = []
        self.__on_active_items_changed = _Event()

    def refresh(self) -> None:
        """Force a refresh of the model."""
        self._item_changed(None)

    def reset(self):
        """Reset the model"""
        self.__items = []
        self.refresh()

    def insert_items(self, items: list[SelectionHistoryItem], idx: int = 0) -> None:
        """
        Insert items at the given position

        Args:
            items: the items to insert
            idx: the index on the list
        """
        item_added = False
        for item in items:
            if self.__items and item.data == self.__items[0].data:
                continue
            self.__items.insert(idx, item)
            item_added = True
            list_len = len(self.__items)
            # Check if the list exceeds the max length, if it does pop the last element
            if list_len == self.MAX_LIST_LENGTH + 1:
                self.__items.pop()
        # If a new item is added to list, update the items stored in custom layer
        if item_added:
            self.refresh()

    def set_active_items(self, items: list[SelectionHistoryItem]) -> None:
        """
        Set the currently active item. For USD this could be the selected viewport item

        Args:
            items: the items to set as active
        """
        self._set_active_items(items)
        self._on_active_items_changed(items)

    @abc.abstractmethod
    def _set_active_items(self, items: list[SelectionHistoryItem]) -> None:
        """
        Set the currently active item. For USD this could be the selected viewport item

        Args:
            items: the items to set as active
        """
        pass

    def _on_active_items_changed(self, items: list[SelectionHistoryItem]):
        """Call the event object that has the list of functions"""
        self.__on_active_items_changed(items)

    def subscribe_on_active_items_changed(self, function: Callable[[list[SelectionHistoryItem]], Any]):
        """
        Subscribe to the *on_active_items_changed* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_active_items_changed, function)

    def get_active_items(self) -> list[Any]:
        """
        Get the currently active item. For USD this could be the selected viewport item

        Returns:
            A list of all active items
        """
        return self._get_active_items()

    @abc.abstractmethod
    def _get_active_items(self) -> list[Any]:
        """
        Get the currently active item. For USD this could be the selected viewport item

        Returns:
            A list of all active items
        """
        pass

    def get_item_children(self, item: SelectionHistoryItem | None = None):
        """Returns all the children when the widget asks it."""
        # Since we are doing a flat list, we return the children of root only.
        # If it's not root we return.
        return self.__items if not item else []

    def get_item_value_model_count(self, item: SelectionHistoryItem | None = None):
        """The number of columns"""
        return 1

    def get_item_value_model(self, item: SelectionHistoryItem | None = None):
        """
        Return value model.
        It's the object that tracks the specific value.
        """
        return item.title if item else ""
