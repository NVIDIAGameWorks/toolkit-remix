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

from fastmcp import FastMCP
from fastmcp.server.openapi import RouteMap, RouteType
from omni.services.core import main

from .prompts import MCPPrompts


class MCPCore:
    @classmethod
    def initialize(cls, mcp: FastMCP):
        # Mount the REST API MCP server
        rest_api_mcp = FastMCP.from_fastapi(
            main.get_app(),
            route_maps=[
                RouteMap(
                    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
                    pattern=r".*",
                    route_type=RouteType.TOOL,
                ),
            ],
        )
        mcp.mount("remix", rest_api_mcp)

        MCPPrompts.register_prompts(mcp)

        # Run the MCP server in SSE mode
        asyncio.ensure_future(mcp.run_async(transport="sse"))
