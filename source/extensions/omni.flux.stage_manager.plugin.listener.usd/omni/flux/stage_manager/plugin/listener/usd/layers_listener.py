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

import omni.kit.usd.layers as _layers
from carb.eventdispatcher import Event, ObserverGuard, get_eventdispatcher
from pydantic import Field, PrivateAttr

from .base import StageManagerUSDListenerPlugin as _StageManagerUSDListenerPlugin


class StageManagerUSDLayersListenerPlugin(_StageManagerUSDListenerPlugin[_layers.LayerEventType]):
    """
    A listener triggered whenever a layer event is triggered.
    """

    event_type: type[_layers.LayerEventType] = Field(default_factory=lambda: _layers.LayerEventType, exclude=True)

    _layer_event_sub: list[ObserverGuard] | None = PrivateAttr(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._layer_event_sub = None

    def setup(self):
        """Observe every layer event for the default layers instance."""
        super().setup()
        layers = _layers.get_layers()
        # Subscribers receive every layer event, not only the types that current plugins use.
        self._layer_event_sub = [
            get_eventdispatcher().observe_event(
                event_name=_layers.layer_event_name(event_type),
                on_event=self._on_layer_event,
                filter=layers.get_event_key(),
                observer_name="omni.flux.stage_manager.plugin.listener.usd:StageManagerUSDLayersListenerPlugin._on_layer_event",
            )
            for event_type in _layers.LayerEventType
        ]

    def cleanup(self):
        """Release the layer event observers."""
        super().cleanup()
        self._layer_event_sub = None

    def _on_layer_event(self, event: Event):
        """Forward the layer event type to subscribers.

        Args:
            event: The layer event.
        """
        self._event_occurred(_layers.layer_event_type(event.event_name))
