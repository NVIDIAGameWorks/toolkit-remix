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

__all__ = ["MCPPrompts"]

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


class MCPPrompts:
    """Class that wraps MCP prompt definitions."""

    @classmethod
    def register_prompts(cls, mcp: FastMCP):
        """Register all prompts with the MCP instance."""

        @mcp.prompt()
        def replace_model_asset(ingested_asset: str) -> str:
            """
            Returns a prompt for replacing a selected 3D model asset in the RTX Remix viewport.
            """
            return f"""
            Use this prompt when a user wants to swap out a currently selected 3D model in the
            RTX Remix viewport with another asset they've specified.

            Please perform the following steps in order:

            1. To get the available ingested models, call the
               `get_available_ingested_assets` tool with the
               argument:
               - asset_type: "models"

            2. To get the current selection, call the `get_assets` tool with these arguments:
               - selection: true
               - asset_types: ["models"]

            3. Use the list of assets returned in step 1 to find the full absolute path that matches
               or contains "{ingested_asset}".
               - If multiple assets match, use the first matching asset.
               - If no exact match is found, look for assets that contain the provided input as a substring
                 in their path.

            4. Call the `replace_asset_file_path` tool with these arguments:
               - asset_path: Use the first asset path from the list returned by step 2
               - asset_file_path: Use the full absolute path you found in step 3
            """
