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


def _get_icons(name: str) -> str | None:
    """
    Get icon from the extension

    Args:
        name: the name of the icon to get (without the extension)
    Returns:
        Path of the icon
    """
    root = pathlib.Path(__file__)
    for _ in range(5):
        root = root.parent
    for icon in root.joinpath("data", "icons").iterdir():
        if icon.stem == name:
            return str(icon)
    return None


_DARK_00 = 0x01000000  # 01 for alpha or it will show a default color
_BLUE_SELECTED = 0x66FFC700
_BLUE_HOVERED = 0x1AFFC700

_GREY_32 = 0xFF202020
_GREY_50 = 0xFF303030

_RED_05 = 0x0D0000FF

_WHITE_10 = 0x1AFFFFFF
_WHITE_20 = 0x33FFFFFF
_WHITE_30 = 0x4DFFFFFF
_WHITE_60 = 0x99FFFFFF
_WHITE_70 = 0xB3FFFFFF
_WHITE_80 = 0xCCFFFFFF
_WHITE_100 = 0xFFFFFFFF


_DEFAULT_DARK_PANEL_BACKGROUND_VALUE = {
    "background_color": _GREY_32,
    "border_width": 1,
    "border_color": _WHITE_20,
    "border_radius": 8,
}


_DEFAULT_FIELD_READ_VALUE = {
    "background_color": _DARK_00,  # 01 for alpha or it will show a default color
    "color": 0x90FFFFFF,
    "border_width": 1,
    "border_radius": 5,
    "border_color": 0x0DFFFFFF,
    "font_size": 14,
}

_DEFAULT_FIELD_READ_ERROR_VALUE = {
    "background_color": _RED_05,  # 01 for alpha or it will show a default color
    "color": 0xCC0000FF,
    "border_width": 1,
    "border_radius": 5,
    "border_color": 0x0DFFFFFF,
    "font_size": 14,
}

_DEFAULT_FIELD_READ_HOVERED_VALUE = {
    "background_color": _BLUE_HOVERED,
    "color": _WHITE_80,
    "border_width": 1,
    "border_radius": 5,
    "border_color": _WHITE_20,
    "font_size": 14,
}


style = {
    "Image::Copy": {"image_url": _get_icons("copy"), "color": _WHITE_60, "margin_width": 4},
    "Image::Copy:hovered": {"image_url": _get_icons("copy"), "color": _WHITE_100, "margin_width": 4},
    "Rectangle::PropertiesPaneSectionWindowBackground": _DEFAULT_DARK_PANEL_BACKGROUND_VALUE,
    "Rectangle::SelectableToolTipBackground": _DEFAULT_FIELD_READ_VALUE,
    "Rectangle::SelectableToolTipBackground:hovered": _DEFAULT_FIELD_READ_HOVERED_VALUE,
    "ScrollingFrame::PropertiesPaneSection": {"background_color": 0x0, "secondary_color": 0x12FFFFFF},
    "ScrollingFrame::TreePanelBackground": {"background_color": 0x0},
}
