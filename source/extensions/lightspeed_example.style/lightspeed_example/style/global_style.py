# Copyright (c) 2018-2021, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
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
