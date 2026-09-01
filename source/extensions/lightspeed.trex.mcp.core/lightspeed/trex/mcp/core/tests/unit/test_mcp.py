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

__all__ = ("TestMCPCore",)

import asyncio
import contextlib
import socket
from unittest import mock

import omni.kit.test
from fastmcp import FastMCP

from lightspeed.trex.mcp.core import mcp as mcp_module


class TestMCPCore(omni.kit.test.AsyncTestCase):
    """Test MCP server initialization behavior."""

    async def setUp(self) -> None:
        """Stop any server initialization retained by the loaded extension."""
        shutdown_task = mcp_module.MCPCore.shutdown()
        if shutdown_task is not None:
            await shutdown_task

    async def tearDown(self) -> None:
        """Stop the server initialization started by the current test."""
        shutdown_task = mcp_module.MCPCore.shutdown()
        if shutdown_task is not None:
            await shutdown_task

    async def __wait_for_port(self, host: str, port: int):
        for _ in range(100):
            try:
                _reader, writer = await asyncio.open_connection(host, port)
                writer.close()
                await writer.wait_closed()
                return
            except OSError:
                await asyncio.sleep(0.05)
        self.fail(f"Timed out waiting for MCP server on {host}:{port}")

    async def __initialize_with_mocks(
        self,
        run_mcp_server_mock,
        settings,
        allow_range=True,
        validate_port_side_effect=None,
        transport="streamable-http",
    ):
        mcp = mock.Mock()
        rest_api_mcp = mock.Mock()
        with (
            mock.patch.object(
                mcp_module.utils,
                "validate_port",
                side_effect=validate_port_side_effect or [8000],
            ),
            mock.patch.object(mcp_module.carb.settings, "get_settings", return_value=settings),
            mock.patch.object(mcp_module.main, "get_app", return_value=mock.Mock()),
            mock.patch.object(mcp_module.FastMCP, "from_fastapi", return_value=rest_api_mcp),
            mock.patch.object(mcp_module.MCPPrompts, "register_prompts"),
            mock.patch.object(mcp_module.MCPCore, "_run_mcp_server", run_mcp_server_mock),
        ):
            await mcp_module.MCPCore._initialize_async(mcp, "127.0.0.1", 8000, allow_range, "warning", transport)

    async def test_initialize_when_mcp_server_bind_fails_retries_with_available_port(self):
        # Arrange
        run_mcp_server_mock = mock.AsyncMock(side_effect=[OSError("Port already in use"), None])
        settings = mock.Mock()

        # Act
        await self.__initialize_with_mocks(run_mcp_server_mock, settings, validate_port_side_effect=[8000, 8001])

        # Assert
        self.assertEqual(run_mcp_server_mock.await_count, 2)
        self.assertEqual(run_mcp_server_mock.await_args_list[0].args[2], 8000)
        self.assertEqual(run_mcp_server_mock.await_args_list[1].args[2], 8001)
        settings.set.assert_called_once_with("/exts/lightspeed.trex.mcp.core/port", 8001)

    async def test_initialize_when_port_is_taken_starts_same_mcp_server_on_retry_port(self):
        # Arrange
        host = "127.0.0.1"
        collision_socket = socket.socket()
        collision_socket.bind((host, 0))
        collision_socket.listen()
        collision_port = collision_socket.getsockname()[1]
        with socket.socket() as retry_port_socket:
            retry_port_socket.bind((host, 0))
            retry_port = retry_port_socket.getsockname()[1]

        mcp = FastMCP("Test MCP port collision")
        settings = mock.Mock()
        servers = []
        server_factory = mcp_module._ServiceReadyServer

        def create_server(config, server_host, server_port):
            server = server_factory(config, server_host, server_port)
            servers.append(server)
            return server

        initialize_task = None
        try:
            with (
                mock.patch.object(
                    mcp_module.utils,
                    "validate_port",
                    side_effect=[collision_port, retry_port],
                ),
                mock.patch.object(mcp_module.carb.settings, "get_settings", return_value=settings),
                mock.patch.object(mcp_module.main, "get_app", return_value=mock.Mock()),
                mock.patch.object(mcp_module.FastMCP, "from_fastapi", return_value=mock.Mock()),
                mock.patch.object(mcp_module.MCPPrompts, "register_prompts"),
                mock.patch.object(mcp_module, "_ServiceReadyServer", side_effect=create_server),
                mock.patch.object(mcp_module.carb, "log_info") as log_info_mock,
            ):
                # Act
                initialize_task = asyncio.create_task(
                    mcp_module.MCPCore._initialize_async(
                        mcp,
                        host,
                        collision_port,
                        allow_range=True,
                        log_level="critical",
                        transport="streamable-http",
                    )
                )
                await self.__wait_for_port(host, retry_port)

            # Assert
            self.assertFalse(initialize_task.done(), "Expected the same FastMCP server to be running on the retry port")
            settings.set.assert_called_once_with("/exts/lightspeed.trex.mcp.core/port", retry_port)
            log_info_mock.assert_any_call(f"SERVICE_READY service=mcp host={host} port={retry_port}")
        finally:
            collision_socket.close()
            if initialize_task is not None:
                for server in servers:
                    server.should_exit = True
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait_for(initialize_task, timeout=5)

    async def test_initialize_when_mcp_server_bind_fails_without_port_range_returns(self):
        # Arrange
        run_mcp_server_mock = mock.AsyncMock(side_effect=OSError("Port already in use"))
        settings = mock.Mock()

        with mock.patch.object(mcp_module.carb, "log_error") as log_error_mock:
            # Act
            await self.__initialize_with_mocks(run_mcp_server_mock, settings, allow_range=False)

        # Assert
        run_mcp_server_mock.assert_awaited_once()
        settings.set.assert_not_called()
        log_error_mock.assert_called_once()

    async def test_initialize_when_mcp_server_retry_bind_fails_returns(self):
        # Arrange
        run_mcp_server_mock = mock.AsyncMock(side_effect=OSError("Port already in use"))
        settings = mock.Mock()

        with mock.patch.object(mcp_module.carb, "log_error") as log_error_mock:
            # Act
            await self.__initialize_with_mocks(run_mcp_server_mock, settings, validate_port_side_effect=[8000, 8001])

        # Assert
        self.assertEqual(run_mcp_server_mock.await_count, 2)
        settings.set.assert_called_once_with("/exts/lightspeed.trex.mcp.core/port", 8001)
        log_error_mock.assert_called_once()

    async def test_run_mcp_server_builds_app_with_configured_transport(self) -> None:
        """Build the Uvicorn app with the transport the settings selected."""
        # Arrange
        host = "127.0.0.1"
        with socket.socket() as available_port_socket:
            available_port_socket.bind((host, 0))
            port = available_port_socket.getsockname()[1]

        mcp = mock.Mock()
        server = mock.Mock()
        server.serve = mock.AsyncMock()

        # Act
        with mock.patch.object(mcp_module, "_ServiceReadyServer", return_value=server):
            await mcp_module.MCPCore._run_mcp_server(mcp, host, port, "critical", "streamable-http")

        # Assert
        mcp.http_app.assert_called_once_with(transport="streamable-http")

    async def test_initialize_when_transport_is_unsupported_uses_default_transport(self) -> None:
        """Fall back to the default transport when the configured transport is not supported."""
        # Arrange
        settings = mock.Mock()
        settings.get.side_effect = {
            "/exts/lightspeed.trex.mcp.core/host": "127.0.0.1",
            "/exts/lightspeed.trex.mcp.core/log_level": "critical",
            "/exts/lightspeed.trex.mcp.core/transport": "websocket",
        }.get
        settings.get_as_int.return_value = 8000
        settings.get_as_bool.return_value = False
        transports = []

        async def record_transport(*_args: object, **kwargs: object) -> None:
            """Record the transport the initialization task was given."""
            transports.append(kwargs["transport"])

        with (
            mock.patch.object(mcp_module.carb.settings, "get_settings", return_value=settings),
            mock.patch.object(mcp_module.MCPCore, "_initialize_async", side_effect=record_transport),
            mock.patch.object(mcp_module.carb, "log_warn") as log_warn_mock,
        ):
            # Act
            mcp_module.MCPCore.initialize(mock.Mock())
            await mcp_module.MCPCore._initialization_task

        # Assert
        self.assertEqual(transports, ["streamable-http"])
        log_warn_mock.assert_called_once()

    async def test_shutdown_with_active_client_closes_connection_and_settles_server(self) -> None:
        """Close active clients before completing MCP server shutdown."""
        # Arrange
        host = "127.0.0.1"
        with socket.socket() as available_port_socket:
            available_port_socket.bind((host, 0))
            port = available_port_socket.getsockname()[1]

        initialization_task = asyncio.create_task(
            mcp_module.MCPCore._run_mcp_server(
                FastMCP("Active client shutdown test"), host, port, "critical", "streamable-http"
            )
        )
        mcp_module.MCPCore._initialization_task = initialization_task
        client_writer = None

        try:
            await self.__wait_for_port(host, port)
            client_reader, client_writer = await asyncio.open_connection(host, port)

            # Act
            shutdown_task = mcp_module.MCPCore.shutdown()
            await asyncio.wait_for(shutdown_task, timeout=5)

            # Assert
            self.assertEqual(await asyncio.wait_for(client_reader.read(1), timeout=5), b"")
            self.assertTrue(initialization_task.done())
            self.assertFalse(initialization_task.cancelled())
        finally:
            if client_writer is not None:
                client_writer.close()
                await client_writer.wait_closed()
            if not initialization_task.done():
                initialization_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await initialization_task

    async def test_shutdown_when_initialization_task_is_pending_cancels_task(self) -> None:
        """Cancel the retained initialization task when MCP shuts down."""
        # Arrange
        initialization_started = asyncio.Event()
        never_finish = asyncio.Event()

        async def wait_for_shutdown(*_args: object, **_kwargs: object) -> None:
            """Wait until the initialization task is cancelled."""
            initialization_started.set()
            await never_finish.wait()

        with mock.patch.object(mcp_module.MCPCore, "_initialize_async", side_effect=wait_for_shutdown):
            mcp_module.MCPCore.initialize(mock.Mock())
            initialization_task = mcp_module.MCPCore._initialization_task
            await initialization_started.wait()

            # Act
            shutdown_task = mcp_module.MCPCore.shutdown()
            await shutdown_task

        # Assert
        self.assertIsNone(mcp_module.MCPCore._initialization_task)
        self.assertTrue(initialization_task.done())
        self.assertTrue(initialization_task.cancelled())
