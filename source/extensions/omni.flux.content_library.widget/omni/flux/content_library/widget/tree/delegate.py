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
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.label import create_label_with_font as _create_label_with_font

from .model import HEADER_DICT


class Delegate(ui.AbstractItemDelegate):
    """Delegate of the left tree"""

    def __init__(self):
        super().__init__()
        self._default_attrs = {"_title_images_provider": None, "_item_stack": None}
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)
        self._title_images_provider = {}
        self._item_stack = {}

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        pass

    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        if column_id == 0:
            self._item_stack[item.title] = ui.VStack(
                height=ui.Pixel(24),
                mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, item),
                mouse_pressed_fn=lambda x, y, b, m: self._on_item_mouse_pressed(b, item),
            )
            with self._item_stack[item.title]:
                ui.Spacer(height=ui.Pixel(4))
                style = ui.Style.get_instance()
                current_dict = style.default
                if "ImageWithProvider::TreePanelTitleItemTitle" not in current_dict:
                    # use regular labels
                    ui.Label(item.title)
                # use custom styled font
                elif item.title not in self._title_images_provider:
                    self._title_images_provider[item.title], _, _ = _create_label_with_font(
                        item.title, "TreePanelTitleItemTitle", remove_offset=True, offset_divider=2
                    )
                ui.Spacer(height=ui.Pixel(4))

    def _on_item_hovered(self, hovered, item):
        self._item_stack[item.title].checked = hovered

    def _on_item_mouse_pressed(self, button, item):
        if button != 0:
            return
        item.on_mouse_pressed()

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def destroy(self):
        _reset_default_attrs(self)
