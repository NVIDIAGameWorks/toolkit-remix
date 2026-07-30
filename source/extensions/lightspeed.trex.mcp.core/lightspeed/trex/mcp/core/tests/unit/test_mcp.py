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
            mock.patch.object(mcp_module, "_run_mcp_server", run_mcp_server_mock),
        ):
            await mcp_module.MCPCore._initialize_async(mcp, "127.0.0.1", 8000, allow_range, "warning")

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
        server_factory = mcp_module.uvicorn.Server

        def create_server(config):
            server = server_factory(config)
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
                mock.patch.object(mcp_module.uvicorn, "Server", side_effect=create_server),
            ):
                # Act
                initialize_task = asyncio.create_task(
                    mcp_module.MCPCore._initialize_async(
                        mcp,
                        host,
                        collision_port,
                        allow_range=True,
                        log_level="critical",
                    )
                )
                await self.__wait_for_port(host, retry_port)

            # Assert
            self.assertFalse(initialize_task.done(), "Expected the same FastMCP server to be running on the retry port")
            settings.set.assert_called_once_with("/exts/lightspeed.trex.mcp.core/port", retry_port)
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
