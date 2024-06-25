"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from pathlib import Path
from typing import Optional

import omni.kit.app
import omni.ui as ui

EXT_RESOURCE_ID = (
    omni.kit.app.get_app().get_extension_manager().get_enabled_extension_id("lightspeed_example.app.resources")
)
EXTENSION_RESOURCES_FOLDER_PATH = Path(
    omni.kit.app.get_app().get_extension_manager().get_extension_path(EXT_RESOURCE_ID)
)


def get_icons(name: str) -> Optional[str]:
    """Get icon from the lightspeed_example.app.resources extension"""
    for icon in EXTENSION_RESOURCES_FOLDER_PATH.joinpath("data", "icons").iterdir():
        if icon.stem == name:
            return str(icon)
    return None


style = ui.Style.get_instance()
current_dict = style.default
current_dict.update(
    {
        "Button::Button1": {"background_color": 0xFF0000FF, "border_radius": 1.0, "margin": 3.0, "padding": 3.0},
        "Button::Button2": {"background_color": 0xFF00FF00, "border_radius": 2.0, "margin": 1.0, "padding": 2.0},
    }
)
style.default = current_dict
