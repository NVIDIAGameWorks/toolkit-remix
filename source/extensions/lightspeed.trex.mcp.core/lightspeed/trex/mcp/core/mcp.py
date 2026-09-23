"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["MCPCore"]

import asyncio
import concurrent.futures
import logging
import os
import socket
import subprocess
import sys
from functools import partial
from pathlib import Path

import carb
import fastmcp.server.openapi as fastmcp_openapi
import omni.usd
import uvicorn
from fastmcp import FastMCP
from fastmcp.utilities.openapi import format_description_with_responses, parse_openapi_to_http_routes
from omni.flux.utils.common.version import get_app_version
from omni.services.core import main

from . import discovery

# fastmcp narrates the conversion at INFO on stderr, which Kit stamps `[Error]` and the test
# harness fails the run over. At import, so a caller reaching `from_fastapi` directly is covered.
fastmcp_openapi.logger.setLevel(logging.WARNING)

_FALLBACK_PORT_RANGE = range(18014, 18020)
_PORT_SETTING_PATH = "/exts/lightspeed.trex.mcp.core/port"
_DEFAULT_TRANSPORT = "streamable-http"
# Mirrors the transports FastMCP's `http_app` accepts. Its other transport, stdio, binds the process's own
# stdin/stdout instead of returning an app to serve, so it cannot reach this Uvicorn path.
_SUPPORTED_HTTP_TRANSPORTS = ("streamable-http", "sse")

_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]

# Root-level endpoints that answer questions about the process, not the mod. Named explicitly
# because everything unnamed is kept.
_INFRASTRUCTURE_PATTERN = r"^/(health|healthz|livez|ready|readyz|startup|startupz|status|asyncapi)(/.*)?$"
_OPENAPI_METADATA_PATTERN = r"^/(openapi\.json|docs|redoc)/?$"
_UI_AUTOMATION_PATTERN = (
    r"^/(find_element|find_elements|widget_properties|windows|window_dimensions"
    r"|automation_sample_status|click|click_at|send_keys|drag_and_drop|scroll_frame"
    r"|set_color_widget|toggle_checkbox|set_widget_value)/?$"
)

# First match wins. Deny-list so a new route prefix becomes a tool without editing this extension.
# The TOOL catch-all is required, not cosmetic: fastmcp appends its own defaults after these and
# they send a bare GET to RESOURCE, which would drop every read operation from the manifest.
_CURATED_ROUTE_MAPS = [
    *(
        fastmcp_openapi.RouteMap(
            methods=_ALL_METHODS,
            pattern=pattern,
            route_type=fastmcp_openapi.RouteType.IGNORE,
        )
        for pattern in (_INFRASTRUCTURE_PATTERN, _OPENAPI_METADATA_PATTERN, _UI_AUTOMATION_PATTERN)
    ),
    # Everything else. Matches `main`, which sent every route to TOOL.
    fastmcp_openapi.RouteMap(
        methods=_ALL_METHODS,
        pattern=r".*",
        route_type=fastmcp_openapi.RouteType.TOOL,
    ),
]


async def _compact_tool_descriptions(mcp: FastMCP, spec: dict) -> None:
    """Omit duplicated input prose while preserving authored and response guidance."""
    tools = await mcp.get_tools()
    for route in parse_openapi_to_http_routes(spec):
        tool = tools.get(route.operation_id)
        if tool is None:
            continue
        # Body-wide guidance is not part of the input schema; property guidance already is.
        body = route.request_body.model_copy(update={"content_schema": {}}) if route.request_body else None
        # ponytail: reuse FastMCP's response formatting instead of parsing or summarizing Markdown.
        tool.description = format_description_with_responses(
            route.description or route.summary or f"Executes {route.method} {route.path}",
            route.responses,
            request_body=body,
        )


def _format_endpoint_host(host: str) -> str:
    """Format a connectable local URL host for the configured bind address."""
    host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    return f"[{host}]" if ":" in host else host


class _ServiceReadyServer(uvicorn.Server):
    """Publish the MCP readiness milestone after Uvicorn starts listening."""

    def __init__(self, config: uvicorn.Config, host: str, port: int, transport: str = "streamable-http") -> None:
        """Initialize the server with the endpoint reported at readiness."""
        super().__init__(config)
        self._host = host
        self._port = port
        self._transport = transport
        self._manifest_path: Path | None = None
        self._manifest: dict = {}

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        """Start listening and publish the service-ready timestamp."""
        await super().startup(sockets=sockets)
        if self.started and not self.should_exit:
            settings = carb.settings.get_settings()
            rest_host = settings.get("/exts/omni.services.transport.server.http/host") or "127.0.0.1"
            rest_port = settings.get_as_int("/exts/omni.services.transport.server.http/port")
            endpoint_host = _format_endpoint_host(self._host)
            rest_host = _format_endpoint_host(rest_host)
            endpoint_path = "/mcp/" if self._transport == "streamable-http" else "/sse"
            self._manifest = {
                "mcp_endpoint": f"http://{endpoint_host}:{self._port}{endpoint_path}",
                "rest_endpoint": f"http://{rest_host}:{rest_port}",
                "port": self._port,
                "rest_port": rest_port,
                "version": get_app_version(),
                "pid": os.getpid(),
            }
            try:
                self._manifest_path = discovery.publish_manifest(self._manifest)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                carb.log_warn(f"MCP discovery manifest could not be published: {exc}")
            carb.log_info(f"SERVICE_READY service=mcp host={self._host} port={self._port}")

    def remove_discovery_manifest(self) -> None:
        """Remove this server's discovery record without deleting a newer instance's record."""
        if self._manifest_path is None:
            return
        try:
            discovery.remove_manifest(self._manifest_path, self._manifest)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            carb.log_warn(f"MCP discovery manifest could not be removed: {exc}")
        else:
            self._manifest_path = None


class MCPCore:
    """Configure and manage the MCP server."""

    _initialization_task: asyncio.Task[None] | None = None
    _server: _ServiceReadyServer | None = None
    _shutdown_task: asyncio.Task[None] | None = None

    @classmethod
    def initialize(cls, mcp: FastMCP) -> None:
        """Schedule MCP server initialization."""
        settings = carb.settings.get_settings()

        # Use the MCP extension's own settings path
        host = settings.get("/exts/lightspeed.trex.mcp.core/host") or "127.0.0.1"
        port = settings.get_as_int("/exts/lightspeed.trex.mcp.core/port") or 18014
        allow_range = settings.get_as_bool("/exts/lightspeed.trex.mcp.core/allow_port_range")
        log_level = settings.get("/exts/lightspeed.trex.mcp.core/log_level") or "warning"
        transport = settings.get("/exts/lightspeed.trex.mcp.core/transport") or _DEFAULT_TRANSPORT

        if transport not in _SUPPORTED_HTTP_TRANSPORTS:
            carb.log_warn(
                f"MCP server transport '{transport}' is not supported, starting with '{_DEFAULT_TRANSPORT}' instead"
            )
            transport = _DEFAULT_TRANSPORT

        cls._initialization_task = asyncio.ensure_future(
            cls._initialize_async(mcp, host, port, allow_range, log_level, transport=transport)
        )

    @classmethod
    def shutdown(cls) -> asyncio.Task[None] | None:
        """Schedule MCP server shutdown and return the owned task."""
        if cls._shutdown_task is not None:
            return cls._shutdown_task
        if cls._initialization_task is None:
            return None

        # Kit may stop pumping the event loop before the asynchronous shutdown finishes.
        if cls._server is not None:
            cls._server.should_exit = True
            cls._server.remove_discovery_manifest()
        cls._shutdown_task = asyncio.ensure_future(cls._shutdown_async())
        return cls._shutdown_task

    @classmethod
    async def _shutdown_async(cls) -> None:
        """Stop initialization or let Uvicorn close its active connections."""
        initialization_task = cls._initialization_task
        server = cls._server
        if initialization_task is None:
            return

        if server is None:
            initialization_task.cancel()
        else:
            server.should_exit = True

        try:
            await initialization_task
        except asyncio.CancelledError:
            pass
        finally:
            if cls._initialization_task is initialization_task:
                cls._initialization_task = None
            if cls._server is server:
                cls._server = None
            cls._shutdown_task = None

    @classmethod
    async def _run_mcp_server(cls, mcp: FastMCP, host: str, port: int, log_level: str, transport: str) -> None:
        """Run and retain the Uvicorn server until it shuts down."""
        config = uvicorn.Config(
            mcp.http_app(transport=transport),
            host=host,
            port=port,
            log_level=log_level,
            lifespan="on",
            timeout_graceful_shutdown=1,
        )
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        server_socket = socket.socket(family=family)
        # Windows SO_REUSEADDR allows another listener to share this endpoint instead of triggering fallback.
        socket_option = socket.SO_EXCLUSIVEADDRUSE if sys.platform == "win32" else socket.SO_REUSEADDR
        server_socket.setsockopt(socket.SOL_SOCKET, socket_option, 1)
        server = _ServiceReadyServer(config, host, port, transport)
        cls._server = server
        try:
            server_socket.bind((host, port))
            await server.serve(sockets=[server_socket])
        finally:
            server.remove_discovery_manifest()
            server_socket.close()
            if cls._server is server:
                cls._server = None

    @classmethod
    @omni.usd.handle_exception
    async def _initialize_async(
        cls, mcp: FastMCP, host: str, port: int, allow_range: bool, log_level: str, transport: str
    ) -> None:
        """Initialize the configured MCP server asynchronously."""
        loop = asyncio.get_event_loop()
        endpoint_host = _format_endpoint_host(host)
        endpoint_path = "/mcp/" if transport == "streamable-http" else "/sse"
        with concurrent.futures.ThreadPoolExecutor() as pool:
            # Mount the REST API MCP server
            app = main.get_app()
            rest_api_mcp = await loop.run_in_executor(
                pool,
                partial(
                    FastMCP.from_fastapi,
                    app,
                    route_maps=_CURATED_ROUTE_MAPS,
                ),
            )
            await _compact_tool_descriptions(rest_api_mcp, app.openapi())
            mcp.mount("remix", rest_api_mcp)

            ports = [port]
            if allow_range:
                ports.extend(candidate for candidate in _FALLBACK_PORT_RANGE if candidate != port)
            for attempt, candidate_port in enumerate(ports):
                try:
                    # Run the MCP server with the configured transport, host, and port
                    await cls._run_mcp_server(mcp, host, candidate_port, log_level, transport)
                    break
                except (OSError, SystemExit) as exc:
                    if attempt == len(ports) - 1:
                        carb.log_error(f"MCP server failed to start on {host}; exhausted ports {ports}: {exc}")
                        return

                    next_port = ports[attempt + 1]
                    carb.log_warn(
                        f"MCP_PORT_FALLBACK requested_port={candidate_port} selected_port={next_port} "
                        f"endpoint=http://{endpoint_host}:{next_port}{endpoint_path}; retrying after bind failure"
                    )
                    carb.settings.get_settings().set(_PORT_SETTING_PATH, next_port)
