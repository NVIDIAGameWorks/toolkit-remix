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

import omni.ui as ui
import pyperclip
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.label import create_label_with_font as _create_label_with_font

from .model import HEADER_DICT


class Delegate(ui.AbstractItemDelegate):
    """Tree of the metadata"""

    def __init__(self):
        super().__init__()
        self._default_attrs = {"_title_images_provider": None, "_context_menu": None}
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)

        self._title_images_provider = {}
        self._context_menu = ui.Menu("Context menu")

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        pass

    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        if column_id == 0:
            with ui.HStack(height=ui.Pixel(24)):
                ui.Spacer()
                with ui.VStack(width=0):
                    ui.Spacer(height=ui.Pixel(4))
                    style = ui.Style.get_instance()
                    current_dict = style.default
                    if "ImageWithProvider::ContentLibraryChooseMetadataTitle" not in current_dict:
                        # use regular labels
                        ui.Label(item.title)
                    else:
                        # use custom styled font
                        self._title_images_provider[item.title], _, _ = _create_label_with_font(
                            item.title, "ContentLibraryChooseMetadataTitle", remove_offset=False
                        )
                    ui.Spacer(height=ui.Pixel(4))
        elif column_id == 1:
            with ui.HStack(height=ui.Pixel(24)):
                ui.Spacer(width=ui.Pixel(8))
                with ui.VStack():
                    ui.Spacer()
                    ui.Label(
                        item.value,
                        name="ContentLibraryChooseMetadataValue",
                        alignment=ui.Alignment.LEFT,
                        height=0,
                        tooltip=item.value,
                        elided_text=True,
                        mouse_pressed_fn=lambda x, y, b, m: self._on_item_mouse_pressed(b, item),
                    )
                    ui.Spacer()

    def _on_item_mouse_pressed(self, button, item):
        if button != 1:
            return
        self._context_menu.clear()
        with self._context_menu:
            ui.MenuItem("Copy value", triggered_fn=lambda it=item: self.__copy_to_clipboard(it.value))
        self._context_menu.show()

    def __copy_to_clipboard(self, value):
        pyperclip.copy(value)

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def destroy(self):
        _reset_default_attrs(self)
