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
from functools import partial

import carb
import fastmcp.server.openapi as fastmcp_openapi
import omni.usd
from fastmcp import FastMCP
from omni.services.core import main
from omni.services.transport.server.base import utils

from .prompts import MCPPrompts


class MCPCore:
    @classmethod
    def initialize(cls, mcp: FastMCP):
        settings = carb.settings.get_settings()

        # Use the MCP extension's own settings path
        host = settings.get("/exts/lightspeed.trex.mcp.core/host") or "127.0.0.1"
        port = settings.get_as_int("/exts/lightspeed.trex.mcp.core/port") or 8000
        allow_range = settings.get_as_bool("/exts/lightspeed.trex.mcp.core/allow_port_range")
        log_level = settings.get("/exts/lightspeed.trex.mcp.core/log_level") or "warning"

        asyncio.ensure_future(cls._initialize_async(mcp, host, port, allow_range, log_level))

    @classmethod
    @omni.usd.handle_exception
    async def _initialize_async(cls, mcp: FastMCP, host: str, port: int, allow_range: bool, log_level: str):
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            # Check if port is available before doing any setup
            validated_port = await loop.run_in_executor(
                pool, partial(utils.validate_port, port, allow_range=allow_range)
            )

            if validated_port != port:
                carb.log_warn(
                    f"MCP server was meant to start on {port} but port is taken, "
                    f"starting on port {validated_port} instead"
                )
                carb.settings.get_settings().set("/exts/lightspeed.trex.mcp.core/port", validated_port)
                port = validated_port

            # Update the log level for the openapi module to avoid printing the startup message
            fastmcp_openapi.logger.setLevel(logging.WARNING)

            # Mount the REST API MCP server
            rest_api_mcp = await loop.run_in_executor(
                pool,
                partial(
                    FastMCP.from_fastapi,
                    main.get_app(),
                    route_maps=[
                        fastmcp_openapi.RouteMap(
                            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
                            pattern=r".*",
                            route_type=fastmcp_openapi.RouteType.TOOL,
                        ),
                    ],
                ),
            )
            mcp.mount("remix", rest_api_mcp)

            MCPPrompts.register_prompts(mcp)

            # Run the MCP server in SSE mode with configured host and port
            await mcp.run_async(transport="sse", host=host, port=port, log_level=log_level)

        carb.log_info(f"MCP server initialized on {host}:{port}")
