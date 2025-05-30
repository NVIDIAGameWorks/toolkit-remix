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

from typing import Optional

import carb
import carb.settings
import omni.ext
from fastmcp import FastMCP

from .mcp import MCPCore

_instance: Optional[FastMCP] = None


def get_mcp_instance():
    return _instance


class MCPCoreExtension(omni.ext.IExt):
    def on_startup(self, _ext_id):
        carb.log_info("[lightspeed.trex.mcp.core] Startup")

        global _instance
        _instance = FastMCP("RTX Remix MCP Server")

        MCPCore.initialize(_instance)

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.mcp.core] Shutdown")

        global _instance
        _instance = None
