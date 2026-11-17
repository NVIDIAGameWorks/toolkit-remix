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

import omni.usd
from carb.eventdispatcher import Event, ObserverGuard, get_eventdispatcher
from pydantic import Field, PrivateAttr

from .base import StageManagerUSDListenerPlugin as _StageManagerUSDListenerPlugin


class StageManagerUSDStageListenerPlugin(_StageManagerUSDListenerPlugin[omni.usd.StageEventType]):
    """
    A listener triggered whenever a stage event is triggered.
    """

    event_type: type[omni.usd.StageEventType] = Field(default_factory=lambda: omni.usd.StageEventType, exclude=True)

    _stage_event_sub: list[ObserverGuard] | None = PrivateAttr(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._stage_event_sub = None

    def setup(self):
        """Observe every stage event for the configured USD context."""
        super().setup()
        context = omni.usd.get_context(self._context_name)
        # Subscribers receive every stage event, not only the types that current plugins use.
        self._stage_event_sub = [
            get_eventdispatcher().observe_event(
                event_name=context.stage_event_name(omni.usd.StageEventType(event_type)),
                on_event=self._on_stage_event,
                observer_name="omni.flux.stage_manager.plugin.listener.usd:StageManagerUSDStageListenerPlugin._on_stage_event",
            )
            for event_type in range(int(omni.usd.StageEventType.COUNT))
        ]

    def cleanup(self):
        """Release the stage event observers."""
        super().cleanup()
        self._stage_event_sub = None

    def _on_stage_event(self, event: Event):
        """Forward the stage event type to subscribers.

        Args:
            event: The stage event.
        """
        self._event_occurred(omni.usd.stage_event_type(event.event_name))
