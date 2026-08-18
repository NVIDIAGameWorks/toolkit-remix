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

from unittest import mock

from omni.kit.test import AsyncTestCase

from lightspeed.trex.comfyui.core.connection import get_connected_endpoint, set_connected_endpoint


class TestConnection(AsyncTestCase):
    """Test connected ComfyUI endpoint snapshots."""

    async def setUp(self) -> None:
        """Clear endpoint snapshots used by each test."""
        set_connected_endpoint("texturecraft", None)
        set_connected_endpoint("stagecraft", None)

    async def tearDown(self) -> None:
        """Clear endpoint snapshots created by each test."""
        set_connected_endpoint("texturecraft", None)
        set_connected_endpoint("stagecraft", None)

    async def test_set_connected_endpoint_keeps_context_snapshots_independent(self) -> None:
        """Each USD context exposes only its own verified endpoint."""
        # Arrange
        texturecraft_endpoint = ("http", "comfy-a", 8188)
        stagecraft_endpoint = ("https", "comfy-b", 443)

        # Act
        set_connected_endpoint("texturecraft", texturecraft_endpoint)
        set_connected_endpoint("stagecraft", stagecraft_endpoint)

        # Assert
        self.assertEqual(get_connected_endpoint("texturecraft"), texturecraft_endpoint)
        self.assertEqual(get_connected_endpoint("stagecraft"), stagecraft_endpoint)

    async def test_set_connected_endpoint_none_clears_only_requested_context(self) -> None:
        """Disconnecting one context leaves other connected contexts intact."""
        # Arrange
        set_connected_endpoint("texturecraft", ("http", "comfy-a", 8188))
        stagecraft_endpoint = ("https", "comfy-b", 443)
        set_connected_endpoint("stagecraft", stagecraft_endpoint)

        # Act
        set_connected_endpoint("texturecraft", None)

        # Assert
        self.assertIsNone(get_connected_endpoint("texturecraft"))
        self.assertEqual(get_connected_endpoint("stagecraft"), stagecraft_endpoint)

    async def test_set_connected_endpoint_notifies_queue_when_endpoint_changes(self) -> None:
        """Connecting to a different endpoint wakes jobs waiting for that service."""
        # Arrange
        with mock.patch("lightspeed.trex.comfyui.core.connection.get_job_queue") as get_job_queue_mock:
            # Act
            set_connected_endpoint("texturecraft", ("http", "comfy-a", 8188))

        # Assert
        get_job_queue_mock.return_value.notify_schedule_conditions_changed.assert_called_once_with()

    async def test_set_connected_endpoint_does_not_notify_queue_when_endpoint_is_unchanged(self) -> None:
        """Re-publishing the current endpoint does not wake idle queue consumers."""
        # Arrange
        endpoint = ("http", "comfy-a", 8188)
        set_connected_endpoint("texturecraft", endpoint)
        with mock.patch("lightspeed.trex.comfyui.core.connection.get_job_queue") as get_job_queue_mock:
            # Act
            set_connected_endpoint("texturecraft", endpoint)

        # Assert
        get_job_queue_mock.return_value.notify_schedule_conditions_changed.assert_not_called()

    async def test_set_connected_endpoint_notifies_queue_when_endpoint_is_cleared(self) -> None:
        """Disconnecting wakes consumers so visible rows immediately explain the wait."""
        # Arrange
        set_connected_endpoint("texturecraft", ("http", "comfy-a", 8188))
        with mock.patch("lightspeed.trex.comfyui.core.connection.get_job_queue") as get_job_queue_mock:
            # Act
            set_connected_endpoint("texturecraft", None)

        # Assert
        get_job_queue_mock.return_value.notify_schedule_conditions_changed.assert_called_once_with()
