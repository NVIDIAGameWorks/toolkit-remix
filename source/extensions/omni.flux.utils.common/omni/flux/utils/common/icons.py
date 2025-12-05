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

__all__ = ["get_prim_type_icons", "ICONS_SETTING_PATH"]

import carb.settings

ICONS_SETTING_PATH = "/exts/omni.flux.utils.common/icons"


def get_prim_type_icons() -> dict[str, str]:
    """
    Get the prim type to icon name mapping from extension settings.

    Icons are defined in extension.toml files under the setting path
    `/exts/omni.flux.utils.common/icons`. Multiple extensions can contribute
    icons by adding to this setting in their extension.toml:

        [settings.exts."omni.flux.utils.common".icons]
        MyPrimType = "MyIconName"

    Returns:
        Dictionary mapping prim type names to icon style names.
        Returns empty dict if no icons are configured.
    """
    icons_dict = carb.settings.get_settings().get(ICONS_SETTING_PATH)
    return dict(icons_dict) if isinstance(icons_dict, dict) else {}
