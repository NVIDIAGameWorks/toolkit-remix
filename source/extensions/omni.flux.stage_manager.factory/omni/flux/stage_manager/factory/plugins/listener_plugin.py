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
from typing import Generic, TypeVar
from collections.abc import Callable

from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pydantic import Field, PrivateAttr

from ..enums import StageManagerDataTypes as _StageManagerDataTypes
from .base import StageManagerPluginBase as _StageManagerPluginBase

T = TypeVar("T")


class StageManagerListenerPlugin(_StageManagerPluginBase, Generic[T], abc.ABC):
    """
    A plugin that allows listening to a source and notify any plugin listening
    """

    event_type: type = Field(description="The type of event that this listener subscribes to", exclude=True)
    compatible_data_type: _StageManagerDataTypes = Field(
        default=_StageManagerDataTypes.NONE, description="The data type that this listener supports.", exclude=True
    )

    _on_event_occurred: _Event = PrivateAttr(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._on_event_occurred = _Event()

    @abc.abstractmethod
    def setup(self):
        """
        A method called during the context initialization to initialize the listener
        """
        pass

    @abc.abstractmethod
    def cleanup(self):
        """
        Cleanup the listeners' subscriptions.
        """
        pass

    def subscribe_event_occurred(self, callback: Callable[[T], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self._on_event_occurred, callback)

    def _event_occurred(self, data: T):
        """
        Trigger the `on_event_occurred` event.

        Args:
            data: Any data that might be relevant to the event
        """
        self._on_event_occurred(data)
