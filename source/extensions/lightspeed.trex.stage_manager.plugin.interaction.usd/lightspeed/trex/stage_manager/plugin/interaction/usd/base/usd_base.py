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

__all__ = ["RemixStageManagerUSDInteractionPlugin"]

from lightspeed.trex.ai_tools.widget import ComfyEventType
from omni.flux.stage_manager.plugin.interaction.usd.base import StageManagerUSDInteractionPlugin


class RemixStageManagerUSDInteractionPlugin(StageManagerUSDInteractionPlugin):
    """
    Base class for all Remix USD interaction plugins.

    Extends the Flux StageManagerUSDInteractionPlugin to subscribe to ComfyUI events,
    enabling interaction plugins to react to ComfyUI connection and workflow state changes.
    All Remix interaction plugins should inherit from this class.
    """

    def _setup_listeners(self):
        """Set up event listeners including ComfyUI event subscription."""
        super()._setup_listeners()
        # Subscribe to ComfyUI events so interactions can react to connection/workflow changes
        self._listener_event_occurred_subs.extend(
            self._context.subscribe_listener_event_occurred(ComfyEventType, self._on_comfy_event_occurred)
        )

    def _on_comfy_event_occurred(self, _):
        """
        Handle ComfyUI events by queuing a UI update.

        Avoid updating the context items since ComfyUI events are not related to USD changes.

        Args:
            _: The event data (unused)
        """
        self._queue_update(update_context_items=False)
