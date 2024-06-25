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

from .tree_model import HEADER_DICT  # noqa PLE0402


class Delegate(ui.AbstractItemDelegate):
    def __init__(self):
        super().__init__()
        self._default_attrs = {"_frames": None, "_labels": None, "_widget_name": None, "_style": None}
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)
        self._style = ui.Style.get_instance().default.copy()
        self._update_default_style()
        self._frames = {}
        self._labels = {}

    def _update_default_style(self):
        """
        This widget generate image from text. It needs to read keys from a the global style.
        If those keys doesn't exist, we add them here (or it will crash). With this, the widget will work even without
        global style that sets those keys
        """
        if "Label::ContentViewerWidgetItemListTitle" not in self._style:
            self._style["Label::ContentViewerWidgetItemListTitle"] = {"color": 0x99FFFFFF, "font_size": 14}
            self._style["Label::ContentViewerWidgetItemListTitle:selected"] = {"color": 0xFFFFFFFF, "font_size": 14}
            self._style["Label::ContentViewerWidgetItemListTitle:hovered"] = {"color": 0xCCFFFFFF, "font_size": 14}

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        pass

    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        self._widget_name = f"{item.content_data.title}_{column_id}"
        grid_size = item.get_current_grid_scale_size()
        if not grid_size:
            grid_size = 100
        frame = ui.Frame(height=ui.Pixel(item.get_grid_row_height() * (grid_size / 100)))
        if item.content_data.title in self._frames:
            self._frames[item.content_data.title][self._widget_name] = frame
        else:
            self._frames[item.content_data.title] = {self._widget_name: frame}
        with self._frames[item.content_data.title][self._widget_name]:
            if column_id == 0:
                with ui.VStack(
                    mouse_pressed_fn=lambda x, y, b, m: self._on_item_mouse_pressed(x, y, b, m, item),
                    mouse_released_fn=lambda x, y, b, m: self._on_item_mouse_released(x, y, b, m, item),
                    mouse_moved_fn=lambda x, y, b, m: self._on_item_mouse_moved(x, y, b, m, item),
                ):
                    if hasattr(item.content_data, "image_path_fn") and item.content_data.image_path_fn:
                        ui.Image(
                            item.content_data.image_path_fn(),  # no need for async, delegate already async
                            fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                        )
                    else:
                        ui.Image("", fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT)
            elif column_id == 1:
                with ui.HStack(
                    mouse_pressed_fn=lambda x, y, b, m: self._on_item_mouse_pressed(x, y, b, m, item),
                    mouse_released_fn=lambda x, y, b, m: self._on_item_mouse_released(x, y, b, m, item),
                    mouse_moved_fn=lambda x, y, b, m: self._on_item_mouse_moved(x, y, b, m, item),
                ):
                    ui.Spacer(width=ui.Pixel(8))
                    with ui.VStack():
                        ui.Spacer(height=ui.Pixel(4))

                        grid_size = item.get_current_grid_scale_size()
                        if not grid_size:
                            grid_size = 100
                        updated_style = self._style["Label::ContentViewerWidgetItemListTitle"].copy()
                        updated_style["font_size"] = updated_style["font_size"] * (grid_size / 100)

                        label = ui.Label(
                            item.content_data.title,
                            name="ContentViewerWidgetItemListTitle",
                            style=self._get_label_style(item),
                        )
                        if item.content_data.title in self._labels:
                            self._labels[item.content_data.title][self._widget_name] = label
                        else:
                            self._labels[item.content_data.title] = {self._widget_name: label}
                        ui.Spacer(height=ui.Pixel(4))
                    ui.Spacer(width=ui.Pixel(8))

        if item.content_data.title in self._frames:
            item.set_list_root_frames(self._frames[item.content_data.title])
        if item.content_data.title in self._labels:
            item.set_list_root_labels(self._labels[item.content_data.title])

    def _get_label_style(self, item):
        grid_size = item.get_current_grid_scale_size()
        if not grid_size:
            grid_size = 100
        updated_style = self._style["Label::ContentViewerWidgetItemListTitle"].copy()
        updated_style["font_size"] = updated_style["font_size"] * (grid_size / 100)
        return updated_style

    def _on_item_mouse_pressed(self, x, y, b, m, item):  # noqa PLC0103
        item.on_mouse_clicked(x, y, b, m)

    def _on_item_mouse_released(self, x, y, b, m, item):  # noqa PLC0103
        item.on_mouse_released(x, y, b, m)

    def _on_item_mouse_moved(self, x, y, b, m, item):  # noqa PLC0103
        item.on_mouse_moved(x, y, b, m)

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def destroy(self):
        _reset_default_attrs(self)
