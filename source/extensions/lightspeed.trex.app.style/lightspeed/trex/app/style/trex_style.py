# noqa PLC0302

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

import asyncio

import carb
import omni.kit.imgui
import omni.ui as ui
from omni.flux.utils.widget.resources import get_fonts as _get_fonts
from omni.flux.utils.widget.resources import get_icons as _get_icons
from omni.flux.utils.widget.resources import get_image as _get_image
from omni.kit.window.popup_dialog import message_dialog
from omni.ui import color as cl
from omni.ui import constant as fl


# override global imgui style
@omni.usd.handle_exception
async def __override_imgui_style():
    """Wait 3 frames or it will crash"""
    for _ in range(3):
        await omni.kit.app.get_app().next_update_async()
    imgui = omni.kit.imgui.acquire_imgui()
    imgui.push_style_color(omni.kit.imgui.StyleColor.WindowShadow, carb.Float4(0.0, 0.0, 0.0, 1.0))


asyncio.ensure_future(__override_imgui_style())


# default values (AABBGGRR)
_BLUE_SELECTED = 0x66FFC700
_BLUE_SEMI_SELECTED = 0x33FFC700
_BLUE_HOVERED = 0x1AFFC700
_BLUE_ACTION = 0xFFFFC734

_DARK_00 = 0x01000000  # 01 for alpha or it will show a default color
_DARK_40 = 0x66000000
_DARK_85 = 0xD9000000
_TRUE_DARK = 0xFF000000

_GREY_26 = 0xFF1A1A1A
_GREY_32 = 0xFF202020
_GREY_40 = 0xFF282828
_GREY_42 = 0xFF2A2A2A
_GREY_50 = 0xFF303030
_GREY_55 = 0xFF373737
_GREY_60 = 0xFF3C3C3C
_GREY_70 = 0xFF464646

_GREEN_05 = 0x0D00FF00
_GREEN_20 = 0x3300FF00
_GREEN_60 = 0x9900FF00
_GREEN_80 = 0xCC00FF00
_GREEN_100 = 0xFF00FF00

_RED_05 = 0x0D0000FF
_RED_20 = 0x330000FF
_RED_60 = 0x990000FF
_RED_80 = 0xCC0000FF
_RED_100 = 0xFF0000FF

_WHITE_10 = 0x1AFFFFFF
_WHITE_20 = 0x33FFFFFF
_WHITE_30 = 0x4DFFFFFF
_WHITE_40 = 0x66FFFFFF
_WHITE_50 = 0x80FFFFFF
_WHITE_60 = 0x99FFFFFF
_WHITE_70 = 0xB3FFFFFF
_WHITE_80 = 0xCCFFFFFF
_WHITE_100 = 0xFFFFFFFF

_YELLOW = 0xFF00FFFF

_MIXED = 0xFF07B6FF

_PALE_ORANGE_40 = 0x4D4682B4
_PALE_ORANGE_60 = 0x994682B4
_ORANGE = 0xFF00AEFF

_DEFAULT_FIELD_READ_VALUE = {
    "background_color": _DARK_00,
    "color": 0x90FFFFFF,
    "border_width": 1,
    "border_radius": 5,
    "border_color": 0x0DFFFFFF,
    "font_size": 14,
}

_DEFAULT_FIELD_READ_ERROR_VALUE = {
    "background_color": _RED_05,
    "color": 0xFF7868FF,
    "border_width": 1,
    "border_radius": 5,
    "border_color": 0x0DFFFFFF,
    "font_size": 14,
}

_DEFAULT_FIELD_MIXED_VALUE = {
    "background_color": _PALE_ORANGE_60,
    "color": _WHITE_60,
    "border_width": 1,
    "border_radius": 5,
    "border_color": _WHITE_20,
    "font_size": 14,
}

_DEFAULT_FIELD_READ_ONLY_MIXED_VALUE = {
    "background_color": _PALE_ORANGE_40,
    "color": 0x90FFFFFF,
    "border_width": 1,
    "border_radius": 5,
    "border_color": 0x0DFFFFFF,
    "font_size": 14,
}

_DEFAULT_FIELD_WARNING_VALUE = {
    "background_color": _DARK_00,
    "color": _ORANGE,
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

_DEFAULT_DARK_PANEL_BACKGROUND_VALUE = {
    "background_color": _GREY_32,
    "border_width": 1,
    "border_color": _WHITE_20,
    "border_radius": 8,
}


ui.url.nvidia_md = _get_fonts("NVIDIASans_A_Md")
ui.url.nvidia_rg = _get_fonts("NVIDIASans_A_Rg")
ui.url.nvidia_bd = _get_fonts("NVIDIASans_A_Bd")
ui.url.nvidia_lt = _get_fonts("NVIDIASans_A_Lt")


# validation colors
cl.validation_result_ok = cl(0.0, 0.6, 0.0, 1.0)
cl.validation_result_failed = cl(0.6, 0.0, 0.0, 1.0)
cl.validation_result_default = cl(0.0, 0.6, 0.0, 1.0)
cl.validation_progress_color = cl.validation_result_default


def update_viewport_menu_style():
    """Should be called after the creation of the menus"""
    # viewport menu
    cl.viewport_menubar_selection = cl.shade(cl("#34C7FF3B"))
    cl.viewport_menubar_selection_border = cl.shade(cl("#34C7FF"))
    cl.viewport_menubar_selection_border_button = cl.shade(cl("#2B87AA"))
    cl.viewport_menubar_background = cl.shade(cl("#25282ACC"))
    cl.viewport_menubar_title_background = 0x0
    cl.viewport_menubar_selection_border = cl.shade(cl("#34C7FF"))
    cl.viewport_menubar_selection_border_button = 0x0
    fl.viewport_menubar_border_radius = fl.shade(0)

    cl.toolbar_button_background = cl.shade(0x0)
    cl.toolbar_button_background_checked = cl.shade(cl("#34C7FF3B"))
    cl.toolbar_button_background_pressed = cl.shade(cl("#2B87AA"))
    cl.toolbar_button_background_hovered = cl.shade(cl("#2b87aa4d"))


update_viewport_menu_style()


# override the style of the message dialog
def override_dialog_get_style(style_value):  # noqa PLW0621
    style_value.update(
        {
            "Background": {"color": _WHITE_100, "background_color": 0x0, "border_width": 0},
            "Button": {"background_color": _BLUE_HOVERED, "selected_color": 0xFF8A8777, "margin": 0},
            "Button:hovered": {"background_color": _BLUE_SELECTED, "selected_color": 0xFF8A8777, "margin": 0},
            "Button.Label": {"color": _WHITE_80},
            "Button.Label:hovered": {"color": _WHITE_100},
        }
    )
    return style_value


try:
    style_value = message_dialog.get_style()
    message_dialog.get_style = lambda: override_dialog_get_style(style_value)
except AttributeError:
    from omni.kit.window.popup_dialog.style import UI_STYLES

    UI_STYLES["NvidiaLight"] = override_dialog_get_style(UI_STYLES["NvidiaLight"])
    UI_STYLES["NvidiaDark"] = override_dialog_get_style(UI_STYLES["NvidiaDark"])


style = ui.Style.get_instance()
current_dict = style.default
current_dict.update(
    {
        # General Styling
        "Button": {
            "background_color": 0x33000000,
            "border_width": 1,
            "border_color": _WHITE_20,
            "border_radius": 4,
            "margin": 2,
        },
        "Button:disabled": {
            "background_color": _GREY_55,
            "border_color": _WHITE_30,
        },
        "Button:hovered": {
            "background_color": _GREY_60,
            "border_color": _WHITE_10,
        },
        "Button::NoBackground": {
            "background_color": 0x0,
            "border_width": 1,
            "border_color": _WHITE_20,
            "border_radius": 4,
            "margin": 2,
        },
        "Button::NoBackground:disabled": {
            "background_color": 0x0,
            "border_width": 1,
            "border_color": _WHITE_30,
            "border_radius": 4,
            "margin": 2,
        },
        "Button.Label::SdfPathButton": {"alignment": ui.Alignment.LEFT_CENTER},
        "Button::LightCylinder": {
            "background_color": 0x0,
            "border_radius": 4,
            "padding": 6,
        },
        "Button.Image::LightCylinder": {"image_url": _get_icons("light_cylinder"), "color": _WHITE_60},
        "Button.Image::LightCylinder:hovered": {"image_url": _get_icons("light_cylinder"), "color": _WHITE_100},
        "Button::LightDisk": {
            "background_color": 0x0,
            "border_radius": 4,
            "padding": 6,
        },
        "Button.Image::LightDisk": {"image_url": _get_icons("light_disc"), "color": _WHITE_60},
        "Button.Image::LightDisk:hovered": {"image_url": _get_icons("light_disc"), "color": _WHITE_100},
        "Button::LightDistant": {
            "background_color": 0x0,
            "border_radius": 4,
            "padding": 6,
        },
        "Button.Image::LightDistant": {"image_url": _get_icons("light_distant"), "color": _WHITE_60},
        "Button.Image::LightDistant:hovered": {"image_url": _get_icons("light_distant"), "color": _WHITE_100},
        "Button::LightRect": {
            "background_color": 0x0,
            "border_radius": 4,
            "padding": 6,
        },
        "Button.Image::LightRect": {"image_url": _get_icons("light_rect"), "color": _WHITE_60},
        "Button.Image::LightRect:hovered": {"image_url": _get_icons("light_rect"), "color": _WHITE_100},
        "Button::LightSphere": {
            "background_color": 0x0,
            "border_radius": 4,
            "padding": 6,
        },
        "Button.Image::LightSphere": {"image_url": _get_icons("light_point"), "color": _WHITE_60},
        "Button.Image::LightSphere:hovered": {"image_url": _get_icons("light_point"), "color": _WHITE_100},
        "Button.Label::NoBackground:disabled": {
            "color": _WHITE_30,
        },
        "Button.Image::Particle": {"image_url": _get_icons("particle"), "color": _WHITE_60},
        "Button.Image::Particle:hovered": {"image_url": _get_icons("particle"), "color": _WHITE_100},
        "Button.Image::teleport": {"image_url": _get_icons("teleport")},
        "Button.Image::ShowValidation": {
            "image_url": _get_icons("v-box"),
            "color": _WHITE_20,
            "margin": 0,
            "margin_width": 1,
            "border_radius": 4,
        },
        "Button.Image::ShowValidation:checked": {
            "image_url": _get_icons("v-box"),
            "color": _WHITE_60,
            "margin": 0,
            "margin_width": 1,
            "border_radius": 4,
        },
        "Button.Image::ShowValidation:hovered": {
            "image_url": _get_icons("v-box"),
            "color": _WHITE_100,
            "margin": 0,
            "margin_width": 1,
            "border_radius": 4,
        },
        "Button.Image::ShowValidationFailed": {
            "image_url": _get_icons("v-box"),
            "color": _RED_20,
            "margin": 0,
            "margin_width": 1,
            "border_radius": 4,
        },
        "Button.Image::ShowValidationFailed:checked": {
            "image_url": _get_icons("v-box"),
            "color": _RED_60,
            "margin": 0,
            "margin_width": 1,
            "border_radius": 4,
        },
        "Button.Image::ShowValidationFailed:hovered": {
            "image_url": _get_icons("v-box"),
            "color": _RED_100,
            "margin": 0,
            "margin_width": 1,
            "border_radius": 4,
        },
        "Button::ShowValidationFailed": {
            "background_color": _RED_20,
            "margin": 2,
            "margin_width": 1,
            "border_radius": 4,
        },
        "Button::ShowValidationFailed:checked": {
            "background_color": _RED_60,
            "margin": 2,
            "margin_width": 1,
            "border_radius": 4,
        },
        "CollapsableFrame::PropertiesPaneSection": {
            "background_color": 0x0,
            "secondary_color": 0x0,
        },
        "CollapsableFrame::PropertiesPaneSection:hovered": {
            "background_color": 0x0,
            "secondary_color": 0x0,
        },
        "ComboBox:hovered": {
            "background_color": _GREY_60,  # make brighter to distinguish from _GREY_50 background
            "secondary_color": _GREY_70,
        },
        "ExpandCollapseButton": {
            "background_color": 0,
        },
        "ExpandCollapseButton.Image::ExpandButton": {
            "image_url": _get_icons("speed_expand"),
        },
        "ExpandCollapseButton.Image::CollapseButton": {
            "image_url": _get_icons("speed_collapse"),
        },
        "Field": _DEFAULT_FIELD_READ_VALUE,
        "FieldError": _DEFAULT_FIELD_READ_ERROR_VALUE,
        "FieldWarning": _DEFAULT_FIELD_WARNING_VALUE,
        "Field:hovered": _DEFAULT_FIELD_READ_HOVERED_VALUE,
        "FreeBezierCurve::HeaderNvidiaLine": {"border_width": 1, "color": _WHITE_30},
        "FreeBezierCurve::TabLineIndicator": {"color": _BLUE_SELECTED, "border_width": 2},
        "IconSeparator": {
            "border_width": 45,
        },
        "Image::AddStatic": {"image_url": _get_icons("add"), "color": _WHITE_50},
        "Image::Add": {"image_url": _get_icons("add"), "color": _WHITE_60},
        "Image::Add:hovered": {"image_url": _get_icons("add"), "color": _WHITE_100},
        "Image::ArrowsLeftRight": {"image_url": _get_icons("arrows-left-right"), "color": _WHITE_80},
        "Image::Eye": {"image_url": _get_icons("eye"), "color": _WHITE_60},
        "Image::Eye:hovered": {"image_url": _get_icons("eye"), "color": _WHITE_100},
        "Image::EyeDisabled": {"image_url": _get_icons("eye"), "color": _WHITE_30},
        "Image::EyeOff": {"image_url": _get_icons("eye-off"), "color": _WHITE_60},
        "Image::EyeOff:hovered": {"image_url": _get_icons("eye-off"), "color": _WHITE_100},
        "Image::EyeOffDisabled": {"image_url": _get_icons("eye-off"), "color": _WHITE_30},
        "Image::CreateLayerDisabled": {"image_url": _get_icons("create-layer"), "color": _WHITE_30},
        "Image::CreateLayer": {"image_url": _get_icons("create-layer"), "color": _WHITE_60},
        "Image::CreateLayer:hovered": {"image_url": _get_icons("create-layer"), "color": _WHITE_100},
        "Image::Duplicate": {"image_url": _get_icons("copy"), "color": _WHITE_60},
        "Image::Duplicate:hovered": {"image_url": _get_icons("copy"), "color": _WHITE_80},
        "Image::ImportLayerDisabled": {"image_url": _get_icons("import-layer"), "color": _WHITE_30},
        "Image::ImportLayer": {"image_url": _get_icons("import-layer"), "color": _WHITE_60},
        "Image::ImportLayer:hovered": {"image_url": _get_icons("import-layer"), "color": _WHITE_100},
        "Image::FolderClosed": {"image_url": _get_icons("folder-closed"), "color": _WHITE_80},
        "Image::FrameDisabled": {"image_url": _get_icons("frame"), "color": _WHITE_30},
        "Image::Frame": {"image_url": _get_icons("frame"), "color": _WHITE_60},
        "Image::Frame:hovered": {"image_url": _get_icons("frame"), "color": _WHITE_100},
        "Image::Bookmark": {"image_url": _get_icons("bookmark"), "color": _WHITE_80},
        "Image::MixedForceDisabled": {"image_url": _get_icons("mixed_checkbox"), "color": _GREY_70},
        "Image::Mixed": {"image_url": _get_icons("mixed_checkbox"), "color": _MIXED},
        "Image::Nickname": {"image_url": _get_icons("nickname"), "color": _WHITE_60},
        "Image::Nickname:hovered": {"image_url": _get_icons("nickname"), "color": _WHITE_100},
        "Image::RemapSkeleton": {"image_url": _get_icons("remap"), "color": _WHITE_80},
        "Image::RemapSkeleton:hovered": {"image_url": _get_icons("remap"), "color": _WHITE_100},
        "Image::RemapSkeletonDisabled": {"image_url": _get_icons("remap"), "color": _WHITE_30},
        "Image::RemapSkeletonDisabled:hovered": {"image_url": _get_icons("remap"), "color": _WHITE_100},
        "Image::SubtractDisabled": {"image_url": _get_icons("subtract"), "color": _WHITE_30},
        "Image::Subtract": {"image_url": _get_icons("subtract"), "color": _WHITE_60},
        "Image::Subtract:hovered": {"image_url": _get_icons("subtract"), "color": _WHITE_100},
        "Image::SaveDisabled": {"image_url": _get_icons("save"), "color": _WHITE_30},
        "Image::Save": {"image_url": _get_icons("save_filled"), "color": _WHITE_60},
        "Image::Save:hovered": {"image_url": _get_icons("save_filled"), "color": _WHITE_100},
        "Image::Skeleton": {"image_url": _get_icons("skeleton"), "color": _WHITE_60},
        "Image::SkeletonJoint": {"image_url": _get_icons("skel_joint"), "color": _WHITE_60},
        "Image::SkeletonRoot": {"image_url": _get_icons("skel_root"), "color": _WHITE_60},
        "Image::LockDisabled": {"image_url": _get_icons("lock"), "color": _WHITE_30},
        "Image::Light": {"image_url": _get_icons("light"), "color": _WHITE_60},
        "Image::Lock": {"image_url": _get_icons("lock"), "color": _WHITE_60},
        "Image::Lock:hovered": {"image_url": _get_icons("lock"), "color": _WHITE_100},
        "Image::UnlockDisabled": {"image_url": _get_icons("unlock"), "color": _WHITE_30},
        "Image::Unlock": {"image_url": _get_icons("unlock"), "color": _WHITE_60},
        "Image::Unlock:hovered": {"image_url": _get_icons("unlock"), "color": _WHITE_100},
        "Image::LayerActive": {"image_url": _get_icons("layers"), "color": _WHITE_100},
        "Image::Layer": {"image_url": _get_icons("layers"), "color": _WHITE_60},
        "Image::Layer:hovered": {"image_url": _get_icons("layers"), "color": _WHITE_100},
        "Image::LayerStatic": {"image_url": _get_icons("layers"), "color": _WHITE_60},
        "Image::LayerDisabled": {"image_url": _get_icons("layers"), "color": _WHITE_30},
        "Image::MoreForceDisabled": {"image_url": _get_icons("ellipsis"), "color": _GREY_70},
        "Image::More": {"image_url": _get_icons("ellipsis"), "color": _WHITE_60},
        "Image::More:hovered": {"image_url": _get_icons("ellipsis"), "color": _WHITE_100},
        "Image::Hourglass": {"image_url": _get_icons("hourglass"), "color": _WHITE_100},
        "Image::Particle": {"image_url": _get_icons("particle"), "color": _WHITE_60},
        "Image::Particle:hovered": {"image_url": _get_icons("particle"), "color": _WHITE_100},
        "Image::DeleteParticle": {"image_url": _get_icons("particle-delete"), "color": _WHITE_60},
        "Image::DeleteParticle:hovered": {"image_url": _get_icons("particle-delete"), "color": _WHITE_100},
        "Image::ParticleDisabled": {"image_url": _get_icons("particle"), "color": _WHITE_30},
        "Image::TreePanelLinesBackground": {
            "image_url": _get_image("45deg-256x256-1px-2px-sp-black"),
            "color": _WHITE_30,
        },
        "Image::OpenFolder": {"image_url": _get_icons("folder_open"), "color": _WHITE_60},
        "Image::OpenFolder:hovered": {"image_url": _get_icons("folder_open"), "color": _WHITE_100},
        "Image::Pin": {"image_url": _get_icons("pin"), "color": _ORANGE},
        "Image::PinOff": {"image_url": _get_icons("pin-outline"), "color": _WHITE_60},
        "Image::Import": {"image_url": _get_icons("import"), "color": _WHITE_60},
        "Image::Import:hovered": {"image_url": _get_icons("import"), "color": _WHITE_100},
        "Image::GoBack": {"image_url": _get_icons("go-back-icon"), "color": _WHITE_60},
        "Image::GoBack:hovered": {"image_url": _get_icons("go-back-icon"), "color": _WHITE_80},
        "Image::GoBack:selected": {"image_url": _get_icons("go-back-icon"), "color": _WHITE_100},
        "Image::HeaderNavigatorLogo": {"image_url": _get_image("NVIDIA-logo-header"), "color": _WHITE_100},
        "Image::MenuBurger": {"image_url": _get_icons("menu-burger"), "color": _WHITE_60},
        "Image::MenuBurger:hovered": {"image_url": _get_icons("menu-burger"), "color": _WHITE_80},
        "Image::MenuBurger:selected": {"image_url": _get_icons("menu-burger"), "color": _WHITE_100},
        "Image::MenuBurgerDisabled": {"image_url": _get_icons("menu-burger"), "color": _WHITE_30},
        "Image::Home": {"image_url": _get_icons("home-icon"), "color": _WHITE_60},
        "Image::Home:hovered": {"image_url": _get_icons("home-icon"), "color": _WHITE_80},
        "Image::Home:selected": {"image_url": _get_icons("home-icon"), "color": _WHITE_100},
        "Image::HomeDisabled": {"image_url": _get_icons("home-icon"), "color": _WHITE_30},
        "Image::ProjectSetup": {"image_url": _get_icons("project-setup-icon"), "color": _WHITE_60},
        "Image::ProjectSetup:hovered": {"image_url": _get_icons("project-setup-icon"), "color": _WHITE_80},
        "Image::ProjectSetup:selected": {"image_url": _get_icons("project-setup-icon"), "color": _WHITE_100},
        "Image::ProjectSetupDisabled": {"image_url": _get_icons("project-setup-icon"), "color": _WHITE_30},
        "Image::Modding": {"image_url": _get_icons("modding-icon"), "color": _WHITE_60},
        "Image::Modding:hovered": {"image_url": _get_icons("modding-icon"), "color": _WHITE_80},
        "Image::Modding:selected": {"image_url": _get_icons("modding-icon"), "color": _WHITE_100},
        "Image::ModdingDisabled": {"image_url": _get_icons("modding-icon"), "color": _WHITE_30},
        "Image::PackageMod": {"image_url": _get_icons("package-mod-icon"), "color": _WHITE_60},
        "Image::PackageMod:hovered": {"image_url": _get_icons("package-mod-icon"), "color": _WHITE_80},
        "Image::PackageMod:selected": {"image_url": _get_icons("package-mod-icon"), "color": _WHITE_100},
        "Image::PackageModDisabled": {"image_url": _get_icons("package-mod-icon"), "color": _WHITE_30},
        "Image::Ingestion": {"image_url": _get_icons("ingestion-icon"), "color": _WHITE_60},
        "Image::Ingestion:hovered": {"image_url": _get_icons("ingestion-icon"), "color": _WHITE_80},
        "Image::Ingestion:selected": {"image_url": _get_icons("ingestion-icon"), "color": _WHITE_100},
        "Image::IngestionDisabled": {"image_url": _get_icons("ingestion-icon"), "color": _WHITE_30},
        "Image::AITools": {"image_url": _get_icons("ai-tools-icon"), "color": _WHITE_60},
        "Image::AITools:hovered": {"image_url": _get_icons("ai-tools-icon"), "color": _WHITE_80},
        "Image::AITools:selected": {"image_url": _get_icons("ai-tools-icon"), "color": _WHITE_100},
        "Image::AIToolsDisabled": {"image_url": _get_icons("ai-tools-icon"), "color": _WHITE_30},
        "Image::NvidiaShort": {"image_url": _get_image("NVIDIA-logo-green-white"), "color": _WHITE_100},
        "Image::Preview": {"image_url": _get_icons("magnify-expand"), "color": _WHITE_60},
        "Image::Preview:hovered": {"image_url": _get_icons("magnify-expand"), "color": _WHITE_80},
        "Image::Refresh": {"image_url": _get_icons("refresh"), "color": _WHITE_60},
        "Image::Refresh:hovered": {"image_url": _get_icons("refresh"), "color": _WHITE_80},
        "Image::Refresh:disabled": {"image_url": _get_icons("refresh"), "color": _WHITE_30},
        "Image::Restore": {"image_url": _get_icons("restore"), "color": _WHITE_60},
        "Image::Restore:hovered": {"image_url": _get_icons("restore"), "color": _WHITE_80},
        "Image::Scope": {"image_url": _get_icons("scope"), "color": _WHITE_60},
        "Image::Xform": {"image_url": _get_icons("xform"), "color": _WHITE_80},
        "Image::TrashCan": {"image_url": _get_icons("trash-can"), "color": _WHITE_60},
        "Image::TrashCan:disabled": {"image_url": _get_icons("trash-can"), "color": _WHITE_30},
        "Image::TrashCan:hovered": {"image_url": _get_icons("trash-can"), "color": _WHITE_80},
        "Image::ModCreate": {"image_url": _get_icons("mod_create"), "color": _WHITE_80},
        "Image::ModEdit": {"image_url": _get_icons("mod_edit"), "color": _WHITE_80},
        "Image::ModOpen": {"image_url": _get_icons("mod_open"), "color": _WHITE_80},
        "Image::ModRemaster": {"image_url": _get_icons("mod_remaster"), "color": _WHITE_80},
        "Image::ModCreateHovered": {"image_url": _get_icons("mod_create"), "color": _BLUE_ACTION},
        "Image::ModEditHovered": {"image_url": _get_icons("mod_edit"), "color": _BLUE_ACTION},
        "Image::ModOpenHovered": {"image_url": _get_icons("mod_open"), "color": _BLUE_ACTION},
        "Image::ModRemasterHovered": {"image_url": _get_icons("mod_remaster"), "color": _BLUE_ACTION},
        "Image::Drag": {"image_url": _get_icons("drag_handle"), "color": _WHITE_30},
        "Image::Capture": {"image_url": _get_icons("database"), "color": _WHITE_80},
        "Image::Collection": {"image_url": _get_icons("link"), "color": _WHITE_80},
        "Image::Material": {"image_url": _get_icons("circle-opacity"), "color": _WHITE_80},
        "Image::Mesh": {"image_url": _get_icons("hexagon-outline"), "color": _WHITE_80},
        "Image::GeomSubset": {"image_url": _get_icons("hexagon-multiple-outline"), "color": _WHITE_80},
        "Image::Categories": {"image_url": _get_icons("categories"), "color": _WHITE_80},
        "Image::Categories:hovered": {"image_url": _get_icons("categories"), "color": _WHITE_100},
        "Image::CategoriesShown": {"image_url": _get_icons("category-on"), "color": _WHITE_80},
        "Image::CategoriesHidden": {"image_url": _get_icons("category-off"), "color": _WHITE_30},
        "Image::CategoriesWhite": {"image_url": _get_icons("categories_white"), "color": _WHITE_60},
        "Image::CategoriesWhite:hovered": {"image_url": _get_icons("categories_white"), "color": _WHITE_100},
        "Image::CategoriesDisabled": {"image_url": _get_icons("categories_white"), "color": _WHITE_30},
        "Image::TimerStatic": {"image_url": _get_icons("timer"), "color": _WHITE_80},
        "Image::CylinderLightStatic": {"image_url": _get_icons("light_cylinder"), "color": _WHITE_60},
        "Image::DiskLightStatic": {"image_url": _get_icons("light_disc"), "color": _WHITE_60},
        "Image::DistantLightStatic": {"image_url": _get_icons("light_distant"), "color": _WHITE_60},
        "Image::RectLightStatic": {"image_url": _get_icons("light_rect"), "color": _WHITE_60},
        "Image::SphereLightStatic": {"image_url": _get_icons("light_point"), "color": _WHITE_60},
        # TODO: Should add a proper Dome Light Icon
        "Image::DomeLightStatic": {"image_url": _get_icons("light_rect"), "color": _WHITE_60},
        "Image::RemixProject": {"image_url": _get_icons("ov_logo")},
        "Image::ShowInViewport": {
            "image_url": _get_icons("axis-arrow"),
            "color": _WHITE_20,
            "margin": 4,
        },
        "Image::ShowInViewport:hovered": {
            "image_url": _get_icons("axis-arrow"),
            "color": _WHITE_100,
            "margin": 4,
        },
        "ImagePropertiesPaneSectionTriangleCollapsed": {
            "image_url": _get_icons("disclosure-collapsed"),
            "color": _WHITE_60,
        },
        "ImagePropertiesPaneSectionTriangleExpanded": {
            "image_url": _get_icons("disclosure-expanded"),
            "color": _WHITE_60,
        },
        "Image::PropertiesPaneSectionInfo": {"image_url": _get_icons("info"), "color": _WHITE_60},
        "Image::PropertiesPaneSectionInfo:hovered": {"image_url": _get_icons("info"), "color": _WHITE_100},
        "Image::Tag": {"image_url": _get_icons("tag"), "color": _WHITE_60},
        "Image::EditTag": {"image_url": _get_icons("tag-edit"), "color": _WHITE_60},
        "Image::EditTagDisabled": {"image_url": _get_icons("tag-edit"), "color": _WHITE_30},
        "Image::EditTag:hovered": {"image_url": _get_icons("tag-edit"), "color": _WHITE_80},
        "Image::ArrowLeft": {"image_url": _get_icons("arrow-left"), "color": _WHITE_60},
        "Image::ArrowLeft:hovered": {"image_url": _get_icons("arrow-left"), "color": _WHITE_80},
        "Image::ArrowRight": {"image_url": _get_icons("arrow-right"), "color": _WHITE_60},
        "Image::ArrowRight:hovered": {"image_url": _get_icons("arrow-right"), "color": _WHITE_80},
        "Image::Filter": {"image_url": _get_icons("filter"), "color": _WHITE_60},
        "Image::Filter:hovered": {"image_url": _get_icons("filter"), "color": _WHITE_80},
        "Image::FilterActive": {"image_url": _get_icons("filter-multiple"), "color": _BLUE_ACTION},
        "Image::FilterActive:hovered": {"image_url": _get_icons("filter-multiple"), "color": _BLUE_SELECTED},
        "Image::WelcomePadDefault": {"color": 0x40000000, "border_radius": 12},
        "Image::WelcomePadImage": {"border_radius": 12},
        "Image::Install": {"image_url": _get_icons("download"), "color": _WHITE_60},
        "Image::Install:hovered": {"image_url": _get_icons("download"), "color": _WHITE_80},
        "Image::Install:disabled": {"image_url": _get_icons("download"), "color": _WHITE_30},
        "Image::Locate": {"image_url": _get_icons("folder_open"), "color": _WHITE_60},
        "Image::Locate:hovered": {"image_url": _get_icons("folder_open"), "color": _WHITE_80},
        "Image::Locate:disabled": {"image_url": _get_icons("folder_open"), "color": _WHITE_30},
        "Image::LogicGraph": {"image_url": _get_icons("LogicGraphIcon"), "color": _WHITE_60},
        "Image::LogicGraph:hovered": {"image_url": _get_icons("LogicGraphIcon"), "color": _WHITE_80},
        "Image::LogicGraph:selected": {"image_url": _get_icons("LogicGraphIcon"), "color": _WHITE_100},
        "Image::LogicGraphDisabled": {"image_url": _get_icons("LogicGraphIcon"), "color": _WHITE_30},
        "Image::LogicGraphStatic": {"image_url": _get_icons("LogicGraphIconThin"), "color": _WHITE_80},
        "Image::LogicGraphStatic:hovered": {"image_url": _get_icons("LogicGraphIconThin"), "color": _WHITE_80},
        "Image::LogicGraphStatic:selected": {"image_url": _get_icons("LogicGraphIconThin"), "color": _WHITE_100},
        "Image::LogicGraphStaticDisabled": {"image_url": _get_icons("LogicGraphIconThin"), "color": _WHITE_30},
        "Image::LogicGraphNodeStatic": {"image_url": _get_icons("LogicGraphNodeIconThin"), "color": _WHITE_80},
        "Image::Edit": {"image_url": _get_icons("pencil"), "color": _WHITE_60},
        "Image::Edit:hovered": {"image_url": _get_icons("pencil"), "color": _WHITE_80},
        "Image::Edit:disabled": {"image_url": _get_icons("pencil"), "color": _WHITE_30},
        "Image::Update": {"image_url": _get_icons("update"), "color": _WHITE_60},
        "Image::Update:hovered": {"image_url": _get_icons("update"), "color": _WHITE_80},
        "Image::Update:disabled": {"image_url": _get_icons("update"), "color": _WHITE_30},
        "Image::Uninstall": {"image_url": _get_icons("trash-can"), "color": _WHITE_60},
        "Image::Uninstall:hovered": {"image_url": _get_icons("trash-can"), "color": _WHITE_80},
        "Image::Uninstall:disabled": {"image_url": _get_icons("trash-can"), "color": _WHITE_30},
        "Image::Start": {"image_url": _get_icons("play"), "color": _GREEN_60},
        "Image::Start:hovered": {"image_url": _get_icons("play"), "color": _GREEN_80},
        "Image::Start:disabled": {"image_url": _get_icons("play"), "color": _GREEN_20},
        "Image::Stop": {"image_url": _get_icons("stop"), "color": _RED_60},
        "Image::Stop:hovered": {"image_url": _get_icons("stop"), "color": _RED_80},
        "Image::Stop:disabled": {"image_url": _get_icons("stop"), "color": _RED_20},
        "Image::Restart": {"image_url": _get_icons("restart"), "color": _WHITE_60},
        "Image::Restart:hovered": {"image_url": _get_icons("restart"), "color": _WHITE_80},
        "Image::Restart:disabled": {"image_url": _get_icons("restart"), "color": _WHITE_30},
        "ImageWithProvider::HeaderNvidiaTitle": {
            "color": _WHITE_60,
            "font_size": 32,
            "image_url": _get_fonts("NVIDIASans_A_Lt"),
        },
        "ImageWithProvider::TreePanelTitleItemTitle": {
            "color": _WHITE_60,
            "font_size": 16,
            "image_url": _get_fonts("NVIDIASans_A_Md"),
        },
        "ImageWithProvider::TreePanelTitleItemTitle:checked": {
            "color": _WHITE_80,
            "font_size": 16,
            "image_url": _get_fonts("NVIDIASans_A_Md"),
        },  # checked == hovered
        "Label::RemixAttrLabel": {"font_size": 14},
        "Label::WizardTitle": {
            "color": _WHITE_80,
            "font_size": 18,
            "font": ui.url.nvidia_bd,
        },
        "Label::WizardTitleActive": {
            "color": _BLUE_ACTION,
            "font_size": 18,
            "font": ui.url.nvidia_bd,
        },
        "Label::WizardDescription": {
            "color": _WHITE_80,
            "font_size": 18,
            "font": ui.url.nvidia_md,
        },
        "Rectangle::WizardPageButton": {
            "background_color": 0x0,
            "border_radius": 16,
        },
        "Rectangle::WizardPageButton:hovered": {
            "background_color": _GREY_42,
        },
        "Rectangle::WizardSeparator": {
            "background_color": _WHITE_10,
            "border_width": 0,
        },
        "Rectangle::DisabledOverlay": {
            "background_color": 0x80303030,  # 50% transparency background grey
        },
        "Rectangle::WizardBackground": {
            "background_color": _GREY_50,
        },
        "Rectangle::WizardTreeBackground": {"background_color": _GREY_32},
        "ImageWithProvider::TreePanelTitle": {
            "color": _WHITE_80,
            "font_size": 18,
            "image_url": _get_fonts("NVIDIASans_A_Md"),
        },
        "ImageWithProvider::TreePanelTitle:hovered": {
            "color": _WHITE_100,
            "font_size": 18,
            "image_url": _get_fonts("NVIDIASans_A_Md"),
        },
        "ImageWithProvider::TreePanelTitle:selected": {
            "color": _WHITE_100,
            "font_size": 18,
            "image_url": _get_fonts("NVIDIASans_A_Md"),
        },
        "ImageWithProvider::HeaderNavigatorTitle": {
            "color": _WHITE_100,
            "font_size": 20,
            "image_url": _get_fonts("NVIDIASans_A_Lt"),
        },
        "ImageWithProvider::HeaderNvidiaBackground": {
            "background_color": 0x99000000,
            "background_gradient_color": 0x00000000,
        },
        "ImageWithProvider::FooterLabel": {
            "color": _WHITE_80,
            "font_size": 14,
            "image_url": _get_fonts("NVIDIASans_A_Lt"),
        },
        "ImageWithProvider::FooterLabel:hovered": {
            "color": _WHITE_100,
            "font_size": 14,
            "image_url": _get_fonts("NVIDIASans_A_Lt"),
        },
        "ImageWithProvider::PropertiesWidgetLabel": {
            "color": _WHITE_70,
            "font_size": 14,
            "image_url": ui.url.nvidia_md,
        },
        "ImageWithProvider::PropertiesWidgetLabel:disabled": {
            "color": _WHITE_30,
            "font_size": 14,
            "image_url": ui.url.nvidia_md,
        },
        "ImageWithProvider::PropertiesPaneSectionTitle": {
            "color": _WHITE_70,
            "font_size": 13,
            "image_url": ui.url.nvidia_bd,
        },
        "ImageWithProvider::PropertiesPaneSectionTitle:disabled": {
            "color": _WHITE_30,
            "font_size": 13,
            "image_url": _get_fonts("NVIDIASans_A_Bd"),
        },
        "ImageWithProvider::SelectionGradient": {
            "background_color": 0x00303030,
            "background_gradient_color": _GREY_50,
        },
        "ImageWithProvider::SelectionGradient_hovered": {
            "background_color": 0x00453F2B,
            "background_gradient_color": 0xFF453F2B,  # hardened _BLUE_HOVERED over _GREY_50
        },
        "ImageWithProvider::SelectionGradient_selected": {
            "background_color": 0x00836C1D,
            "background_gradient_color": 0xFF836C1D,  # hardened _BLUE_SELECTED over _GREY_50
        },
        "ImageWithProvider::SelectionGradient_secondary": {
            "background_color": 0x00594E26,
            "background_gradient_color": 0xFF594E26,  # hardened _BLUE_SEMI_SELECTED over _GREY_50
        },
        "ImageWithProvider::WelcomePadItemTitle": {
            "color": _WHITE_100,
            "font_size": 18,
            "image_url": _get_fonts("NVIDIASans_A_Md"),
        },
        "ImageWithProvider::WelcomePadItemTitle:checked": {
            "color": _WHITE_30,
            "font_size": 18,
            "image_url": _get_fonts("NVIDIASans_A_Md"),
        },
        "ImageWithProvider::WelcomePadTitle": {
            "color": _WHITE_60,
            "font_size": 24,
            "image_url": _get_fonts("NVIDIASans_A_Md"),
        },
        "KeyboardKey": {"background_color": 0, "border_width": 1.5, "border_radius": 3},
        "KeyboardLabel": {},
        "Label::FooterLabel": {
            "color": _WHITE_80,
            "font_size": 18,
            "font": ui.url.nvidia_lt,
        },
        "Label::FooterLabel:hovered": {
            "color": _WHITE_100,
            "font_size": 18,
            "font": ui.url.nvidia_lt,
        },
        "Label::VersionLabel": {
            "color": _WHITE_40,
            "font_size": 18,
            "font": ui.url.nvidia_lt,
        },
        "Label::VersionLabel:hovered": {
            "color": _WHITE_60,
        },
        "Label::ProgressLabel": {"color": _WHITE_100},
        "Label::PropertiesWidgetLabel": {"color": _WHITE_70, "font_size": 18, "font": ui.url.nvidia_md},
        "Label::PropertiesWidgetValue": {"color": _WHITE_60, "font_size": 18, "font": ui.url.nvidia_rg},
        "Label::ExperimentalFeatureLabel": {"color": _WHITE_50, "font_size": 18, "font": ui.url.nvidia_md},
        "Label::USDPropertiesWidgetValueOverlay": {"color": _WHITE_20},
        "Button::HomeButton": {"background_color": _GREY_32},
        "Button::HomeButton:disabled": {"background_color": _GREY_50, "border_color": _WHITE_20},
        "Button::HomeButton:hovered": {"background_color": _GREY_70},
        "Button.Label::HomeButton": {"color": _WHITE_80, "font_size": 20, "font": ui.url.nvidia_md},
        "Label::HomeLabel": {"color": _WHITE_80, "font_size": 32, "font": ui.url.nvidia_md},
        "Label::HomeDiscreteLabel": {"color": _WHITE_60, "font_size": 18, "font": ui.url.nvidia_rg},
        "Label::HomeEmphasizedLabel": {"color": _WHITE_80, "font_size": 18, "font": ui.url.nvidia_md},
        "Rectangle::HomeInvalidProject": {"background_color": _RED_05},
        "Label::WelcomePadItemDescription": {"color": _WHITE_100, "font_size": 16},
        "Label::WelcomePadItemDescription:checked": {"color": _WHITE_30, "font_size": 16},
        "Label::PropertiesPaneSectionTreeItem": {"color": _WHITE_80, "font_size": 14},
        "Label::PropertiesPaneSectionTreeItem60": {"color": _WHITE_40, "font_size": 14},
        "Label::PropertiesPaneSectionCaptureTreeItemNoImage": {"color": _WHITE_80, "font_size": 18},
        "Label::PropertiesPaneSectionTitle": {
            "color": _WHITE_70,
            "font_size": 16,
            "font": ui.url.nvidia_bd,
        },
        "Label::PropertiesPaneSectionTitle:disabled": {
            "color": _WHITE_30,
            "font_size": 16,
            "image_url": ui.url.nvidia_bd,
        },
        "Label::HeaderNavigatorMenuItem": {"color": _WHITE_60, "font_size": 20},
        "Label::HeaderNavigatorMenuItem:selected": {"color": _WHITE_100, "font_size": 20},
        "Label::HeaderNavigatorMenuItem:hovered": {"color": _WHITE_80, "font_size": 20},
        "Label::MenuBurgerHotkey": {"color": _WHITE_60, "font_size": 12},
        "Label::TreePanelTitle": {"color": _WHITE_80, "font_size": 23, "font": ui.url.nvidia_md},
        "Label::TreePanelTitle:hovered": {"color": _WHITE_100, "font_size": 23, "font": ui.url.nvidia_md},
        "Label::TreePanelTitle:selected": {"color": _WHITE_100, "font_size": 23, "font": ui.url.nvidia_md},
        "Label::TreePanelTitleItemTitle": {"color": _WHITE_60, "font_size": 20, "font": ui.url.nvidia_md},
        "Label::TreePanelTitleItemTitle:checked": {
            "color": _WHITE_80,
            "font_size": 20,
            "font": ui.url.nvidia_md,
        },  # checked == hovered
        "TreePanelTitleItemTitleDisabled": {
            "color": _WHITE_30,
            "font_size": 20,
            "font": ui.url.nvidia_md,
        },
        "Label::TopBarTitle": {"color": _WHITE_80, "font_size": 23, "font": ui.url.nvidia_md},
        "Label::TopBarTitle:hovered": {"color": _WHITE_100, "font_size": 23, "font": ui.url.nvidia_md},
        "Label::TopBarTitle:selected": {"color": _WHITE_100, "font_size": 23, "font": ui.url.nvidia_md},
        "Label::Warning": {"color": _YELLOW, "font_size": 18},
        "Label::WelcomePadFooter": {"color": _WHITE_100, "font_size": 18},
        "Label::Placeholder": {"color": _WHITE_40},
        "Line::PropertiesPaneSectionTitle": {"color": _WHITE_20, "border_width": 1},
        "Line::WelcomePadTop": {"color": _WHITE_20, "border_width": 1},
        "Line::TreeSpacer": {"color": _BLUE_SELECTED, "border_width": 2},
        "Menu.Separator": {
            "color": _WHITE_20,
            "margin_height": 3,
            "border_width": 1.5,
        },
        "MenuBurger": {
            "background_color": _DARK_85,
            "border_radius": 8,
            "border_width": 0,
            "padding": 8,
            "background_selected_color": _BLUE_SELECTED,
        },
        "MenuBurgerItem": {"background_selected_color": _BLUE_HOVERED, "color": _WHITE_100},
        "MouseImage": {
            "image_url": _get_icons("mouse_wheel_dark"),
        },
        "PropertiesPaneSectionTreeItem": {"color": _WHITE_80, "font_size": 14},
        "PropertiesPaneSectionTreeItemError": {
            "color": _RED_80,
            "font_size": 14,
        },
        "ColorsWidgetFieldRead": {
            "background_color": _DARK_00,
            "color": 0x90FFFFFF,
            "border_color": 0x0,
            "font_size": 14,
        },
        "ColorsWidgetFieldReadMixed": {
            "background_color": _PALE_ORANGE_40,
            "color": 0x90FFFFFF,
            "border_color": 0x0,
            "font_size": 14,
        },
        "ColorWidget::ColorsWidgetFieldRead": {
            "border_color": _WHITE_20,
            "border_radius": 5,
        },
        "ColorWidget::ColorsWidgetFieldReadMixed": {
            "background_color": _PALE_ORANGE_40,
            "border_radius": 5,
        },
        "Rectangle::ColorsWidgetSeparator": {
            "background_color": _WHITE_10,
            "border_width": 0,
        },
        "FloatSliderField": {
            "draw_mode": ui.SliderDrawMode.FILLED,
            "background_color": _GREY_50,
            "secondary_color": _BLUE_SEMI_SELECTED,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _WHITE_20,
            "font_size": 14,
        },
        "FloatSliderFieldSelected": {
            "draw_mode": ui.SliderDrawMode.FILLED,
            "background_color": _GREY_50,
            "secondary_color": _BLUE_SELECTED,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _WHITE_40,
            "font_size": 14,
        },
        "FloatSliderFieldMixed": {
            "draw_mode": ui.SliderDrawMode.FILLED,
            "background_color": _GREY_50,
            "secondary_color": _PALE_ORANGE_60,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _WHITE_20,
            "font_size": 14,
        },
        "FloatSliderFieldRead": {
            "draw_mode": ui.SliderDrawMode.FILLED,
            "background_color": _GREY_70,
            "secondary_color": _BLUE_SEMI_SELECTED,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _WHITE_20,
            "font_size": 14,
        },
        "FloatSliderFieldReadMixed": {
            "draw_mode": ui.SliderDrawMode.FILLED,
            "background_color": _GREY_70,
            "secondary_color": _PALE_ORANGE_40,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _WHITE_20,
            "font_size": 14,
        },
        "FloatSliderFieldSelectedMixed": {
            "draw_mode": ui.SliderDrawMode.FILLED,
            "background_color": _GREY_50,
            "secondary_color": _PALE_ORANGE_60,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _WHITE_40,
            "font_size": 14,
        },
        "Rectangle::SelectableToolTipBackground": _DEFAULT_FIELD_READ_VALUE,
        "Rectangle::SelectableToolTipBackground:hovered": _DEFAULT_FIELD_READ_HOVERED_VALUE,
        "PropertiesWidgetField": {
            "background_color": _GREY_50,
            "color": _WHITE_80,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _WHITE_20,
            "font_size": 14,
        },
        "PropertiesWidgetField:hovered": {
            "background_color": _BLUE_HOVERED,
        },
        "PropertiesWidgetFieldMixed": _DEFAULT_FIELD_MIXED_VALUE,
        "PropertiesWidgetFieldRead": _DEFAULT_FIELD_READ_VALUE,
        "PropertiesWidgetFieldRead:hovered": _DEFAULT_FIELD_READ_HOVERED_VALUE,
        "PropertiesWidgetFieldReadMixed": _DEFAULT_FIELD_READ_ONLY_MIXED_VALUE,
        # Note: cannot be both Read (only) and Selected for editing
        "PropertiesWidgetFieldSelected": {
            "background_color": _DARK_40,
            "color": _WHITE_100,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _WHITE_40,
            "font_size": 14,
        },
        "PropertiesWidgetFieldSelectedMixed": {  # selected + mixed
            "background_color": _PALE_ORANGE_60,
            "color": _WHITE_100,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _WHITE_40,
            "font_size": 14,
        },
        # Note: bool field cannot be "selected"
        "PropertiesWidgetFieldBool": {
            "background_color": _GREY_32,  # make visible against _GREY_50 background
            "color": _WHITE_30,
        },
        "PropertiesWidgetFieldBoolRead": {
            "background_color": _GREY_70,
            "color": _WHITE_30,
        },
        "PropertiesWidgetFieldBoolMixed": {
            "background_color": _PALE_ORANGE_60,
            "color": _WHITE_30,
        },
        "PropertiesWidgetFieldBoolReadMixed": {
            "background_color": _PALE_ORANGE_40,
            "color": _WHITE_30,
        },
        "PropertiesWidgetLabel": {
            "color": _WHITE_70,
            "font_size": 14,
            "image_url": _get_fonts("NVIDIASans_A_Md"),
        },
        "PropertiesWidgetLabel:disabled": {
            "color": _WHITE_30,
            "font_size": 14,
            "image_url": _get_fonts("NVIDIASans_A_Md"),
        },
        "PropertiesWidgetLabelSelected": {
            "color": _WHITE_100,
            "font_size": 14,
            "image_url": _get_fonts("NVIDIASans_A_Md"),
        },
        "SelectionHistoryLabel": {
            "color": _WHITE_70,
            "font_size": 14,
        },
        "ImagePreviewCanvas": {
            "background_color": 0x0,
        },
        "Image::ActiveLayerBackground": {"image_url": _get_image("45deg-256x256-1px-2px-sp-black"), "color": _WHITE_60},
        "ScrollingFrame::ActiveLayerBackground": {"background_color": 0x6F9AAD09},
        "OverrideIndicatorForceDisabled": {"background_color": _GREY_70, "border_width": 0},
        "OverrideIndicator": {"background_color": _BLUE_ACTION, "border_width": 0},
        "OverrideIndicator:hovered": {"background_color": 0xFFFFDE88},
        "OverrideBackground": {"background_color": _GREY_42},
        "OverrideBackgroundHovered": {"background_color": _BLUE_HOVERED},
        "OverrideBackgroundSelected": {"background_color": _BLUE_SELECTED},
        "Rectangle::BackgroundButton": {"background_color": 0x33000000, "border_radius": 8},
        "Rectangle::WelcomePadContent": {"background_color": 0x0},
        "Rectangle::WelcomePadContent:hovered": {
            "background_color": 0x0,
            "border_width": 3,
            "border_color": _WHITE_20,
            "border_radius": 16,
        },
        "Rectangle::BackgroundWithBorder": {
            "background_color": 0x0,
            "border_width": 1,
            "border_color": _GREY_32,
            "border_radius": 8,
        },
        "Rectangle::BackgroundWithWhiteBorder": {
            "background_color": 0x33000000,
            "border_width": 1,
            "border_color": _WHITE_20,
            "border_radius": 4,
        },
        "Rectangle::PreviewWindowBackground": {"background_color": _GREY_42},
        "ScrollingFrame::PreviewWindowBackground": {"background_color": _GREY_42},
        "Rectangle::PropertiesPaneSectionWindowBackground": _DEFAULT_DARK_PANEL_BACKGROUND_VALUE,
        "Rectangle::TreePanelBackground": {"background_color": 0x33000000},
        "Rectangle::DarkBackgroound": {"background_color": _TRUE_DARK},
        "Rectangle::WorkspaceBackground": {"background_color": _GREY_50},
        "Rectangle::TreePanelBackgroundSplitter": {
            "background_color": 0x0,
            "border_width": 2,
            "border_color": _WHITE_20,
        },
        "Rectangle::TreePanelBackgroundSplitter:hovered": {
            "background_color": _WHITE_10,
            "border_width": 2,
            "border_color": _WHITE_60,
        },
        "Rectangle::TreePanelBackgroundSplitter:disabled": {
            "background_color": _GREY_50,
            "border_width": 2,
            "border_color": _GREY_50,
        },
        "ScrollingFrame::WorkspaceBackground": {"background_color": _GREY_50},
        "Rectangle::FooterBackground": {"background_color": 0x99000000},
        "Rectangle::PropertiesPaneSectionWindowImageBackground": _DEFAULT_DARK_PANEL_BACKGROUND_VALUE,
        "Rectangle::PropertiesPaneSectionWindowCaptureBackground": _DEFAULT_DARK_PANEL_BACKGROUND_VALUE,
        "Rectangle::PropertiesPaneSectionTreeManipulator": {
            "background_color": _WHITE_40,
            "border_radius": 2,
        },
        "Rectangle::MenuBurgerBackground": {"background_color": 0x0},
        "Rectangle::MenuBurgerFloatingBackground": {"background_color": 0x0},
        "Rectangle::MenuBurgerBackground:hovered": {"background_color": _BLUE_HOVERED},
        "Rectangle::MenuBurgerBackground:selected": {"background_color": _BLUE_SELECTED},
        "ScrollingFrame::PropertiesPaneSection": {"background_color": 0x0, "secondary_color": 0x12FFFFFF},
        "ScrollingFrame::TreePanelBackground": {"background_color": 0x0},
        "ScrollingFrame::WelcomePad": {"background_color": 0x0, "secondary_color": _WHITE_10},
        "ScrollingFrame::WelcomePadItem": {"background_color": 0x0, "secondary_color": _WHITE_10},
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
        "TreeView::TreePanel": {
            "background_color": 0x0,
            "background_selected_color": 0x0,
        },  # background_selected_color = hovered
        "TreeView::TreePanel:selected": {"background_color": _GREY_50},
        "TreeView::WelcomePad:selected": {"background_color": 0x0},
        "TreeView.Item": {"background_color": 0x0},
        "TreeView.Item:selected": {"background_color": _BLUE_SELECTED},
        "TreeView.Item.selected": {"background_color": _BLUE_SELECTED},
        "TreeView.Item.semi_selected": {"background_color": _BLUE_SEMI_SELECTED},
        "TreeView.Item.IsHovered": {"background_color": _BLUE_HOVERED},
        "TreeView.Item.Minus": {"image_url": _get_icons("disclosure-expanded"), "color": _WHITE_60},
        "TreeView.Item.Plus": {"image_url": _get_icons("disclosure-collapsed_h"), "color": _WHITE_60},
        "Image::FadeoutBG": {"image_url": _get_icons("fade-gradient")},
        # Stage Prim Picker Widget
        "Image::AngledArrowDown": {"image_url": _get_icons("disclosure-expanded"), "color": _WHITE_60},
        "Rectangle::StagePrimPickerClearBackground": {
            "background_color": _GREY_50,
            "border_radius": 8,
            "margin": 0,
            "padding": 0,
        },
        "Rectangle::StagePrimPickerClearBackground:hovered": {
            "background_color": _GREY_60,
        },
        "Rectangle::StagePrimPickerArrowBackground": {
            "background_color": _GREY_50,
            "border_radius": 8,
            "margin": 0,
            "padding": 0,
        },
        "Image::StagePrimPickerClear": {"image_url": _get_icons("close"), "color": _WHITE_60},
        "Image::StagePrimPickerClear:hovered": {"image_url": _get_icons("close"), "color": _WHITE_100},
        "Field::StagePrimPickerField": {
            "background_color": _GREY_50,
            "color": _WHITE_80,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _WHITE_20,
            "padding": 4,
            "font_size": 14,
        },
        "Field::StagePrimPickerField:hovered": {
            "background_color": _BLUE_HOVERED,
        },
        "Button::StagePrimPickerFieldShowMore": {"background_color": _GREY_50, "border_radius": 3, "padding": 4},
        "Button::StagePrimPickerFieldShowMore:hovered": {"background_color": _GREY_60},
        "Button::StagePrimPickerFieldShowMore:disabled": {"background_color": _GREY_40},
        "Button.Label::StagePrimPickerFieldShowMore:disabled": {"color": _WHITE_30},
        "Label::StagePrimPickerItem": {"alignment": ui.Alignment.LEFT_CENTER},
        "Field::StagePrimPickerSearch": {
            "background_color": _GREY_50,
            "border_width": 1,
            "border_radius": 3,
            "border_color": _WHITE_20,
            "padding": 4,
        },
        "Field::StagePrimPickerSearch:hovered": {
            "background_color": _GREY_60,
            "border_color": _WHITE_40,
        },
        "Label::StagePrimPickerSearchPlaceholder": {
            "color": _WHITE_30,
            "margin_width": 6,
        },
        "Label::StagePrimPickerHeaderText": {"color": _WHITE_80},
        "Label::StagePrimPickerHeaderTextBold": {"color": _WHITE_80, "font": ui.url.nvidia_md, "font_size": 16},
        "Window::StagePrimPickerDropdown": {
            "background_color": _GREY_50,
            "border_color": _GREY_60,
            "border_width": 1,
            "border_radius": 4,
        },
        "Rectangle::StagePrimPickerDropdownBackground": {"background_color": _GREY_50},
        # Backdrop Rename Popup
        "Window::BackdropRenamePopup": {
            "background_color": 0x0,
            "border_radius": 4,
        },
        "Rectangle::BackdropRenamePopupBackground": {
            "background_color": _GREY_50,
            "border_radius": 4,
        },
        "TreeView.ScrollingFrame::WelcomePad": {"background_color": 0x0},
        "ViewportStats::FloatField": {
            "background_color": 0,
        },
        "Viewport.Item.Background": {
            "background_color": cl.viewport_menubar_background,
            "border_radius": cl.viewport_menubar_border_radius,
            "padding": 1,
            "margin": 2,
        },
        "Viewport.Item.Hover": {
            "background_color": 0,
            "padding": 1,
            "margin": 1,
        },
        "Viewport.Item.Hover:hovered": {
            "background_color": cl.viewport_menubar_selection,
            "border_color": cl.viewport_menubar_selection_border_button,
            "border_width": 1.5,
        },
        "Viewport.Item.Hover:pressed": {
            "background_color": cl.viewport_menubar_selection,
            "border_color": cl.viewport_menubar_selection_border_button,
            "border_width": 1.5,
        },
        "Window": {"background_color": 0xFF0F0F0F},
        "Rectangle::TransparentBackground": {"background_color": 0x0},
        "Rectangle::TabBackground": {"background_color": _GREY_42},
        "Rectangle::Row": {"background_color": _GREY_42},
        "Rectangle::AlternateRow": {"background_color": _GREY_40},
        "Rectangle::ColumnSeparator": {"background_color": _WHITE_10},
        "Rectangle::LoadingBackground": {"background_color": 0x80303030},
        "Rectangle::Background_GREY_26": {"background_color": _GREY_26},
        "Rectangle::Background_GREY_60": {"background_color": _GREY_60},
        "Label::LoadingLabel": {
            "color": _WHITE_80,
            "font_size": 18,
            "font": ui.url.nvidia_md,
        },
        "ScrollingFrame::CategoriesFrame": {
            "background_color": _GREY_42,
            "padding": 8,
        },
        "ScrollingFrame::Background_GREY_50": {"background_color": _GREY_50},
        "Rectangle::CustomTag": {
            "background_color": _GREY_60,
            "padding": 2,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _GREY_70,
        },
        "Label::FadedLabel": {
            "color": _WHITE_30,
        },
        "Label::VirtualItemLabel": {
            "color": _WHITE_80,
            "font_size": 16,
            "font": ui.url.nvidia_md,
        },
        "Label::Color_WHITE_60": {"color": _WHITE_60},
    }
)
style.default = current_dict
