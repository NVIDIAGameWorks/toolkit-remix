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


class Delegate(ui.AbstractItemDelegate):
    """Delegate for TreeView"""

    _WIDGET_PADDING = 16
    _ROW_HEIGHT = 24
    _ROW_WIDTH = 600
    _LABEL_HEIGHT = 16
    _CHECKBOX_WIDTH = 24
    _ROW_PADDING = 4

    def __init__(self):
        super().__init__()
        self._context_menu = None
        self._checkboxes = {}

    def get_checkboxes(self):
        return self._checkboxes

    def refresh(self):
        self._checkboxes = {}

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        pass

    def _set_value(self, item, model):
        if item.value:
            item.value = False
        else:
            item.value = True

        # From all the selected children, loop through to set new value.
        # Secondly, gather values to see if the Select button should be enabled or not.
        values = []
        change_value = item.value
        for child in model.get_item_children(None):
            if not child.selected:
                values.append(child.value)
                continue
            if child == item:
                continue
            child.value = change_value
            self._checkboxes[child.texture_type].model.set_value(change_value)
            values.append(child.value)

    # noinspection PyUnusedLocal
    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        if column_id == 0:
            with ui.VStack(height=ui.Pixel(self._ROW_HEIGHT)):
                ui.Spacer(height=ui.Pixel(self._ROW_PADDING))
                with ui.HStack(
                    height=ui.Pixel(self._LABEL_HEIGHT),
                ):
                    ui.Spacer(width=ui.Pixel(self._WIDGET_PADDING))
                    checkbox = ui.CheckBox(
                        mouse_pressed_fn=lambda x, y, b, m: self._set_value(item, model),
                        width=ui.Pixel(self._CHECKBOX_WIDTH),
                    )
                    checkbox.name = item.texture_type
                    checkbox.model.set_value(item.value)
                    self._checkboxes[checkbox.name] = checkbox
                    ui.Label(item.name, tooltip=item.name, identifier="texture_item")
                ui.Spacer(height=ui.Pixel(self._ROW_PADDING))
