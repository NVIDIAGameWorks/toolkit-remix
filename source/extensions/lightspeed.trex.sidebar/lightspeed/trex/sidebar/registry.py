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

import asyncio
from enum import Enum
from collections.abc import Callable

import omni.kit.app
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription

__all__ = [
    "Groups",
    "ItemDescriptor",
    "SidebarSubscription",
    "get_items",
    "register_items",
    "subscribe_items_change",
    "unregister_items",
]


class Groups(str, Enum):
    LAYOUTS = "Layouts"
    UNGROUPED = "Ungrouped"


class ItemDescriptor:
    def __init__(
        self,
        name: str | None = "",
        group: str = "",
        tooltip: str | None = None,
        mouse_released_fn: Callable | None = None,
        sort_index: int = 0,
        enabled: bool = True,
        disabled_tooltip: str | None = None,
    ):
        """
        Description of a Sidebar Item (Button, Image, etc.)

        Args:
            name: The widget name (used for styling, icon matching, and ui queries)
            group: Items can optionally be grouped in the sidebar with splitters + labels.
            tooltip: Optional tooltip.
            mouse_released_fn: Callback function for when the button is clicked.
            sort_index: Allows a loose method for sorting the buttons, similar to OV extension load order.
            enabled: Whether the item starts enabled or not.
            disabled_tooltip: Optional tooltip to show when the item is disabled.
        """
        self.name = name
        self.group = group
        self.tooltip = tooltip
        self.mouse_released_fn = mouse_released_fn
        self.sort_index = sort_index
        self.enabled = enabled
        self.disabled_tooltip = disabled_tooltip


class SidebarSubscription:
    """Holds the subscription of ItemDescriptors to the Sidebar with auto-unsubscription when no longer referenced."""

    def __init__(self, items: list[ItemDescriptor]):
        self._items = items

    def set_enabled(self, enabled: bool):
        for item in self._items:
            item.enabled = enabled
        Registry.refresh_deferred()

    def __del__(self):
        unregister_items(self._items)


class Registry:
    """Sidebar Actions Registry."""

    __ITEMS: dict[str, list[ItemDescriptor]] = {}
    __refresh_items: _Event = _Event()
    __pending_refresh: asyncio.Task | None = None

    @classmethod
    def register_items(cls, items_descriptors: list[ItemDescriptor]):
        for item in items_descriptors:
            cls.__ITEMS.setdefault(item.group or Groups.UNGROUPED, []).append(item)
        cls.refresh_deferred()
        return SidebarSubscription(items_descriptors)

    @classmethod
    def unregister_items(cls, items_descriptors: list[ItemDescriptor]):
        for item in items_descriptors:
            if item.group in cls.__ITEMS:
                cls.__ITEMS[item.group].remove(item)
        cls.refresh_deferred()

    @classmethod
    def get_items(cls, group: str | None = None) -> dict[str : list[ItemDescriptor]]:
        if group is None:
            return {grp: items.copy() for grp, items in cls.__ITEMS.items()}

        if group not in cls.__ITEMS:
            return {}

        return {group: cls.__ITEMS[group].copy()}

    @classmethod
    def subscribe_items_change(cls, function: Callable):
        return _EventSubscription(cls.__refresh_items, function)

    @classmethod
    def refresh_deferred(cls):
        if not cls.__pending_refresh:
            cls.__pending_refresh = asyncio.ensure_future(cls.__deferred_refresh_items())

    @classmethod
    async def __deferred_refresh_items(cls):
        await omni.kit.app.get_app().next_update_async()
        cls.__refresh_items()
        cls.__pending_refresh = None


def register_items(items_descriptors: list[ItemDescriptor]):
    return Registry.register_items(items_descriptors)


def unregister_items(items_descriptors: list[ItemDescriptor]):
    return Registry.unregister_items(items_descriptors)


def get_items(group: str | None = None) -> dict[str : list[ItemDescriptor]]:
    return Registry.get_items(group)


def subscribe_items_change(function: Callable):
    return Registry.subscribe_items_change(function)
