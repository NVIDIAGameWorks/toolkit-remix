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
from typing import Any, Callable, Iterable

from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pydantic import Field, PrivateAttr

from .base import StageManagerUIPluginBase as _StageManagerUIPluginBase


class StageManagerFilterPlugin(_StageManagerUIPluginBase, abc.ABC):
    """
    A plugin that allows filtering a list of items based on parameters controlled within the plugin
    """

    display: bool = Field(True, description="Whether the filter plugin should be displayed in the UI")

    _on_filter_items_changed: _Event = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._on_filter_items_changed = _Event()

    @abc.abstractmethod
    def filter_items(self, items: Iterable[Any]) -> list[Any]:
        """
        Args:
            items: The list of items to filter.

        Returns:
            A list of filtered items.
        """
        pass

    def subscribe_filter_items_changed(self, callback: Callable[[], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self._on_filter_items_changed, callback)

    def _filter_items_changed(self):
        """
        Trigger the `on_items_changed` event.
        """
        self._on_filter_items_changed()
