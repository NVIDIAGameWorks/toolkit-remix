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

import carb
import omni.usd
from pydantic import Field, PrivateAttr

from .base import StageManagerUSDListenerPlugin as _StageManagerUSDListenerPlugin


class StageManagerUSDStageListenerPlugin(_StageManagerUSDListenerPlugin[omni.usd.StageEventType]):
    """
    A listener triggered whenever a stage event is triggered.
    """

    event_type: type[omni.usd.StageEventType] = Field(default_factory=lambda: omni.usd.StageEventType, exclude=True)

    _stage_event_sub: carb.events.ISubscription | None = PrivateAttr(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._stage_event_sub = None

    def setup(self):
        context = omni.usd.get_context(self._context_name)
        self._stage_event_sub = context.get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event, name="StageManagerStageEventListener"
        )

    def _on_stage_event(self, event: "carb.events.IEvent"):
        """
        Callback executed whenever a stage event is triggered

        Args:
            event: The triggered stage event
        """
        try:
            # Convert the integer to the corresponding Enum entry
            self._event_occurred(omni.usd.StageEventType(event.type))
        except ValueError:
            # Unknown event, ignore it
            carb.log_error(f"An unknown stage event occurred: {event.type}")
