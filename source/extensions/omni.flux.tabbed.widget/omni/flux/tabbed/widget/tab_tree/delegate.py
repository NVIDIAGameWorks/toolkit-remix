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

from typing import TYPE_CHECKING, List

import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.color import hex_to_color as _hex_to_color
from omni.flux.utils.widget.gradient import create_gradient as _create_gradient
from omni.flux.utils.widget.label import create_label_with_font as _create_label_with_font
from omni.flux.utils.widget.resources import get_fonts as _get_fonts
from omni.flux.utils.widget.text_to_image import Rotation as _Rotation

from .model import HEADER_DICT  # noqa PLE0402

if TYPE_CHECKING:
    from .model import Item as _Item


class Delegate(ui.AbstractItemDelegate):
    """Delegate of the tree"""

    def __init__(self, rotation: _Rotation = None, horizontal: bool = True):
        super().__init__()
        self._default_attrs = {
            "_image_provider": None,
            "_rotation": None,
            "_background_rectangles": None,
            "_ext_name": None,
        }
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)
        self._rotation = rotation
        self._background_rectangles = {}
        self._image_provider = {}
        self._previous_selection = None

        self._gradient_image_provider = {}
        self._gradient_image_with_provider = {}

        style = ui.Style.get_instance()
        if "ImageWithProvider::SelectionGradient_secondary" not in style.default:
            style1 = 0xFF594E26
            style2 = 0x00594E26
        else:
            style1 = style.default["ImageWithProvider::SelectionGradient_secondary"]["background_gradient_color"]
            style2 = style.default["ImageWithProvider::SelectionGradient_secondary"]["background_color"]
        self.__gradient_color1 = _hex_to_color(style1)
        self.__gradient_color2 = _hex_to_color(style2)
        self.__gradient_width = 10
        self.__gradient_height = 10
        self._gradient_array = _create_gradient(
            self.__gradient_width,
            self.__gradient_height,
            self.__gradient_color1,
            self.__gradient_color2,
            (not horizontal, not horizontal, not horizontal, not horizontal),
        )

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        pass

    def build_widget(self, model, item: "_Item", column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        if column_id == 0:
            with ui.VStack(mouse_released_fn=lambda x, y, b, m: self._on_item_mouse_released(b, item)):
                with ui.ZStack():
                    self._background_rectangles[id(item)] = ui.Rectangle(
                        name="WorkspaceBackground", visible=item.selected
                    )
                    self._gradient_image_provider[id(item)] = ui.ByteImageProvider()
                    self._gradient_image_with_provider[item] = ui.ImageWithProvider(
                        self._gradient_image_provider[id(item)],
                        fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                        name="HeaderNvidiaBackground",
                        visible=False,
                        identifier="SelectedGradient",
                    )
                    self._gradient_image_provider[id(item)].set_bytes_data(
                        self._gradient_array.ravel().tolist(), [self.__gradient_width, self.__gradient_height]
                    )
                    with ui.VStack(identifier="TabLabel"):
                        ui.Spacer(height=ui.Pixel(8))
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(8))
                            style = ui.Style.get_instance()
                            current_dict = style.default
                            if "ImageWithProvider::TreePanelTitleItemTitle" not in current_dict:
                                self._ext_name = "omni.flux.tabbed.widget"
                                current_dict["ImageWithProvider::TreePanelTitleItemTitle"] = {
                                    "color": 0x99FFFFFF,
                                    "font_size": 16,
                                    "image_url": _get_fonts("NVIDIASans_A_Md", ext_name=self._ext_name),
                                }
                                style.default = current_dict
                            # we use a text to image because we want to rotate the text!
                            self._image_provider[id(item)], _, _ = _create_label_with_font(
                                item.title, "TreePanelTitleItemTitle", ext_name=self._ext_name, rotation=self._rotation
                            )
                            ui.Spacer(width=ui.Pixel(8))
                        ui.Spacer(height=ui.Pixel(8))

    def _on_item_mouse_released(self, button, item: "_Item"):
        if button != 0:
            return
        self.on_item_mouse_released(item)

    def on_item_mouse_released(self, item: "_Item"):
        for id_item, rectangle in self._background_rectangles.items():
            rectangle.visible = id_item == id(item)
        item.on_mouse_released()
        if item != self._previous_selection and item in self._gradient_image_with_provider:
            self.set_toggled_value(
                [item], any(widget.visible for widget in self._gradient_image_with_provider.values())
            )
        self._previous_selection = item

    def set_toggled_value(self, items: List["_Item"], value: bool):
        """
        Set the gradient visible (toggle on/off)

        Args:
            items: the item to toggle
            value: toggle or not
        """
        for _item, widget in self._gradient_image_with_provider.items():
            if _item in items:
                widget.visible = value
            else:
                widget.visible = False

    def get_toggled_values(self):
        """Get the visibility of the gradients"""
        return {item: widget.visible for item, widget in self._gradient_image_with_provider.items()}

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def destroy(self):
        if self._ext_name is not None:
            style = ui.Style.get_instance()
            current_dict = style.default
            del current_dict["ImageWithProvider::TreePanelTitleItemTitle"]
            style.default = current_dict
        _reset_default_attrs(self)
