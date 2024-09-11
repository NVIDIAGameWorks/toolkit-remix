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

import omni.kit.usd.layers as _layers
from pydantic import PrivateAttr

from .base import StageManagerUSDListenerPlugin as _StageManagerUSDListenerPlugin

if TYPE_CHECKING:
    import carb


class StageManagerUSDLayersListenerPlugin(_StageManagerUSDListenerPlugin[_layers.LayerEventType]):
    """
    A listener triggered whenever a layer event is triggered.
    """

    event_type: type = _layers.LayerEventType

    _layer_event_sub = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._layer_event_sub = None

    def setup(self):
        layers = _layers.get_layers()
        self._layer_event_sub = layers.get_event_stream().create_subscription_to_pop(
            self._on_layer_event, name="StageManagerLayerEventListener"
        )

    def _on_layer_event(self, event: "carb.events.IEvent"):
        """
        Callback executed whenever a layer event is triggered

        Args:
            event: The triggered layer event
        """
        payload = _layers.get_layer_event_payload(event)
        if not payload:
            return
        self._event_occurred(payload.event_type)
