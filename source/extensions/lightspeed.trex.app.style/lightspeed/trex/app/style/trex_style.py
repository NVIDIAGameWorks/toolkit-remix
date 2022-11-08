# Copyright (c) 2018-2021, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
import carb.imgui
import omni.ui as ui
from omni.flux.utils.widget.resources import get_fonts as _get_fonts
from omni.flux.utils.widget.resources import get_icons as _get_icons
from omni.flux.utils.widget.resources import get_image as _get_image
from omni.kit.window.popup_dialog import message_dialog

# override global imgui style
imgui = carb.imgui.acquire_imgui()
imgui.push_style_color(carb.imgui.StyleColor.WindowShadow, carb.Float4(0, 0, 0, 0))

# default values
_BLUE_SELECTED = 0x66FFC700
_BLUE_SEMI_SELECTED = 0x33FFC700
_BLUE_HOVERED = 0x1AFFC700

_DARK_00 = 0x01000000  # 01 for alpha or it will show a default color
_DARK_40 = 0x66000000
_DARK_85 = 0xD9000000

_GREY_32 = 0xFF202020
_GREY_42 = 0xFF2A2A2A
_GREY_50 = 0xFF303030

_RED_05 = 0x0D0000FF

_WHITE_10 = 0x1AFFFFFF
_WHITE_20 = 0x33FFFFFF
_WHITE_30 = 0x4DFFFFFF
_WHITE_40 = 0x66FFFFFF
_WHITE_50 = 0x80FFFFFF
_WHITE_60 = 0x99FFFFFF
_WHITE_70 = 0xB3FFFFFF
_WHITE_80 = 0xCCFFFFFF
_WHITE_100 = 0xFFFFFFFF

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

_DEFAULT_DARK_PANEL_BACKGROUND_VALUE = {
    "background_color": _GREY_32,
    "border_width": 1,
    "border_color": _WHITE_20,
    "border_radius": 8,
}


# override the style of the message dialog
def override_dialog_get_style(style_value):  # noqa PLW0621
    style_value.update(
        {
            "Background": _DEFAULT_DARK_PANEL_BACKGROUND_VALUE,
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
        "Button::Main": {
            "background_color": _GREY_42,
            "border_width": 1,
            "border_color": _WHITE_20,
            "border_radius": 4,
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
        "Button::ExportButton:disabled": {
            "background_color": _WHITE_10,
            "border_width": 1,
            "border_color": _WHITE_30,
            "border_radius": 4,
            "margin": 2,
        },
        "Button::ExportButton:hovered": {
            "background_color": _WHITE_10,
            "border_width": 1,
            "border_color": _WHITE_30,
            "border_radius": 4,
            "margin": 2,
        },
        "Button.Label::NoBackground:disabled": {
            "color": _WHITE_30,
        },
        "CollapsableFrame::PropertiesPaneSection": {
            "background_color": 0x0,
            "secondary_color": 0x0,
        },
        "CollapsableFrame::PropertiesPaneSection:hovered": {
            "background_color": 0x0,
            "secondary_color": 0x0,
        },
        "Field": _DEFAULT_FIELD_READ_VALUE,
        "FieldError": _DEFAULT_FIELD_READ_ERROR_VALUE,
        "Field:hovered": _DEFAULT_FIELD_READ_HOVERED_VALUE,
        "FreeBezierCurve::HeaderNvidiaLine": {"border_width": 1, "color": _WHITE_30},
        "Image::Account": {"image_url": _get_icons("account-circle"), "color": _WHITE_50},
        "Image::Account:selected": {"image_url": _get_icons("account-circle"), "color": _WHITE_100},
        "Image::Account:hovered": {"image_url": _get_icons("account-circle"), "color": _WHITE_80},
        "Image::AddStatic": {"image_url": _get_icons("add"), "color": _WHITE_50},
        "Image::Add": {"image_url": _get_icons("add"), "color": _WHITE_60},
        "Image::Add:hovered": {"image_url": _get_icons("add"), "color": _WHITE_100},
        "Image::Eye": {"image_url": _get_icons("eye"), "color": _WHITE_60},
        "Image::Eye:hovered": {"image_url": _get_icons("eye"), "color": _WHITE_100},
        "Image::EyeOff": {"image_url": _get_icons("eye-off"), "color": _WHITE_60},
        "Image::EyeOff:hovered": {"image_url": _get_icons("eye-off"), "color": _WHITE_100},
        "Image::CreateLayer": {"image_url": _get_icons("create-layer"), "color": _WHITE_60},
        "Image::CreateLayer:hovered": {"image_url": _get_icons("create-layer"), "color": _WHITE_100},
        "Image::ImportLayer": {"image_url": _get_icons("import-layer"), "color": _WHITE_60},
        "Image::ImportLayer:hovered": {"image_url": _get_icons("import-layer"), "color": _WHITE_100},
        "Image::FolderClosed": {"image_url": _get_icons("folder-closed"), "color": _WHITE_80},
        "Image::Frame": {"image_url": _get_icons("frame"), "color": _WHITE_60},
        "Image::Frame:hovered": {"image_url": _get_icons("frame"), "color": _WHITE_100},
        "Image::Bookmark": {"image_url": _get_icons("bookmark"), "color": _WHITE_80},
        "Image::Hexagon": {"image_url": _get_icons("shape-hexagon"), "color": _WHITE_80},
        "Image::Nickname": {"image_url": _get_icons("nickname"), "color": _WHITE_60},
        "Image::Nickname:hovered": {"image_url": _get_icons("nickname"), "color": _WHITE_100},
        "Image::SubtractDisabled": {"image_url": _get_icons("subtract"), "color": _WHITE_30},
        "Image::Subtract": {"image_url": _get_icons("subtract"), "color": _WHITE_60},
        "Image::Subtract:hovered": {"image_url": _get_icons("subtract"), "color": _WHITE_100},
        "Image::SaveDisabled": {"image_url": _get_icons("save"), "color": _WHITE_30},
        "Image::Save": {"image_url": _get_icons("save"), "color": _WHITE_60},
        "Image::Save:hovered": {"image_url": _get_icons("save"), "color": _WHITE_100},
        "Image::LockDisabled": {"image_url": _get_icons("lock"), "color": _WHITE_30},
        "Image::Lock": {"image_url": _get_icons("lock"), "color": _WHITE_60},
        "Image::Lock:hovered": {"image_url": _get_icons("lock"), "color": _WHITE_100},
        "Image::UnlockDisabled": {"image_url": _get_icons("unlock"), "color": _WHITE_30},
        "Image::Unlock": {"image_url": _get_icons("unlock"), "color": _WHITE_60},
        "Image::Unlock:hovered": {"image_url": _get_icons("unlock"), "color": _WHITE_100},
        "Image::LayerActive": {"image_url": _get_icons("layers"), "color": _WHITE_100},
        "Image::Layer": {"image_url": _get_icons("layers"), "color": _WHITE_30},
        "Image::Layer:hovered": {"image_url": _get_icons("layers"), "color": _WHITE_60},
        "Image::More": {"image_url": _get_icons("ellipsis"), "color": _WHITE_60},
        "Image::More:hovered": {"image_url": _get_icons("ellipsis"), "color": _WHITE_100},
        "Image::TreePanelLinesBackground": {
            "image_url": _get_image("45deg-256x256-1px-2px-sp-black"),
            "color": _WHITE_30,
        },
        "Image::OpenFolder": {"image_url": _get_icons("folder_open"), "color": _WHITE_60},
        "Image::OpenFolder:hovered": {"image_url": _get_icons("folder_open"), "color": _WHITE_100},
        "Image::Import": {"image_url": _get_icons("import"), "color": _WHITE_60},
        "Image::Import:hovered": {"image_url": _get_icons("import"), "color": _WHITE_100},
        "Image::GoBack": {"image_url": _get_icons("go-back-icon"), "color": _WHITE_60},
        "Image::GoBack:hovered": {"image_url": _get_icons("go-back-icon"), "color": _WHITE_80},
        "Image::GoBack:selected": {"image_url": _get_icons("go-back-icon"), "color": _WHITE_100},
        "Image::HeaderNavigatorLogo": {"image_url": _get_image("NVIDIA-logo-header"), "color": _WHITE_100},
        "Image::MenuBurger": {"image_url": _get_icons("menu-burger"), "color": _WHITE_60},
        "Image::MenuBurger:hovered": {"image_url": _get_icons("menu-burger"), "color": _WHITE_80},
        "Image::MenuBurger:selected": {"image_url": _get_icons("menu-burger"), "color": _WHITE_100},
        "Image::NvidiaShort": {"image_url": _get_image("NVIDIA-logo-green-white"), "color": _WHITE_100},
        "Image::Preview": {"image_url": _get_icons("magnify-expand"), "color": _WHITE_60},
        "Image::Preview:hovered": {"image_url": _get_icons("magnify-expand"), "color": _WHITE_80},
        "Image::Scope": {"image_url": _get_icons("scope"), "color": _WHITE_60},
        "Image::Xform": {"image_url": _get_icons("xform"), "color": _WHITE_80},
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
        "Image::WelcomePadDefault": {"color": 0x40000000, "border_radius": 12},
        "Image::WelcomePadImage": {"border_radius": 12},
        "ImageWithProvider::HeaderNvidiaTitle": {
            "color": _WHITE_60,
            "font_size": 32,
            "image_url": _get_fonts("Barlow-Light"),
        },
        "ImageWithProvider::TreePanelTitleItemTitle": {
            "color": _WHITE_60,
            "font_size": 16,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::TreePanelTitleItemTitle:checked": {
            "color": _WHITE_80,
            "font_size": 16,
            "image_url": _get_fonts("Barlow-Medium"),
        },  # checked == hovered
        "ImageWithProviderTreePanelTitleItemTitleDisabled": {
            "color": _WHITE_30,
            "font_size": 16,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::TreePanelTitle": {
            "color": _WHITE_80,
            "font_size": 18,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::TreePanelTitle:hovered": {
            "color": _WHITE_100,
            "font_size": 18,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::TreePanelTitle:selected": {
            "color": _WHITE_100,
            "font_size": 18,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::HeaderNavigatorTitle": {
            "color": _WHITE_100,
            "font_size": 20,
            "image_url": _get_fonts("Barlow-Light"),
        },
        "ImageWithProvider::HeaderNvidiaBackground": {
            "background_color": 0x33000000,
            "background_gradient_color": 0x00000000,
        },
        "ImageWithProvider::FooterLabel": {
            "color": _WHITE_80,
            "font_size": 14,
            "image_url": _get_fonts("Barlow-Light"),
        },
        "ImageWithProvider::FooterLabel:hovered": {
            "color": _WHITE_100,
            "font_size": 14,
            "image_url": _get_fonts("Barlow-Light"),
        },
        "ImageWithProvider::PropertiesWidgetLabel": {
            "color": _WHITE_70,
            "font_size": 14,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::PropertiesWidgetLabel:disabled": {
            "color": _WHITE_30,
            "font_size": 14,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::PropertiesPaneSectionTitle": {
            "color": _WHITE_70,
            "font_size": 13,
            "image_url": _get_fonts("Barlow-Bold"),
        },
        "ImageWithProvider::PropertiesPaneSectionTitle:disabled": {
            "color": _WHITE_30,
            "font_size": 13,
            "image_url": _get_fonts("Barlow-Bold"),
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
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::WelcomePadItemTitle:checked": {
            "color": _WHITE_30,
            "font_size": 18,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::WelcomePadTitle": {
            "color": _WHITE_60,
            "font_size": 24,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "Label::USDPropertiesWidgetValueOverlay": {"color": _WHITE_20},
        "Label::WelcomePadItemDescription": {"color": _WHITE_100, "font_size": 16},
        "Label::WelcomePadItemDescription:checked": {"color": _WHITE_30, "font_size": 16},
        "Label::PropertiesPaneSectionTreeItem": {"color": _WHITE_80, "font_size": 14},
        "Label::PropertiesPaneSectionTreeItem60": {"color": _WHITE_40, "font_size": 14},
        "Label::PropertiesPaneSectionCaptureTreeItemNoImage": {"color": _WHITE_80, "font_size": 18},
        "Label::HeaderNavigatorMenuItem": {"color": _WHITE_60, "font_size": 20},
        "Label::HeaderNavigatorMenuItem:selected": {"color": _WHITE_100, "font_size": 20},
        "Label::HeaderNavigatorMenuItem:hovered": {"color": _WHITE_80, "font_size": 20},
        "Label::MenuBurgerHotkey": {"color": _WHITE_60, "font_size": 12},
        "Label::WelcomePadFooter": {"color": _WHITE_100, "font_size": 18},
        "Line::PropertiesPaneSectionTitle": {"color": _WHITE_20, "border_width": 1},
        "Line::PropertiesPaneSectionSeparator": {"color": _WHITE_10, "border_width": 1},
        "Line::WelcomePadTop": {"color": _WHITE_20, "border_width": 1},
        "Line::TreeSpacer": {"color": _BLUE_SELECTED, "border_width": 2},
        "MenuBurger": {
            "background_color": _DARK_85,
            "border_radius": 8,
            "border_width": 0,
            "padding": 8,
            "background_selected_color": _BLUE_SELECTED,
        },
        "MenuBurgerItem": {"background_selected_color": _BLUE_HOVERED, "color": _WHITE_100},
        "PropertiesWidgetField": {
            "background_color": _DARK_00,  # 01 for alpha or it will show a default color
            "color": _WHITE_80,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _WHITE_20,
            "font_size": 14,
        },
        "PropertiesWidgetField:hovered": {
            "background_color": _WHITE_20,
            "color": _WHITE_80,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _WHITE_30,
            "font_size": 14,
        },
        "ColorsWidgetFieldRead": {
            "background_color": _DARK_00,  # 01 for alpha or it will show a default color
            "color": 0x90FFFFFF,
            "border_color": 0x0,
            "font_size": 14,
        },
        "ColorWidget::ColorsWidgetFieldRead": {
            "border_color": _WHITE_20,
            "border_radius": 5,
        },
        "Rectangle::ColorsWidgetSeparator": {
            "background_color": _WHITE_10,
            "border_width": 0,
        },
        "PropertiesWidgetFieldRead": _DEFAULT_FIELD_READ_VALUE,
        "PropertiesWidgetFieldRead:hovered": _DEFAULT_FIELD_READ_HOVERED_VALUE,
        "PropertiesWidgetFieldSelected": {
            "background_color": _WHITE_30,
            "color": _WHITE_100,
            "border_width": 1,
            "border_radius": 5,
            "border_color": _WHITE_40,
            "font_size": 14,
        },
        "PropertiesWidgetLabel": {
            "color": _WHITE_70,
            "font_size": 14,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "PropertiesWidgetLabel:disabled": {
            "color": _WHITE_30,
            "font_size": 14,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "PropertiesWidgetLabelSelected": {
            "color": _WHITE_100,
            "font_size": 14,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImagePreviewCanvas": {
            "background_color": 0x0,
        },
        "OverrideIndicator": {"background_color": 0xFFFFC734, "border_width": 0},
        "OverrideIndicator:hovered": {"background_color": 0xFFFFDE88},
        "OverrideBackground": {"background_color": _DARK_40},
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
        "Rectangle::PreviewWindowBackground": {"background_color": _GREY_42},
        "ScrollingFrame::PreviewWindowBackground": {"background_color": _GREY_42},
        "Rectangle::PropertiesPaneSectionWindowBackground": _DEFAULT_DARK_PANEL_BACKGROUND_VALUE,
        "Rectangle::TreePanelBackground": {"background_color": 0x33000000},
        "Rectangle::WorkspaceBackground": {"background_color": _GREY_50},
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
        "TreeView.Item.Minus": {"image_url": _get_icons("disclosure-collapsed"), "color": _WHITE_60},
        "TreeView.Item.Plus": {"image_url": _get_icons("disclosure-collapsed_h"), "color": _WHITE_60},
        "TreeView.ScrollingFrame::WelcomePad": {"background_color": 0x0},
        "Window": {"background_color": 0xFF0F0F0F},
    }
)
style.default = current_dict
