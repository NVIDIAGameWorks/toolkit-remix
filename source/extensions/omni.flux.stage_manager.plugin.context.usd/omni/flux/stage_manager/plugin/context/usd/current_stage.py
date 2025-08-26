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
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pxr import Usd
from pydantic import Field, PrivateAttr, field_validator

from .base import StageManagerUSDContextPlugin as _StageManagerUSDContextPlugin


class CurrentStageContextPlugin(_StageManagerUSDContextPlugin):
    display_name: str = Field(default="Current Stage", exclude=True)
    context_name: str = Field(description="The name of the context from which to get the stage", exclude=True)

    _stage: Usd.Stage | None = PrivateAttr(default=None)
    _listener_event_occurred_subs: list[_EventSubscription] = PrivateAttr(default=[])

    @field_validator("context_name", mode="before")
    @classmethod
    def context_name_is_valid(cls, v):  # noqa N805
        if not omni.usd.get_context(v):
            raise ValueError("The context does not exist")
        return v

    def setup(self):
        """
        Set up the context. This will be called once by the core.

        Raises:
            ValueError: If no stage exists for the given context
        """
        self._stage = omni.usd.get_context(self.context_name).get_stage()
        super().setup()
        self._listener_event_occurred_subs.extend(
            self.subscribe_listener_event_occurred(omni.usd.StageEventType, self._on_stage_event_occurred)
        )

    def cleanup(self):
        self._listener_event_occurred_subs.clear()
        self._stage = None
        super().cleanup()

    def update_stage(self):
        """
        Setup the stage. This will be called on open or close stage.
        """
        self.cleanup()
        self._stage = omni.usd.get_context(self.context_name).get_stage()
        self.setup()

    def get_items(self):
        """
        Fetch the list of prims other plugins should use

        Raises:
            ValueError: If the context was not setup

        Returns:
            List of USD prims
        """
        if not self._listener_event_occurred_subs:
            raise ValueError("The context plugin was not setup")
        if not self._stage:
            return []  # no stage is open

        items = {}
        current_layer = self._stage.GetPseudoRoot().GetChildren()

        while current_layer:
            next_layer = []

            for prim in current_layer:
                item = _StageManagerItem(hash(prim), prim, parent=items.get(hash(prim.GetParent())))
                items[item.identifier] = item

                # Add children to the next layer
                next_layer.extend(prim.GetFilteredChildren(Usd.PrimAllPrimsPredicate))

            current_layer = next_layer

        return list(items.values())

    def _on_stage_event_occurred(self, event_type: omni.usd.StageEventType):
        """
        An event callback ake sure to update the cached stage when the stage changes

        Args:
            event_type: The stage event type
        """
        if event_type in [omni.usd.StageEventType.OPENED, omni.usd.StageEventType.CLOSED]:
            # Make sure to update the cached stage
            self.update_stage()
