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
    "COMFYUI_SETTINGS_ROOT",
    "HOSTNAME_REGEX",
    "INVALID_LOCAL_LEAF_CHARACTERS",
    "SUPPORTED_COMFYUI_SCHEMES",
    "WINDOWS_RESERVED_LOCAL_LEAVES",
)

import re

COMFYUI_SETTINGS_ROOT = "/exts/lightspeed.trex.comfyui.core"
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
