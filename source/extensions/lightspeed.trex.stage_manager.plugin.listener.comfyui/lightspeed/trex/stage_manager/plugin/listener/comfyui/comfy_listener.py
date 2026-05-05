"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["StageManagerComfyListenerPlugin"]

from lightspeed.trex.ai_tools.widget import ComfyEventType
from lightspeed.trex.ai_tools.widget.comfy import get_comfy_interface
from omni.flux.stage_manager.factory import StageManagerDataTypes
from omni.flux.stage_manager.factory.plugins import StageManagerListenerPlugin
from omni.flux.utils.common import EventSubscription
from pydantic import Field, PrivateAttr


class StageManagerComfyListenerPlugin(StageManagerListenerPlugin[ComfyEventType]):
    """
    Stage Manager listener plugin that monitors ComfyUI connection and workflow state changes.

    This listener uses StageManagerDataTypes.NONE as a wildcard, making it compatible
    with any context data type. When ComfyUI connection or workflow state changes,
    it triggers an event that the Stage Manager can react to.
    """

    display_name: str = Field(default="ComfyUI Listener", exclude=True)
    event_type: type = Field(default=ComfyEventType, exclude=True)
    # NONE acts as a wildcard - compatible with any context data type
    compatible_data_type: StageManagerDataTypes = Field(default=StageManagerDataTypes.NONE, exclude=True)

    _event_subscriptions: list[EventSubscription] = PrivateAttr(default_factory=list)

    def setup(self):
        """Subscribe to ComfyUI connection and workflow change events."""
        comfy = get_comfy_interface()
        self._event_subscriptions = [
            comfy.subscribe_connected_changed(self._on_comfy_event),
            comfy.subscribe_workflow_changed(self._on_comfy_event),
        ]

    def cleanup(self):
        """Unsubscribe from ComfyUI events by releasing subscription references."""
        self._event_subscriptions.clear()

    def _on_comfy_event(self, _):
        """
        Callback executed whenever a ComfyUI event is triggered.

        Args:
            _: The event payload (unused)
        """
        self._event_occurred(ComfyEventType())
