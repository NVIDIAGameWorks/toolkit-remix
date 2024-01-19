"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import carb.settings

SETTING_NAME = "/exts/lightspeed.trex.viewports.manipulators/dxvkremix_use_legacy_select_highlight"


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
    except Exception:
        return defaultvalue
