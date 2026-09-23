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
import os
import socket
from copy import deepcopy
from pathlib import Path as FilePath
from unittest import mock

import omni.kit.test
from fastapi import FastAPI, Path, Query
from fastmcp import FastMCP
from pydantic import BaseModel, Field

from lightspeed.trex.mcp.core import mcp as mcp_module


class TestMCPCore(omni.kit.test.AsyncTestCase):
    """Test MCP server initialization behavior."""

    async def setUp(self) -> None:
        """Stop any server initialization retained by the loaded extension."""
        shutdown_task = mcp_module.MCPCore.shutdown()
        if shutdown_task is not None:
            await shutdown_task
        publish_patch = mock.patch.object(mcp_module.discovery, "publish_manifest", return_value=FilePath("mcp.json"))
        remove_patch = mock.patch.object(mcp_module.discovery, "remove_manifest")
        self._publish_manifest = publish_patch.start()
        self._remove_manifest = remove_patch.start()
        self.addCleanup(publish_patch.stop)
        self.addCleanup(remove_patch.stop)

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
        port=18014,
        transport="streamable-http",
        host="127.0.0.1",
    ):
        mcp = mock.Mock()
        rest_api_mcp = mock.Mock()
        with (
            mock.patch.object(mcp_module.carb.settings, "get_settings", return_value=settings),
            mock.patch.object(mcp_module.main, "get_app", return_value=mock.Mock()),
            mock.patch.object(mcp_module.FastMCP, "from_fastapi", return_value=rest_api_mcp),
            mock.patch.object(mcp_module, "_compact_tool_descriptions", new_callable=mock.AsyncMock),
            mock.patch.object(mcp_module.MCPCore, "_run_mcp_server", run_mcp_server_mock),
        ):
            await mcp_module.MCPCore._initialize_async(mcp, host, port, allow_range, "warning", transport)

    async def test_compact_descriptions_removes_only_generated_input_prose(self) -> None:
        """Preserve authored guidance, responses and schemas while omitting repeated inputs."""

        # Arrange
        class ModelUpdate(BaseModel):
            """Describe the model replacement request."""

            title: str = Field(description="Replacement model title.")

        authored = (
            "Replace the model.\n\n**Path Parameters:** Keep this authored path guidance."
            "\n\n**Query Parameters:** Keep this authored query guidance."
            "\n\n**Request Properties:** Keep this authored body guidance."
            "\n\n**Responses:** Keep this authored response guidance."
        )
        app = FastAPI()

        @app.post(
            "/stagecraft/models/{model_id}",
            operation_id="update_model",
            description=authored,
            openapi_extra={"requestBody": {"description": "Load the capture before replacing its model."}},
        )
        async def update_model(
            payload: ModelUpdate,
            model_id: str = Path(..., description="Model prim path."),
            overwrite: bool = Query(False, description="Replace an existing model."),
        ) -> ModelUpdate:
            """Return the requested model for this isolated conversion fixture."""
            del model_id, overwrite
            return payload

        @app.get("/health", operation_id="health")
        async def health() -> dict:
            """Return health without exposing an MCP tool."""
            return {"ready": True}

        mcp = FastMCP.from_fastapi(app, route_maps=mcp_module._CURATED_ROUTE_MAPS)
        tools = await mcp.get_tools()
        description_before = tools["update_model"].description
        parameters_before = deepcopy(tools["update_model"].parameters)
        spec_before = deepcopy(app.openapi())

        # Act
        await mcp_module._compact_tool_descriptions(mcp, app.openapi())

        # Assert
        description = tools["update_model"].description
        self.assertEqual(set(tools), {"update_model"})
        self.assertTrue(description.startswith(authored))
        for heading in ("**Path Parameters:**", "**Query Parameters:**", "**Request Properties:**"):
            self.assertEqual(description_before.count(heading), 2)
            self.assertEqual(description.count(heading), 1)
        self.assertIn("Load the capture before replacing its model. (Required)", description)
        self.assertEqual(description.rsplit("**Responses:**", 1)[1], description_before.rsplit("**Responses:**", 1)[1])
        self.assertEqual(tools["update_model"].parameters, parameters_before)
        self.assertIn("title", parameters_before["properties"])
        self.assertIn("title", parameters_before["required"])
        self.assertEqual(app.openapi(), spec_before)

    async def test_initialize_when_bind_retry_changes_port_warns_with_discoverable_endpoint(self) -> None:
        """Publish the retry endpoint after the requested port fails to bind."""
        for host, transport, endpoint in (
            ("127.0.0.1", "streamable-http", "http://127.0.0.1:18015/mcp/"),
            ("127.0.0.1", "sse", "http://127.0.0.1:18015/sse"),
            ("::1", "streamable-http", "http://[::1]:18015/mcp/"),
            ("::1", "sse", "http://[::1]:18015/sse"),
            ("0.0.0.0", "streamable-http", "http://127.0.0.1:18015/mcp/"),
            ("0.0.0.0", "sse", "http://127.0.0.1:18015/sse"),
            ("::", "streamable-http", "http://[::1]:18015/mcp/"),
            ("::", "sse", "http://[::1]:18015/sse"),
        ):
            with self.subTest(title=f"host={host}, transport={transport}"):
                # Arrange
                run_mcp_server_mock = mock.AsyncMock(side_effect=[OSError("Port already in use"), None])
                settings = mock.Mock()
                with mock.patch.object(mcp_module.carb, "log_warn") as log_warn_mock:
                    # Act
                    await self.__initialize_with_mocks(
                        run_mcp_server_mock,
                        settings,
                        transport=transport,
                        host=host,
                    )

                # Assert
                log_warn_mock.assert_called_once_with(
                    "MCP_PORT_FALLBACK requested_port=18014 selected_port=18015 "
                    f"endpoint={endpoint}; retrying after bind failure"
                )
                settings.set.assert_called_once_with("/exts/lightspeed.trex.mcp.core/port", 18015)
                self.assertEqual(run_mcp_server_mock.await_args.args[1], host)
                self.assertEqual(run_mcp_server_mock.await_args.args[2], 18015)

    async def test_initialize_when_preferred_port_is_available_does_not_try_fallback(self) -> None:
        """Keep the configured port when its first bind succeeds."""
        # Arrange
        run_mcp_server_mock = mock.AsyncMock()
        settings = mock.Mock()

        # Act
        await self.__initialize_with_mocks(run_mcp_server_mock, settings)

        # Assert
        run_mcp_server_mock.assert_awaited_once()
        self.assertEqual(run_mcp_server_mock.await_args.args[2], 18014)
        settings.set.assert_not_called()

    async def test_initialize_when_only_last_port_is_available_starts_on_18019(self) -> None:
        """Try every allowed fallback through the inclusive upper bound."""
        # Arrange
        run_mcp_server_mock = mock.AsyncMock(side_effect=[OSError("Port already in use")] * 5 + [None])
        settings = mock.Mock()

        # Act
        await self.__initialize_with_mocks(run_mcp_server_mock, settings)

        # Assert
        self.assertEqual([call.args[2] for call in run_mcp_server_mock.await_args_list], list(range(18014, 18020)))
        self.assertEqual(settings.set.call_args, mock.call("/exts/lightspeed.trex.mcp.core/port", 18019))

    async def test_initialize_when_port_is_taken_starts_same_mcp_server_on_retry_port(self):
        """Retry when an existing listener allows address reuse."""
        # Arrange
        host = "127.0.0.1"
        collision_socket = socket.socket()
        collision_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        collision_socket.bind((host, 0))
        collision_socket.listen()
        collision_port = collision_socket.getsockname()[1]
        with socket.socket() as retry_port_socket:
            retry_port_socket.bind((host, 0))
            retry_port = retry_port_socket.getsockname()[1]

        mcp = FastMCP("Test MCP port collision")
        settings = mock.Mock()
        settings.get.return_value = host
        settings.get_as_int.return_value = 8017
        servers = []
        server_factory = mcp_module._ServiceReadyServer

        def create_server(config, server_host, server_port, transport):
            server = server_factory(config, server_host, server_port, transport)
            servers.append(server)
            return server

        initialize_task = None
        try:
            with (
                mock.patch.object(mcp_module, "_FALLBACK_PORT_RANGE", [retry_port]),
                mock.patch.object(mcp_module.carb.settings, "get_settings", return_value=settings),
                mock.patch.object(mcp_module.main, "get_app", return_value=mock.Mock()),
                mock.patch.object(mcp_module.FastMCP, "from_fastapi", return_value=mock.Mock()),
                mock.patch.object(mcp_module, "_compact_tool_descriptions", new_callable=mock.AsyncMock),
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
                await asyncio.wait_for(self.__wait_for_port(host, retry_port), timeout=5)

            # Assert
            self.assertFalse(initialize_task.done(), "Expected the same FastMCP server to be running on the retry port")
            settings.set.assert_called_once_with("/exts/lightspeed.trex.mcp.core/port", retry_port)
            log_info_mock.assert_any_call(f"SERVICE_READY service=mcp host={host} port={retry_port}")
            self._publish_manifest.assert_called_once()
            manifest = self._publish_manifest.call_args.args[0]
            self.assertEqual(manifest["port"], retry_port)
            self.assertEqual(manifest["mcp_endpoint"], f"http://{host}:{retry_port}/mcp/")
            self.assertEqual(manifest["rest_port"], 8017)
        finally:
            collision_socket.close()
            if initialize_task is not None:
                for server in servers:
                    server.should_exit = True
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait_for(initialize_task, timeout=5)

    async def test_initialize_when_mcp_server_bind_fails_without_port_range_returns(self) -> None:
        """Stop after the preferred port fails when fallback is disabled."""
        for preferred_port in (18014, 19000):
            with self.subTest(title=f"preferred_port={preferred_port}"):
                # Arrange
                run_mcp_server_mock = mock.AsyncMock(side_effect=OSError("Port already in use"))
                settings = mock.Mock()

                with mock.patch.object(mcp_module.carb, "log_error") as log_error_mock:
                    # Act
                    await self.__initialize_with_mocks(
                        run_mcp_server_mock, settings, allow_range=False, port=preferred_port
                    )

                # Assert
                run_mcp_server_mock.assert_awaited_once()
                self.assertEqual(run_mcp_server_mock.await_args.args[2], preferred_port)
                settings.set.assert_not_called()
                log_error_mock.assert_called_once()

    async def test_initialize_when_all_range_ports_are_busy_stops_after_18019(self) -> None:
        """Report exhaustion without attempting a port outside the configured range."""
        # Arrange
        run_mcp_server_mock = mock.AsyncMock(side_effect=OSError("Port already in use"))
        settings = mock.Mock()

        with mock.patch.object(mcp_module.carb, "log_error") as log_error_mock:
            # Act
            await self.__initialize_with_mocks(run_mcp_server_mock, settings)

        # Assert
        self.assertEqual([call.args[2] for call in run_mcp_server_mock.await_args_list], list(range(18014, 18020)))
        self.assertEqual(settings.set.call_count, 5)
        log_error_mock.assert_called_once()
        for port in range(18014, 18020):
            self.assertIn(str(port), log_error_mock.call_args.args[0])

    async def test_initialize_when_custom_preferred_port_is_busy_tries_range_without_duplicates(self) -> None:
        """Honor an explicit preferred port before the bounded shared fallback range."""
        for preferred_port in (18015, 19000):
            with self.subTest(title=f"preferred_port={preferred_port}"):
                # Arrange
                run_mcp_server_mock = mock.AsyncMock(side_effect=OSError("Port already in use"))
                settings = mock.Mock()
                with mock.patch.object(mcp_module.carb, "log_error"):
                    # Act
                    await self.__initialize_with_mocks(run_mcp_server_mock, settings, port=preferred_port)

                # Assert
                attempts = [call.args[2] for call in run_mcp_server_mock.await_args_list]
                self.assertEqual(attempts[0], preferred_port)
                self.assertEqual(len(attempts), len(set(attempts)))
                self.assertEqual(attempts[1:], [port for port in range(18014, 18020) if port != preferred_port])

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

    async def test_initialize_when_port_is_unset_uses_18014(self) -> None:
        """Use the published preferred port when no port setting is available."""
        # Arrange
        settings = mock.Mock()
        settings.get.return_value = None
        settings.get_as_int.return_value = 0
        settings.get_as_bool.return_value = True
        with (
            mock.patch.object(mcp_module.carb.settings, "get_settings", return_value=settings),
            mock.patch.object(mcp_module.MCPCore, "_initialize_async", new_callable=mock.AsyncMock) as initialize_mock,
        ):
            # Act
            mcp_module.MCPCore.initialize(mock.Mock())
            await mcp_module.MCPCore._initialization_task

        # Assert
        initialize_mock.assert_awaited_once()
        self.assertEqual(initialize_mock.await_args.args[2], 18014)

    async def test_startup_when_listening_publishes_runtime_discovery_fields(self) -> None:
        """Publish bound ports, transport, process and Toolkit version after readiness."""
        for host, rest_host, transport, endpoint, rest_endpoint in (
            ("127.0.0.1", "::1", "streamable-http", "http://127.0.0.1:18015/mcp/", "http://[::1]:8099"),
            ("::1", "127.0.0.1", "sse", "http://[::1]:18015/sse", "http://127.0.0.1:8099"),
            ("0.0.0.0", "::", "streamable-http", "http://127.0.0.1:18015/mcp/", "http://[::1]:8099"),
            ("::", "0.0.0.0", "sse", "http://[::1]:18015/sse", "http://127.0.0.1:8099"),
        ):
            with self.subTest(title=f"host={host}, rest_host={rest_host}, transport={transport}"):
                # Arrange
                server = mcp_module._ServiceReadyServer(mock.Mock(), host, 18015, transport)
                server.started = True
                settings = mock.Mock()
                settings.get.return_value = rest_host
                settings.get_as_int.return_value = 8099
                self._publish_manifest.reset_mock()
                with (
                    mock.patch.object(mcp_module.uvicorn.Server, "startup", new_callable=mock.AsyncMock),
                    mock.patch.object(mcp_module.carb.settings, "get_settings", return_value=settings),
                    mock.patch.object(mcp_module, "get_app_version", return_value="1.29.0"),
                ):
                    # Act
                    await server.startup()

                # Assert
                self._publish_manifest.assert_called_once_with(
                    {
                        "mcp_endpoint": endpoint,
                        "rest_endpoint": rest_endpoint,
                        "port": 18015,
                        "rest_port": 8099,
                        "version": "1.29.0",
                        "pid": os.getpid(),
                    }
                )

    async def test_startup_when_not_listening_does_not_publish_manifest(self) -> None:
        """Avoid advertising a server whose startup did not complete."""
        # Arrange
        server = mcp_module._ServiceReadyServer(mock.Mock(), "127.0.0.1", 18014)
        server.should_exit = True
        with mock.patch.object(mcp_module.uvicorn.Server, "startup", new_callable=mock.AsyncMock):
            # Act
            await server.startup()

        # Assert
        self._publish_manifest.assert_not_called()

    async def test_startup_when_manifest_write_fails_keeps_server_ready(self) -> None:
        """Report discovery failure without changing a successfully bound endpoint."""
        # Arrange
        server = mcp_module._ServiceReadyServer(mock.Mock(), "127.0.0.1", 18014)
        server.started = True
        self._publish_manifest.side_effect = PermissionError("ACL denied")
        with (
            mock.patch.object(mcp_module.uvicorn.Server, "startup", new_callable=mock.AsyncMock),
            mock.patch.object(mcp_module.carb, "log_warn") as log_warn,
            mock.patch.object(mcp_module.carb, "log_info") as log_info,
        ):
            # Act
            await server.startup()

        # Assert
        self.assertFalse(server.should_exit)
        log_warn.assert_called_once()
        log_info.assert_called_once_with("SERVICE_READY service=mcp host=127.0.0.1 port=18014")

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
            self._remove_manifest.assert_called_once()
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
