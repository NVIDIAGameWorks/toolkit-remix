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
from omni.flux.info_icon.widget import InfoIconWidget as _InfoIconWidget

from .model import Item, Model


class Delegate(ui.AbstractItemDelegate):
    """Delegate for TreeView"""

    _WIDGET_PADDING = 12
    _ROW_HORIZONTAL_SPACER = 8
    _ROW_VERTICAL_SPACER = 4
    _CHECKBOX_WIDTH = 24
    _ICON_DIMENSIONS = 16
    _ICON_BUFFER = 24
    _ROW_WIDTH = 100
    _ROW_HEIGHT = 24
    _WINDOW_WIDTH = 364

    def __init__(self):
        super().__init__()
        self._context_menu = None
        self._checkboxes = {}

    def refresh(self):
        self._checkboxes = {}

    def get_all_checkboxes(self):
        return self._checkboxes

    def _set_value(self, item: Item, model: Model):
        if item.value:
            item.value = False
        else:
            item.value = True
        self._change_selection(item.value, model, ignore=[item])

    def _change_selection(self, val: bool, model: Model, ignore: list = None):
        children = model.get_item_children(None)
        if not ignore:
            ignore = []
        for child in children:
            if child.selected and child not in ignore:
                child.value = val
                self._checkboxes[str(child.attribute)].model.set_value(val)

    # noinspection PyUnusedLocal
    def build_widget(self, model: Model, item: Item, column_id: int, level: int, expanded: bool = False) -> None:
        """Create a widget per item"""
        if item is None:
            return
        if column_id == 0:
            with ui.VStack(height=ui.Pixel(self._ROW_HEIGHT), width=ui.Pixel(self._WINDOW_WIDTH)):
                ui.Spacer(height=ui.Pixel(self._ROW_VERTICAL_SPACER))
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(self._ROW_HORIZONTAL_SPACER))
                    checkbox = ui.CheckBox(
                        mouse_pressed_fn=lambda x, y, b, m: self._set_value(item, model),
                        width=ui.Pixel(self._CHECKBOX_WIDTH),
                        tooltip=str(item.tooltip),
                    )
                    checkbox.name = item.attribute
                    checkbox.model.set_value(item.value)
                    self._checkboxes[checkbox.name] = checkbox
                    ui.Label(str(item.name), alignment=ui.Alignment.LEFT, tooltip=checkbox.tooltip)
                    ui.Spacer()
                    _InfoIconWidget("\n".join(item.description))
                    ui.Spacer(width=ui.Pixel(self._ICON_BUFFER))
                ui.Spacer(height=ui.Pixel(self._ROW_VERTICAL_SPACER))
