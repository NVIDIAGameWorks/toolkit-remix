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
from typing import Any, Callable

from omni.flux.utils.common import EventSubscription as _EventSubscription
from pydantic import Field, field_validator

from ..enums import StageManagerDataTypes as _StageManagerDataTypes
from ..items import StageManagerItem as _StageManagerItem
from .base import StageManagerPluginBase as _StageManagerPluginBase
from .listener_plugin import StageManagerListenerPlugin as _StageManagerListenerPlugin


class StageManagerContextPlugin(_StageManagerPluginBase, abc.ABC):
    """
    A plugin that allows setting up a context for the other Stage Manager plugins to use afterward.

    There should only ever be one context plugin active at any time.
    """

    display_name: str = Field(description="The string to display when displaying the plugin in the UI", exclude=True)
    data_type: _StageManagerDataTypes = Field(
        default=_StageManagerDataTypes.NONE,
        description="The data type that this plugin provides.",
        exclude=True,
    )

    listeners: list[_StageManagerListenerPlugin] = Field(
        description="The listeners that should be used to notify the plugins when data changes"
    )

    @field_validator("listeners", mode="before")
    @classmethod
    def check_unique_listeners(cls, v):  # noqa N805
        # Use a list + validator to keep the list order
        return list(dict.fromkeys(v))

    @abc.abstractmethod
    def get_items(self) -> list[_StageManagerItem]:
        """
        Get the items that should be used by the other plugins. This will be called whenever the interaction plugin
        needs updated data.

        Returns:
            A list of items to be used by the other plugins.
        """
        pass

    def setup(self):
        """
        Set up the context. This will be called once by the core.
        """
        self._validate_data_type()

        for listener in self.listeners:
            listener.setup()

    def cleanup(self):
        """
        Cleanup the context. This will remove all listeners' subscriptions.
        """
        for listener in self.listeners:
            listener.cleanup()

    def subscribe_listener_event_occurred(
        self, event_type: type, function: Callable[[Any], None]
    ) -> list[_EventSubscription]:
        """
        Subscribe to any listener that utilizes a matching event type.

        Args:
            event_type: The event type to listen to
            function: The callback to execute when an event of the given type is executed

        Raises
            ValueError: If no listener is compatible with the given event type

        Returns:
            A list of Event Subscriptions that will unsubscribe automatically on deletion
        """
        expected_listeners = []
        for listener in self.listeners:
            listener_type = listener.event_type
            if isinstance(listener_type, list) and listener_type:
                listener_type = type(listener_type[0])
            if listener_type == event_type:
                expected_listeners.append(listener)
        if not expected_listeners:
            raise ValueError(f"No listener is compatible with event type -> {event_type}")

        return [listener.subscribe_event_occurred(function) for listener in expected_listeners]

    def _validate_data_type(self):
        """
        Validate the compatibility of the context data type

        Raises:
            ValueError: If the data type is not compatible with this plugin
        """
        for listener in self.listeners:
            if self.data_type != listener.compatible_data_type:
                raise ValueError(
                    f"The listener plugin data type is not compatible with this context plugin -> {listener.name} -> "
                    f"{self.data_type.value} != {listener.compatible_data_type.value}"
                )
