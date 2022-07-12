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


# override the style of the message dialog
def override_dialog_get_style(style_value):  # noqa PLW0621
    style_value.update(
        {
            "Background": {
                "background_color": 0xFF202020,
                "border_width": 1,
                "border_color": 0x66FFFFFF,
                "border_radius": 8,
            },
            "Button": {"background_color": 0x1AFFC700, "selected_color": 0xFF8A8777, "margin": 0},
            "Button:hovered": {"background_color": 0x66FFC700, "selected_color": 0xFF8A8777, "margin": 0},
            "Button.Label": {"color": 0xCCFFFFFF},
            "Button.Label:hovered": {"color": 0xFFFFFFFF},
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
        "CollapsableFrame::PropertiesPaneSection": {
            "background_color": 0x0,
            "secondary_color": 0x0,
        },
        "CollapsableFrame::PropertiesPaneSection:hovered": {
            "background_color": 0x0,
            "secondary_color": 0x0,
        },
        "Field::USDPropertiesWidgetValue": {
            "background_color": 0x0,
            "border_width": 1,
            "border_color": 0x33FFFFFF,
            "border_radius": 4,
        },
        "FreeBezierCurve::HeaderNvidiaLine": {"border_width": 1, "color": 0x4DFFFFFF},
        "Image::Account": {"image_url": _get_icons("account-circle"), "color": 0x80FFFFFF},
        "Image::Account:selected": {"image_url": _get_icons("account-circle"), "color": 0xFFFFFFFF},
        "Image::Account:hovered": {"image_url": _get_icons("account-circle"), "color": 0xCCFFFFFF},
        "Image::TreePanelLinesBackground": {
            "image_url": _get_image("45deg-256x256-1px-2px-sp-black"),
            "color": 0x40FFFFFF,
        },
        "Image::OpenFolder": {"image_url": _get_icons("folder_open"), "color": 0x99FFFFFF},
        "Image::OpenFolder:hovered": {"image_url": _get_icons("folder_open"), "color": 0xFFFFFFFF},
        "Image::Import": {"image_url": _get_icons("import"), "color": 0x99FFFFFF},
        "Image::Import:hovered": {"image_url": _get_icons("import"), "color": 0xFFFFFFFF},
        "Image::GoBack": {"image_url": _get_icons("go-back-icon"), "color": 0x99FFFFFF},
        "Image::GoBack:hovered": {"image_url": _get_icons("go-back-icon"), "color": 0xCCFFFFFF},
        "Image::GoBack:selected": {"image_url": _get_icons("go-back-icon"), "color": 0xFFFFFFFF},
        "Image::HeaderNavigatorLogo": {"image_url": _get_image("NVIDIA-logo-header"), "color": 0xFFFFFFFF},
        "Image::MenuBurger": {"image_url": _get_icons("menu-burger"), "color": 0x99FFFFFF},
        "Image::MenuBurger:hovered": {"image_url": _get_icons("menu-burger"), "color": 0xCCFFFFFF},
        "Image::MenuBurger:selected": {"image_url": _get_icons("menu-burger"), "color": 0xFFFFFFFF},
        "Image::NvidiaShort": {"image_url": _get_image("NVIDIA-logo-green-white"), "color": 0xFFFFFFFF},
        "ImagePropertiesPaneSectionTriangleCollapsed": {
            "image_url": _get_icons("disclosure-collapsed"),
            "color": 0x99FFFFFF,
        },
        "ImagePropertiesPaneSectionTriangleExpanded": {
            "image_url": _get_icons("disclosure-expanded"),
            "color": 0x99FFFFFF,
        },
        "Image::PropertiesPaneSectionInfo": {"image_url": _get_icons("info"), "color": 0x99FFFFFF},
        "Image::PropertiesPaneSectionInfo:hovered": {"image_url": _get_icons("info"), "color": 0xFFFFFFFF},
        "Image::TreeViewBranchCollapsed": {"image_url": _get_icons("disclosure-collapsed"), "color": 0xFFFFFFFF},
        "Image::TreeViewBranchExpanded": {"image_url": _get_icons("disclosure-expanded"), "color": 0xFFFFFFFF},
        "Image::WelcomePadDefault": {"color": 0x40000000, "border_radius": 12},
        "ImageWithProvider::HeaderNvidiaTitle": {
            "color": 0x99FFFFFF,
            "font_size": 32,
            "image_url": _get_fonts("Barlow-Light"),
        },
        "ImageWithProvider::TreePanelTitleItemTitle": {
            "color": 0x99FFFFFF,
            "font_size": 16,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::TreePanelTitleItemTitle:checked": {
            "color": 0xCCFFFFFF,
            "font_size": 16,
            "image_url": _get_fonts("Barlow-Medium"),
        },  # checked == hovered
        "ImageWithProviderTreePanelTitleItemTitleDisabled": {
            "color": 0x4DFFFFFF,
            "font_size": 16,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::TreePanelTitle": {
            "color": 0xCCFFFFFF,
            "font_size": 18,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::TreePanelTitle:hovered": {
            "color": 0xFFFFFFFF,
            "font_size": 18,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::TreePanelTitle:selected": {
            "color": 0xFFFFFFFF,
            "font_size": 18,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::HeaderNavigatorTitle": {
            "color": 0xFFFFFFFF,
            "font_size": 20,
            "image_url": _get_fonts("Barlow-Light"),
        },
        "ImageWithProvider::HeaderNvidiaBackground": {
            "background_color": 0x33000000,
            "background_gradient_color": 0x00000000,
        },
        "ImageWithProvider::FooterLabel": {
            "color": 0xCCFFFFFF,
            "font_size": 14,
            "image_url": _get_fonts("Barlow-Light"),
        },
        "ImageWithProvider::FooterLabel:hovered": {
            "color": 0xFFFFFFFF,
            "font_size": 14,
            "image_url": _get_fonts("Barlow-Light"),
        },
        "ImageWithProvider::PropertiesWidgetLabel": {
            "color": 0xB3FFFFFF,
            "font_size": 14,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::PropertiesPaneSectionTitle": {
            "color": 0xB3FFFFFF,
            "font_size": 13,
            "image_url": _get_fonts("Barlow-Bold"),
        },
        "ImageWithProvider::WelcomePadItemTitle": {
            "color": 0xFFFFFFFF,
            "font_size": 18,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "ImageWithProvider::WelcomePadTitle": {
            "color": 0x99FFFFFF,
            "font_size": 24,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "Label::USDPropertiesWidgetValueOverlay": {"color": 0x33FFFFFF},
        "Label::WelcomePadItemDescription": {"color": 0xFFFFFFFF, "font_size": 16},
        "Label::PropertiesPaneSectionCaptureTreeItem": {"color": 0xCCFFFFFF, "font_size": 14},
        "Label::PropertiesPaneSectionCaptureTreeItemNoImage": {"color": 0xCCFFFFFF, "font_size": 18},
        "Label::HeaderNavigatorMenuItem": {"color": 0x99FFFFFF, "font_size": 20},
        "Label::HeaderNavigatorMenuItem:selected": {"color": 0xFFFFFFFF, "font_size": 20},
        "Label::HeaderNavigatorMenuItem:hovered": {"color": 0xCCFFFFFF, "font_size": 20},
        "Label::WelcomePadFooter": {"color": 0xFFFFFFFF, "font_size": 18},
        "Line::PropertiesPaneSectionTitle": {"color": 0x33FFFFFF, "border_width": 1},
        "Line::WelcomePadTop": {"color": 0x26FFFFFF, "border_width": 1},
        "Menu": {"background_color": 0xFF1E1E1E, "color": 0xFFFFFFFF, "background_selected_color": 0xCCFFFFFF},
        "PropertiesWidgetField": {
            "background_color": 0x01000000,  # 01 for alpha or it will show a default color
            "color": 0xCCFFFFFF,
            "border_width": 1,
            "border_radius": 5,
            "border_color": 0x33FFFFFF,
            "font_size": 14,
        },
        "PropertiesWidgetField:hovered": {
            "background_color": 0x26FFFFFF,
            "color": 0xCCFFFFFF,
            "border_width": 1,
            "border_radius": 5,
            "border_color": 0x4DFFFFFF,
            "font_size": 14,
        },
        "PropertiesWidgetFieldRead": {
            "background_color": 0x01000000,  # 01 for alpha or it will show a default color
            "color": 0x90FFFFFF,
            "border_width": 1,
            "border_radius": 5,
            "border_color": 0x33FFFFFF,
            "font_size": 14,
        },
        "PropertiesWidgetFieldRead:hovered": {
            "background_color": 0x26FFFFFF,
            "color": 0xCCFFFFFF,
            "border_width": 1,
            "border_radius": 5,
            "border_color": 0x4DFFFFFF,
            "font_size": 14,
        },
        "PropertiesWidgetFieldSelected": {
            "background_color": 0x40FFFFFF,
            "color": 0xFFFFFFFF,
            "border_width": 1,
            "border_radius": 5,
            "border_color": 0x66FFFFFF,
            "font_size": 14,
        },
        "PropertiesWidgetLabel": {
            "color": 0xB3FFFFFF,
            "font_size": 14,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "PropertiesWidgetLabelSelected": {
            "color": 0xFFFFFFFF,
            "font_size": 14,
            "image_url": _get_fonts("Barlow-Medium"),
        },
        "Rectangle::WelcomePadContent": {"background_color": 0x0},
        "Rectangle::WelcomePadContent:hovered": {
            "background_color": 0x0,
            "border_width": 3,
            "border_color": 0x33FFFFFF,
            "border_radius": 16,
        },
        "Rectangle::PropertiesPaneSectionWindowBackground": {  # info tooltip
            "background_color": 0xFF202020,
            "border_width": 1,
            "border_color": 0x33FFFFFF,
            "border_radius": 8,
        },
        "Rectangle::TreePanelBackground": {"background_color": 0x33000000},
        "Rectangle::WorkspaceBackground": {"background_color": 0xFF303030},
        "Rectangle::FooterBackground": {"background_color": 0x99000000},
        "Rectangle::PropertiesPaneSectionWindowImageBackground": {
            "background_color": 0xFF202020,
            "border_width": 1,
            "border_color": 0x33FFFFFF,
            "border_radius": 8,
        },
        "Rectangle::PropertiesPaneSectionWindowCaptureBackground": {
            "background_color": 0xFF202020,
            "border_width": 1,
            "border_color": 0x33FFFFFF,
            "border_radius": 8,
        },
        "Rectangle::PropertiesPaneSectionCaptureTreeManipulator": {
            "background_color": 0x66FFFFFF,
            "border_radius": 2,
        },
        "Rectangle::MenuBurgerBackground": {"background_color": 0x0},
        "Rectangle::MenuBurgerBackground:hovered": {"background_color": 0x1AFFC734},
        "Rectangle::MenuBurgerBackground:selected": {"background_color": 0x4DFFC734},
        "ScrollingFrame::PropertiesPaneSection": {"background_color": 0x0, "secondary_color": 0x12FFFFFF},
        "ScrollingFrame::TreePanelBackground": {"background_color": 0x0},
        "TreeView::TreePanel": {
            "background_color": 0x0,
            "background_selected_color": 0x0,
        },  # background_selected_color = hovered
        "TreeView::TreePanel:selected": {"background_color": 0xFF303030},
        "TreeView::PropertiesPaneSectionCapture": {
            "background_color": 0x0,
            "background_selected_color": 0x1AFFC700,
        },  # background_selected_color = hovered
        "TreeView::PropertiesPaneSectionCapture:selected": {"background_color": 0x66FFC700},
        "TreeView::WelcomePad:selected": {"background_color": 0x0},
        "TreeView.ScrollingFrame::WelcomePad": {"background_color": 0x0},
        "Window": {"background_color": 0xFF0F0F0F},
    }
)
style.default = current_dict
