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

from lightspeed.trex.comfyui.core.enums import ComfyUIEventType
from lightspeed.trex.comfyui.core.events import ComfyUIEventPayload, subscribe_comfyui_event
from omni.flux.stage_manager.factory import StageManagerDataTypes
from omni.flux.stage_manager.plugin.listener.usd.base import StageManagerUSDListenerPlugin
from omni.flux.utils.common import EventSubscription
from pydantic import Field, PrivateAttr


class StageManagerComfyListenerPlugin(StageManagerUSDListenerPlugin[ComfyUIEventType]):
    """
    Stage Manager listener plugin that monitors ComfyUI state, workflow, and endpoint-setting changes.

    This listener uses StageManagerDataTypes.NONE as a wildcard, making it compatible
    with any context data type. Relevant ComfyUI events trigger a corresponding event
    that the Stage Manager can react to.
    """

    display_name: str = Field(default="ComfyUI Listener", exclude=True)
    event_type: type = Field(default=ComfyUIEventType, exclude=True)
    compatible_data_type: StageManagerDataTypes = Field(default=StageManagerDataTypes.NONE, exclude=True)

    _event_subscription: EventSubscription | None = PrivateAttr(default=None)

    def setup(self):
        """Subscribe to ComfyUI state, workflow, and endpoint-setting events."""
        if self._event_subscription is not None:
            return
        self._event_subscription = subscribe_comfyui_event(self._context_name, self._on_comfy_event)

    def cleanup(self):
        """Release the ComfyUI event subscription."""
        self._event_subscription = None

    def _on_comfy_event(self, payload: ComfyUIEventPayload):
        """Forward relevant ComfyUI events to Stage Manager listeners.

        Args:
            payload: ComfyUI event to filter and forward.
        """
        relevant_events: set[ComfyUIEventType] = {
            ComfyUIEventType.STATE_CHANGED,
            ComfyUIEventType.SETTINGS_CHANGED,
            ComfyUIEventType.WORKFLOW_CHANGED,
        }
        if payload.event_type in relevant_events:
            self._event_occurred(payload.event_type)
