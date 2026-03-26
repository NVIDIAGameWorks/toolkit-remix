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

Name-based style configuration for the Curve Editor widget.

All colors are 0xAABBGGRR (omni.ui ABGR convention).
"""

from __future__ import annotations

from functools import lru_cache

from omni.flux.utils.widget.resources import get_icons

__all__ = ["DEFAULT_STYLE", "TOOLBAR_BUTTON_ICONS", "build_default_style"]

# Button ID suffix → icon file stem (without file extension).
# Shared between the style builder (resolves icon paths) and the toolbar
# (maps each button to its widget name ``CurveEditorBtn{id}``).
TOOLBAR_BUTTON_ICONS: dict[str, str] = {
    "AddKey": "KeyframeAdd",
    "DeleteKey": "KeyframeDelete",
    "Link": "Tangents_Link",
    "Broken": "Tangents_Broken",
    "TangentLinear": "Tangent_Linear",
    "TangentStep": "Tangent_Step",
    "TangentFlat": "Tangent_Flat",
    "TangentAuto": "Tangent_Auto",
    "TangentSmooth": "Tangent_Smooth",
    "TangentCustom": "Tangent_Custom",
}

DEFAULT_STYLE: dict[str, dict] = {
    # ── Canvas ───────────────────────────────────────────────────────────────
    "Rectangle::CurveEditorBackground": {
        "background_color": 0xFF1A1A1A,
    },
    "Rectangle::CurveEditorCorner": {
        "background_color": 0xFF252525,
    },
    "Label::CurveEditorStatus": {
        "color": 0xAABBBBBB,
        "font_size": 16,
        "margin_width": 6,
        "margin_height": 4,
    },
    # ── Grid ─────────────────────────────────────────────────────────────────
    "Rectangle::CurveEditorGrid": {
        "background_color": 0x10FFFFFF,
    },
    "Rectangle::CurveEditorGridMajor": {
        "background_color": 0x25FFFFFF,
    },
    "Rectangle::CurveEditorAxis": {
        "background_color": 0x40FFFFFF,
    },
    # ── Ruler ────────────────────────────────────────────────────────────────
    "Label::CurveEditorRulerLabel": {
        "color": 0xFFCCCCCC,
        "font_size": 12,
    },
    "Rectangle::CurveEditorRulerTick": {
        "background_color": 0xFF888888,
    },
    "Rectangle::CurveEditorRulerBg": {
        "background_color": 0xFF252525,
    },
    # ── Toolbar (non-button widgets) ─────────────────────────────────────────
    "Label::CurveEditorToolbarLabel": {
        "color": 0xFFBBBBBB,
        "font_size": 12,
    },
    "Rectangle::CurveEditorToolbarSep": {
        "background_color": 0xFF555555,
    },
    # ── Panels ────────────────────────────────────────────────────────────────
    "Rectangle::CurveEditorToolbarBg": {
        "background_color": 0xFF343434,
    },
    "HStack::CurveEditorToolbar": {
        "margin_width": 8,
    },
    "Rectangle::CurveEditorTreePanelBg": {
        "background_color": 0xFF252525,
    },
    "Rectangle::CurveEditorMainBg": {
        "background_color": 0xFF1A1A1A,
    },
    "HStack::CurveEditorTreeRow": {
        "margin_width": 8,
    },
    "Label::CurveEditorListEmpty": {
        "color": 0xFF808080,
    },
    # ── Guideline ────────────────────────────────────────────────────────────
    "Rectangle::CurveEditorGuideline": {
        "background_color": 0x20FFFFFF,
    },
}

_BTN_BASE = {"background_color": 0xFF3A3A3A, "border_radius": 4, "margin": 1}
_BTN_HOVERED = {"background_color": 0xFF4A4A4A}
_BTN_ACTIVE = {"background_color": 0xFFFFFFFF, "border_radius": 4, "margin": 1}
_BTN_ACTIVE_HOVERED = {"background_color": 0xFFEEEEEE}


@lru_cache(maxsize=4)
def build_default_style(resources_ext: str = "omni.flux.resources") -> dict[str, dict]:
    """Build the full default style with resolved icon paths.

    Generates per-button entries for every toolbar button so that icon URLs,
    hover colors, and active states are all driven by the stylesheet.  Each
    button uses a unique name (``CurveEditorBtn{id}`` / ``CurveEditorBtn{id}Active``)
    giving full pseudo-state control via the omni.ui cascade.

    Must be called after the extension system is running (icons are resolved
    via ``omni.flux.utils.widget.resources.get_icons``).  The result is cached
    per *resources_ext* value, so repeated calls are free.

    Args:
        resources_ext: Extension providing ``data/icons/``.  Defaults to
            ``"omni.flux.resources"``; downstream apps can pass their own
            themed resources extension.
    """
    style: dict[str, dict] = dict(DEFAULT_STYLE)

    for btn_id, icon_stem in TOOLBAR_BUTTON_ICONS.items():
        name = f"CurveEditorBtn{btn_id}"
        icon_path = get_icons(icon_stem, ext_name=resources_ext) or ""

        style[f"Button::{name}"] = dict(_BTN_BASE)
        style[f"Button::{name}:hovered"] = dict(_BTN_HOVERED)
        style[f"Button.Image::{name}"] = {"image_url": icon_path}

        style[f"Button::{name}Active"] = dict(_BTN_ACTIVE)
        style[f"Button::{name}Active:hovered"] = dict(_BTN_ACTIVE_HOVERED)
        style[f"Button.Image::{name}Active"] = {
            "image_url": icon_path,
            "color": 0xFF000000,
        }

    # Tree panel icons (reuse toolbar icon stems)
    add_icon = get_icons("KeyframeAdd", ext_name=resources_ext) or ""
    delete_icon = get_icons("KeyframeDelete", ext_name=resources_ext) or ""
    style["Image::CurveEditorTreeAdd"] = {"image_url": add_icon}
    style["Image::CurveEditorTreeDelete"] = {"image_url": delete_icon}

    return style
