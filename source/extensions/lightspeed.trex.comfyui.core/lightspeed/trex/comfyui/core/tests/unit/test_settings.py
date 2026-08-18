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

import lightspeed.trex.comfyui.core.settings as settings
from lightspeed.trex.comfyui.core.enums import ComfyUIProtocol
from lightspeed.trex.comfyui.core.settings import ComfyUISettings
from omni.kit.test import AsyncTestCase

__all__ = ("TestComfyUISettings",)


class TestComfyUISettings(AsyncTestCase):
    """Tests for ComfyUI connection settings."""

    async def test_host_getter_rejects_invalid_persisted_value(self):
        """Invalid persisted hosts fall back to the safe local default."""
        # Arrange
        backend = MagicMock()
        backend.get_as_string.return_value = "bad host!"
        subject = ComfyUISettings()

        # Act
        with patch.object(settings, "get_settings", return_value=backend):
            result = subject.host

        # Assert
        self.assertEqual(result, "127.0.0.1")

    async def test_port_getter_rejects_out_of_range_persisted_value(self):
        """Out-of-range persisted ports fall back to the ComfyUI default."""
        # Arrange
        backend = MagicMock()
        backend.get_as_int.return_value = 65536
        subject = ComfyUISettings()

        # Act
        with patch.object(settings, "get_settings", return_value=backend):
            result = subject.port

        # Assert
        self.assertEqual(result, 8188)

    async def test_protocol_getter_returns_persisted_value(self):
        """protocol decodes persisted known enum values."""
        # Arrange
        backend = MagicMock()
        subject = ComfyUISettings()

        with patch.object(settings, "get_settings", return_value=backend):
            backend.get.return_value = ComfyUIProtocol.HTTPS.scheme

            # Act
            result = subject.protocol

        # Assert
        self.assertEqual(result, ComfyUIProtocol.HTTPS)

    async def test_protocol_getter_returns_default_for_unknown_value(self):
        """protocol falls back to HTTP for unknown persisted values."""
        # Arrange
        backend = MagicMock()
        subject = ComfyUISettings()

        with patch.object(settings, "get_settings", return_value=backend):
            backend.get.return_value = "ftp"

            # Act
            result = subject.protocol

        # Assert
        self.assertEqual(result, ComfyUIProtocol.HTTP)

    async def test_host_getter_returns_persisted_value(self):
        """host returns persisted non-empty values."""
        # Arrange
        backend = MagicMock()
        subject = ComfyUISettings()

        with patch.object(settings, "get_settings", return_value=backend):
            backend.get_as_string.return_value = "comfy.example"

            # Act
            result = subject.host

        # Assert
        self.assertEqual(result, "comfy.example")

    async def test_host_getter_returns_default_for_empty_value(self):
        """host falls back to localhost when storage is empty."""
        # Arrange
        backend = MagicMock()
        subject = ComfyUISettings()

        with patch.object(settings, "get_settings", return_value=backend):
            backend.get_as_string.return_value = ""

            # Act
            result = subject.host

        # Assert
        self.assertEqual(result, "127.0.0.1")

    async def test_port_getter_returns_persisted_value(self):
        """port returns persisted positive values."""
        # Arrange
        backend = MagicMock()
        subject = ComfyUISettings()

        with patch.object(settings, "get_settings", return_value=backend):
            backend.get_as_int.return_value = 443

            # Act
            result = subject.port

        # Assert
        self.assertEqual(result, 443)

    async def test_port_getter_returns_default_for_invalid_value(self):
        """port falls back to 8188 for invalid values."""
        # Arrange
        backend = MagicMock()
        subject = ComfyUISettings()

        with patch.object(settings, "get_settings", return_value=backend):
            backend.get_as_int.return_value = 0

            # Act
            result = subject.port

        # Assert
        self.assertEqual(result, 8188)

    async def test_protocol_setter_persists_and_notifies_observer(self):
        """set_protocol persists values and notifies its observer."""
        # Arrange
        backend = MagicMock()
        observer = MagicMock()
        subject = ComfyUISettings(settings_changed_callback=observer)

        with patch.object(settings, "get_settings", return_value=backend):
            # Act
            subject.set_protocol(ComfyUIProtocol.HTTPS)

        # Assert
        backend.set.assert_called_once_with(
            "/persistent/exts/lightspeed.trex.comfyui.core/protocol",
            "https",
        )
        observer.assert_called_once_with("protocol", ComfyUIProtocol.HTTPS)

    async def test_host_setter_ignores_invalid_value(self):
        """set_host ignores empty values."""
        # Arrange
        backend = MagicMock()
        observer = MagicMock()
        subject = ComfyUISettings(settings_changed_callback=observer)

        with patch.object(settings, "get_settings", return_value=backend):
            # Act
            subject.set_host("")

        # Assert
        backend.set.assert_not_called()
        observer.assert_not_called()

    async def test_port_setter_ignores_invalid_value(self):
        """set_port ignores non-positive values."""
        # Arrange
        backend = MagicMock()
        observer = MagicMock()
        subject = ComfyUISettings(settings_changed_callback=observer)

        with patch.object(settings, "get_settings", return_value=backend):
            # Act
            subject.set_port(0)

        # Assert
        backend.set.assert_not_called()
        observer.assert_not_called()

    async def test_host_setter_persists_and_notifies_observer(self):
        """set_host persists valid values and notifies its observer."""
        # Arrange
        backend = MagicMock()
        observer = MagicMock()
        subject = ComfyUISettings(settings_changed_callback=observer)

        with patch.object(settings, "get_settings", return_value=backend):
            # Act
            subject.set_host("comfy.example")

        # Assert
        backend.set.assert_called_once_with(
            "/persistent/exts/lightspeed.trex.comfyui.core/host",
            "comfy.example",
        )
        observer.assert_called_once_with("host", "comfy.example")

    async def test_port_setter_persists_and_notifies_observer(self):
        """set_port persists valid values and notifies its observer."""
        # Arrange
        backend = MagicMock()
        observer = MagicMock()
        subject = ComfyUISettings(settings_changed_callback=observer)

        with patch.object(settings, "get_settings", return_value=backend):
            # Act
            subject.set_port(8189)

        # Assert
        backend.set.assert_called_once_with(
            "/persistent/exts/lightspeed.trex.comfyui.core/port",
            8189,
        )
        observer.assert_called_once_with("port", 8189)

    async def test_protocol_setter_ignores_unchanged_value(self):
        """Recommitting the protocol cannot invalidate a live connection."""
        # Arrange
        backend = MagicMock()
        backend.get.return_value = ComfyUIProtocol.HTTPS.scheme
        observer = MagicMock()
        subject = ComfyUISettings(settings_changed_callback=observer)

        with patch.object(settings, "get_settings", return_value=backend):
            # Act
            subject.set_protocol(ComfyUIProtocol.HTTPS)

        # Assert
        backend.set.assert_not_called()
        observer.assert_not_called()

    async def test_host_setter_ignores_unchanged_value(self):
        """Recommitting the host cannot invalidate a live connection."""
        # Arrange
        backend = MagicMock()
        backend.get_as_string.return_value = "comfy.example"
        observer = MagicMock()
        subject = ComfyUISettings(settings_changed_callback=observer)

        with patch.object(settings, "get_settings", return_value=backend):
            # Act
            subject.set_host("comfy.example")

        # Assert
        backend.set.assert_not_called()
        observer.assert_not_called()

    async def test_port_setter_ignores_unchanged_value(self):
        """Recommitting the port cannot invalidate a live connection."""
        # Arrange
        backend = MagicMock()
        backend.get_as_int.return_value = 8189
        observer = MagicMock()
        subject = ComfyUISettings(settings_changed_callback=observer)

        with patch.object(settings, "get_settings", return_value=backend):
            # Act
            subject.set_port(8189)

        # Assert
        backend.set.assert_not_called()
        observer.assert_not_called()

    async def test_setter_without_observer_still_persists(self):
        """An observer is optional for callers that only need persistence."""
        # Arrange
        backend = MagicMock()
        subject = ComfyUISettings()

        with patch.object(settings, "get_settings", return_value=backend):
            # Act
            subject.set_host("localhost")

        # Assert
        backend.set.assert_called_once_with("/persistent/exts/lightspeed.trex.comfyui.core/host", "localhost")

    async def test_setter_propagates_observer_error_after_persisting(self):
        """A committed setting stays committed while its direct observer error remains visible."""
        # Arrange
        backend = MagicMock()
        backend.get_as_string.return_value = "old.example"
        callback = MagicMock(side_effect=RuntimeError("observer failed"))
        subject = ComfyUISettings(settings_changed_callback=callback)

        with patch.object(settings, "get_settings", return_value=backend):
            # Act
            with self.assertRaises(RuntimeError) as error_context:
                subject.set_host("new.example")

        # Assert
        self.assertEqual(str(error_context.exception), "observer failed")
        backend.set.assert_called_once_with("/persistent/exts/lightspeed.trex.comfyui.core/host", "new.example")
