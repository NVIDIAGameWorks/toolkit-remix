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

__all__ = ("TestMCPCoreExtension",)

from unittest import mock

import omni.kit.app
import omni.kit.test

from lightspeed.trex.mcp.core import extension as extension_module


class TestMCPCoreExtension(omni.kit.test.AsyncTestCase):
    """Test MCP extension lifecycle behavior."""

    async def setUp(self) -> None:
        """Reset the MCP instance before each test."""
        shutdown_task = extension_module.MCPCore.shutdown()
        if shutdown_task is not None:
            await shutdown_task
        extension_module._instance = None

    async def tearDown(self) -> None:
        """Reset the MCP instance after each test."""
        shutdown_task = extension_module.MCPCore.shutdown()
        if shutdown_task is not None:
            await shutdown_task
        extension_module._instance = None

    async def test_on_startup_when_app_is_ready_initializes_mcp_server(self) -> None:
        """Initialize the MCP server immediately when the application is ready."""
        # Arrange
        app = mock.Mock()
        app.is_app_ready.return_value = True
        mcp_server = mock.Mock()
        extension = extension_module.MCPCoreExtension()

        with (
            mock.patch.object(extension_module.omni.kit.app, "get_app", return_value=app),
            mock.patch.object(extension_module, "FastMCP", return_value=mcp_server),
            mock.patch.object(extension_module.MCPCore, "initialize") as initialize_mock,
        ):
            # Act
            extension.on_startup("lightspeed.trex.mcp.core")

        # Assert
        initialize_mock.assert_called_once_with(mcp_server)

    async def test_on_startup_when_app_is_not_ready_retains_app_ready_subscription(self) -> None:
        """Retain the ready subscription until Kit dispatches the ready event."""
        # Arrange
        app = mock.Mock()
        app.is_app_ready.return_value = False
        startup_event_stream = mock.Mock()
        subscription = mock.Mock()
        app.get_startup_event_stream.return_value = startup_event_stream
        startup_event_stream.create_subscription_to_pop_by_type.return_value = subscription
        extension = extension_module.MCPCoreExtension()

        with mock.patch.object(extension_module.omni.kit.app, "get_app", return_value=app):
            # Act
            extension.on_startup("lightspeed.trex.mcp.core")

        # Assert
        startup_event_stream.create_subscription_to_pop_by_type.assert_called_once_with(
            omni.kit.app.EVENT_APP_READY,
            extension._on_app_ready,
            name="MCP Server App Ready",
        )
        self.assertIs(extension._app_ready_subscription, subscription)

    async def test_on_app_ready_initializes_mcp_server_once(self) -> None:
        """Initialize the MCP server once when Kit dispatches the ready event."""
        # Arrange
        mcp_server = mock.Mock()
        extension = extension_module.MCPCoreExtension()
        extension._app_ready_subscription = mock.Mock()

        with (
            mock.patch.object(extension_module, "FastMCP", return_value=mcp_server),
            mock.patch.object(extension_module.MCPCore, "initialize") as initialize_mock,
        ):
            # Act
            extension._on_app_ready(mock.Mock())

        # Assert
        initialize_mock.assert_called_once_with(mcp_server)
        self.assertIsNone(extension._app_ready_subscription)

    async def test_on_app_ready_after_shutdown_does_not_initialize_mcp_server(self) -> None:
        """Ignore an already-queued ready event after extension shutdown."""
        # Arrange
        extension = extension_module.MCPCoreExtension()
        extension._app_ready_subscription = mock.Mock()

        with mock.patch.object(extension_module.MCPCore, "initialize") as initialize_mock:
            extension.on_shutdown()

            # Act
            extension._on_app_ready(mock.Mock())

        # Assert
        initialize_mock.assert_not_called()
