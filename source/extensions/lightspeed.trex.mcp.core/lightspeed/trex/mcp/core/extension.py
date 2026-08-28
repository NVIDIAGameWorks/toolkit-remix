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

from __future__ import annotations

import carb
import omni.ext
import omni.kit.app
from fastmcp import FastMCP

from .mcp import MCPCore

__all__ = ["MCPCoreExtension", "get_mcp_instance"]

_instance: FastMCP | None = None


def get_mcp_instance() -> FastMCP | None:
    """Return the MCP server instance when it has been initialized."""
    return _instance


class MCPCoreExtension(omni.ext.IExt):
    """Manage MCP server initialization during the Kit application lifecycle."""

    def __init__(self) -> None:
        """Initialize the extension lifecycle state."""
        super().__init__()
        self._app_ready_subscription: carb.events.ISubscription | None = None
        self._is_shutdown: bool = False

    def on_startup(self, _ext_id: str) -> None:
        """Start the MCP server when the Kit application is ready."""
        carb.log_info("[lightspeed.trex.mcp.core] Startup")
        self._is_shutdown = False

        app = omni.kit.app.get_app()
        if app.is_app_ready():
            self._start_mcp_server()
            return

        self._app_ready_subscription = app.get_startup_event_stream().create_subscription_to_pop_by_type(
            omni.kit.app.EVENT_APP_READY,
            self._on_app_ready,
            name="MCP Server App Ready",
        )

    def on_shutdown(self) -> None:
        """Release lifecycle resources as the extension shuts down."""
        carb.log_info("[lightspeed.trex.mcp.core] Shutdown")
        self._is_shutdown = True
        self._app_ready_subscription = None
        MCPCore.shutdown()

        global _instance
        _instance = None

    def _on_app_ready(self, _event: carb.events.IEvent) -> None:
        """Initialize the MCP server after Kit dispatches its ready event."""
        self._app_ready_subscription = None
        if self._is_shutdown:
            return
        self._start_mcp_server()

    def _start_mcp_server(self) -> None:
        """Initialize the MCP server once for the active extension instance."""
        global _instance
        if _instance is not None:
            return

        _instance = FastMCP("RTX Remix MCP Server")
        MCPCore.initialize(_instance)
