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

import carb.settings

# Default ComfyUI URL
DEFAULT_COMFY_URL = "http://127.0.0.1:8188"

# Persistent setting path for the ComfyUI URL (persisted between sessions)
COMFY_URL_SETTING_PATH = "/persistent/exts/lightspeed.trex.ai_tools.widget/comfy_url"


def get_comfy_url() -> str:
    """
    Get the current ComfyUI URL from settings.

    Returns the persisted value if set, otherwise returns the default URL.
    """
    url = carb.settings.get_settings().get(COMFY_URL_SETTING_PATH)
    if url is None or not isinstance(url, str):
        return DEFAULT_COMFY_URL
    return url


def set_comfy_url(url: str) -> None:
    """
    Set the ComfyUI URL in persistent settings.

    This value will be remembered between sessions.
    """
    carb.settings.get_settings().set(COMFY_URL_SETTING_PATH, url)
