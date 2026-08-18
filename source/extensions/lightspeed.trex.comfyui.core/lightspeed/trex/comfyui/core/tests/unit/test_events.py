"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

from unittest.mock import patch

from lightspeed.events_manager.core import EventsManagerCore
from lightspeed.trex.comfyui.core.enums import ComfyUIEventType
from lightspeed.trex.comfyui.core.events import (
    COMFYUI_EVENT_NAME,
    publish_comfyui_event,
    subscribe_comfyui_event,
)
from omni.kit.test import AsyncTestCase

__all__ = ("TestComfyUIEvents",)


class TestComfyUIEvents(AsyncTestCase):
    """Test shared, context-qualified ComfyUI event delivery."""

    async def setUp(self) -> None:
        """Register the shared event on an isolated events manager."""
        self._manager = EventsManagerCore()
        self._manager.register_global_custom_event(COMFYUI_EVENT_NAME)
        self._manager_patch = patch(
            "lightspeed.trex.comfyui.core.events._get_event_manager_instance",
            return_value=self._manager,
        )
        self._manager_patch.start()
        self.addCleanup(self._manager_patch.stop)

    async def test_publish_subscriber_failure_notifies_remaining_subscribers(self) -> None:
        """One observer failure cannot stop delivery to the remaining snapshot."""
        # Arrange
        received = []

        def fail(_payload) -> None:
            """Raise the deterministic observer failure."""
            raise AssertionError("observer failed")

        subscriptions = (
            subscribe_comfyui_event("texturecraft", fail),
            subscribe_comfyui_event("texturecraft", received.append),
        )

        with patch("lightspeed.trex.comfyui.core.events.carb.log_error") as log_error:
            # Act
            publish_comfyui_event("texturecraft", ComfyUIEventType.STATE_CHANGED, {"ready": True})

        # Assert
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].context_name, "texturecraft")
        self.assertIs(received[0].event_type, ComfyUIEventType.STATE_CHANGED)
        log_error.assert_called_once()
        self.assertEqual(len(subscriptions), 2)

    async def test_publish_notifies_only_matching_context_subscribers(self) -> None:
        """A context event cannot leak to subscribers for another USD context."""
        # Arrange
        texturecraft_received = []
        stagecraft_received = []
        subscriptions = (
            subscribe_comfyui_event("texturecraft", texturecraft_received.append),
            subscribe_comfyui_event("", stagecraft_received.append),
        )

        # Act
        publish_comfyui_event("texturecraft", ComfyUIEventType.SETTINGS_CHANGED)

        # Assert
        self.assertEqual(len(texturecraft_received), 1)
        self.assertEqual(stagecraft_received, [])
        self.assertEqual(len(subscriptions), 2)
