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

__all__ = (
    "COMFYUI_ASSET_OUTPUT_FOLDER",
    "COMFYUI_INPUTS_FOLDER",
    "COMFYUI_OUTPUTS_FOLDER",
    "COMFYUI_PROCESSED_FOLDER",
    "COMFYUI_SETTINGS_ROOT",
    "COMFYUI_WORKFLOWS_ROUTE",
    "HOSTNAME_REGEX",
    "INVALID_LOCAL_LEAF_CHARACTERS",
    "SUPPORTED_COMFYUI_SCHEMES",
    "WINDOWS_RESERVED_LOCAL_LEAVES",
)

import re

COMFYUI_SETTINGS_ROOT = "/exts/lightspeed.trex.comfyui.core"
#: Folder under the project's ingested assets that holds every published ComfyUI result, one child per job.
COMFYUI_PROCESSED_FOLDER = "comfyui"
#: Child of the published job folder that receives the optimized mesh directory.
COMFYUI_ASSET_OUTPUT_FOLDER = "asset"
#: Child of the job folder (server side and queue side) that holds uploaded inputs, one child per source hash.
COMFYUI_INPUTS_FOLDER = "inputs"
#: Child of the queue job directory that holds downloaded results, one child per prompt.
COMFYUI_OUTPUTS_FOLDER = "outputs"
#: RTX Remix node pack route that lists, types, and serves workflows.
COMFYUI_WORKFLOWS_ROUTE = "/rtx-remix/v1/workflows"
HOSTNAME_REGEX = re.compile(r"^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)(\.(?!-)[a-zA-Z0-9-]{1,63}(?<!-))*$")
INVALID_LOCAL_LEAF_CHARACTERS = frozenset('<>:"/\\|?*')
SUPPORTED_COMFYUI_SCHEMES = frozenset(("http", "https"))
WINDOWS_RESERVED_LOCAL_LEAVES = frozenset(
    {
        "AUX",
        "CON",
        "NUL",
        "PRN",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)
