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

from unittest.mock import MagicMock, patch

from lightspeed.trex.comfyui.core.enums import ComfyUIEventType
from lightspeed.trex.comfyui.core.events import ComfyUIEventPayload
from lightspeed.trex.stage_manager.plugin.listener.comfyui.comfy_listener import StageManagerComfyListenerPlugin
from omni.kit.test import AsyncTestCase


class TestStageManagerComfyListenerPlugin(AsyncTestCase):
    """Test the Stage Manager ComfyUI listener integration."""

    async def test_workflow_event_forwards_actual_event_type(self):
        """Workflow changes retain their event type when forwarded."""
        # Arrange
        listener = StageManagerComfyListenerPlugin()
        listener._event_occurred = MagicMock()
        payload = ComfyUIEventPayload("", ComfyUIEventType.WORKFLOW_CHANGED)

        # Act
        listener._on_comfy_event(payload)

        # Assert
        listener._event_occurred.assert_called_once_with(ComfyUIEventType.WORKFLOW_CHANGED)

    async def test_irrelevant_event_is_not_forwarded(self):
        """Non-Stage-Manager ComfyUI events are ignored."""
        # Arrange
        listener = StageManagerComfyListenerPlugin()
        listener._event_occurred = MagicMock()
        payload = ComfyUIEventPayload("", ComfyUIEventType.WORKFLOWS_LOADED)

        # Act
        listener._on_comfy_event(payload)

        # Assert
        listener._event_occurred.assert_not_called()

    async def test_settings_event_forwards_actual_event_type(self):
        """Shared endpoint changes trigger Stage Manager readiness recomputation."""
        # Arrange
        listener = StageManagerComfyListenerPlugin()
        listener._event_occurred = MagicMock()
        payload = ComfyUIEventPayload("", ComfyUIEventType.SETTINGS_CHANGED)

        # Act
        listener._on_comfy_event(payload)

        # Assert
        listener._event_occurred.assert_called_once_with(ComfyUIEventType.SETTINGS_CHANGED)

    async def test_setup_uses_injected_usd_context(self):
        """Listener setup subscribes using its configured USD context."""
        # Arrange
        listener = StageManagerComfyListenerPlugin()
        listener.set_context_name("texturecraft")

        # Act
        with patch(
            "lightspeed.trex.stage_manager.plugin.listener.comfyui.comfy_listener.subscribe_comfyui_event"
        ) as subscribe:
            listener.setup()

        # Assert
        subscribe.assert_called_once_with("texturecraft", listener._on_comfy_event)

    async def test_repeated_setup_keeps_one_subscription(self):
        """Repeated setup calls do not register duplicate event callbacks."""
        # Arrange
        listener = StageManagerComfyListenerPlugin()
        listener.set_context_name("texturecraft")
        with patch(
            "lightspeed.trex.stage_manager.plugin.listener.comfyui.comfy_listener.subscribe_comfyui_event"
        ) as subscribe:
            # Act
            listener.setup()
            listener.setup()

        # Assert
        subscribe.assert_called_once_with("texturecraft", listener._on_comfy_event)

    async def test_cleanup_releases_event_subscription(self):
        """Listener cleanup releases its ComfyUI event subscription."""
        # Arrange
        listener = StageManagerComfyListenerPlugin()
        listener._event_subscription = MagicMock()

        # Act
        listener.cleanup()

        # Assert
        self.assertIsNone(listener._event_subscription)
