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

__all__ = ["TestEventCameraClipRangeOverrideExtension"]

from unittest.mock import MagicMock, patch

from omni.kit.test import AsyncTestCase

from lightspeed.event.camera_clip_range_override import extension as _extension
from lightspeed.event.camera_clip_range_override.extension import (
    EventCameraClipRangeOverrideExtension,
)


class TestEventCameraClipRangeOverrideExtension(AsyncTestCase):
    """REMIX-4628: tests for the extension lifecycle hooks."""

    async def test_on_startup_registers_event(self):
        """on_startup must construct the event and register it with the events manager."""
        # Arrange
        ext = EventCameraClipRangeOverrideExtension()
        fake_event = MagicMock()
        fake_manager = MagicMock()

        # Act
        with (
            patch.object(_extension, "_EventCameraClipRangeOverride", return_value=fake_event),
            patch.object(_extension, "_get_event_manager_instance", return_value=fake_manager),
        ):
            ext.on_startup(ext_id="lightspeed.event.camera_clip_range_override-1.0.0")

        # Assert
        self.assertIs(ext._core, fake_event)
        fake_manager.register_event.assert_called_once_with(fake_event)

    async def test_on_shutdown_unregisters_event(self):
        """on_shutdown must unregister the event from the events manager."""
        # Arrange
        ext = EventCameraClipRangeOverrideExtension()
        ext.default_attr = {"_core": None}
        fake_event = MagicMock()
        ext._core = fake_event
        fake_manager = MagicMock()

        # Act
        with patch.object(_extension, "_get_event_manager_instance", return_value=fake_manager):
            ext.on_shutdown()

        # Assert
        fake_manager.unregister_event.assert_called_once_with(fake_event)
