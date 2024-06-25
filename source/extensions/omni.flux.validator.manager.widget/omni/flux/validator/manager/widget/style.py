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

import pathlib
from typing import Optional

import carb.imgui
from omni.ui import color as cl


def _get_icons(name: str) -> Optional[str]:
    """
    Get icon from the extension

    Args:
        name: the name of the icon to get (without the extension)
    Returns:
        Path of the icon
    """
    root = pathlib.Path(__file__)
    for _ in range(6):
        root = root.parent
    for icon in root.joinpath("data", "icons").iterdir():
        if icon.stem == name:
            return str(icon)
    return None


def _get_image(name: str) -> Optional[str]:
    """
    Get icon from the extension

    Args:
        name: the name of the icon to get (without the extension)

    Returns:
        Path of the icon
    """
    root = pathlib.Path(__file__)
    for _ in range(6):
        root = root.parent
    for icon in root.joinpath("data", "images").iterdir():
        if icon.stem == name:
            return str(icon)
    return None


_BLUE_SELECTED = 0x66FFC700
_BLUE_HOVERED = 0x1AFFC700

_GREY_32 = 0xFF202020
_GREY_50 = 0xFF303030

_WHITE_10 = 0x1AFFFFFF
_WHITE_20 = 0x33FFFFFF
_WHITE_30 = 0x4DFFFFFF
_WHITE_60 = 0x99FFFFFF
_WHITE_70 = 0xB3FFFFFF
_WHITE_100 = 0xFFFFFFFF

_DEFAULT_DARK_PANEL_BACKGROUND_VALUE = {
    "background_color": _GREY_32,
    "border_width": 1,
    "border_color": _WHITE_20,
    "border_radius": 8,
}

# override global imgui style
imgui = carb.imgui.acquire_imgui()
imgui.push_style_color(carb.imgui.StyleColor.WindowShadow, carb.Float4(0, 0, 0, 0))

cl.validation_result_ok = cl(0.0, 0.6, 0.0, 1.0)
cl.validation_result_failed = cl(0.6, 0.0, 0.0, 1.0)
cl.validation_result_default = cl(0.0, 0.6, 0.0, 1.0)
cl.validation_progress_color = cl.validation_result_default

style = {
    "Field::ValidatorField": {"background_color": 0x0},
    "Image::PropertiesPaneSectionInfo": {"image_url": _get_icons("info"), "color": _WHITE_60},
    "Image::PropertiesPaneSectionInfo:hovered": {"image_url": _get_icons("info"), "color": _WHITE_100},
    "Image::TreePanelLinesBackground": {
        "image_url": _get_image("45deg-256x256-1px-2px-sp-black"),
        "color": _WHITE_30,
    },
    "Label::PropertiesPaneSectionTitle": {
        "color": _WHITE_70,
        "font_size": 18,
    },
    "Label::PropertiesWidgetLabel": {"color": _WHITE_70, "font_size": 14},
    "Rectangle::BackgroundWithBorder": {
        "background_color": 0x0,
        "border_width": 1,
        "border_color": _GREY_50,
        "border_radius": 1,
    },
    "Rectangle::PropertiesPaneSectionWindowBackground": _DEFAULT_DARK_PANEL_BACKGROUND_VALUE,
    "ScrollingFrame::PropertiesPaneSection": {"background_color": 0x0, "secondary_color": 0x12FFFFFF},
    "ScrollingFrame::TreePanelBackground": {"background_color": 0x0},
    "TreeView": {
        "background_color": 0x0,
        "background_selected_color": _BLUE_HOVERED,
    },  # background_selected_color = hovered
    "TreeView:selected": {"background_color": _BLUE_SELECTED},
    "TreeView.Selection": {
        "background_color": 0x0,
        "background_selected_color": 0x0,
    },  # background_selected_color = hovered
    "TreeView.Selection:selected": {"background_color": 0x0},
    "TreeView.Item.Minus": {"image_url": _get_icons("disclosure-collapsed"), "color": _WHITE_60},
    "TreeView.Item.Plus": {"image_url": _get_icons("disclosure-collapsed_h"), "color": _WHITE_60},
}
