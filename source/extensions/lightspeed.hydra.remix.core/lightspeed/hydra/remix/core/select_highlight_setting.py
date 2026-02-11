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

import carb.settings

SETTING_NAME = "/exts/lightspeed/hydra/remix/useLegacySelectHighlight"


# This can be called from HdRemix.dll::renderDelegate.cpp and from Python,
# so the setting is shared between Hydra delegate and Python code
def hdremix_uselegacyselecthighlight() -> int:
    defaultvalue = 0
    try:
        isettings = carb.settings.get_settings()

        if isettings is None:
            return defaultvalue

        if isettings.get(SETTING_NAME) is None:
            return defaultvalue

        return 1 if isettings.get_as_bool(SETTING_NAME) else 0
    except Exception:  # noqa: BLE001
        return defaultvalue
