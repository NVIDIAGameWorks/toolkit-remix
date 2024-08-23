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

    def __init__(self):
        super().__init__()
        self._context_menu = None
        self._checkboxes = {}

    def refresh(self):
        self._checkboxes = {}

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        pass

    def _set_value(self, item):
        if item.value:
            item.value = False
        else:
            item.value = True

    def _change_selection(self, val, model):
        children = model.get_item_children(None)
        for child in children:
            if child.selected:
                child.value = val
                self._checkboxes[str(child.path)].model.set_value(val)

    def _show_context_menu(self, button, model):
        if button != 1:
            return
        if self._context_menu is not None:
            self._context_menu = None
        self._context_menu = ui.Menu("Context Menu")

        with self._context_menu:
            ui.MenuItem(
                "Check selected paths",
                identifier="check_paths",
                triggered_fn=lambda: self._change_selection(True, model),
            )
            ui.MenuItem(
                "Uncheck selected paths",
                identifier="uncheck_paths",
                triggered_fn=lambda: self._change_selection(False, model),
            )
        self._context_menu.show()

    # noinspection PyUnusedLocal
    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        if column_id == 0:
            with ui.HStack(mouse_pressed_fn=lambda x, y, b, m: self._show_context_menu(b, model)):
                ui.Label(str(item.path))
                ui.Spacer(width=ui.Pixel(10))
                checkbox = ui.CheckBox(mouse_pressed_fn=lambda x, y, b, m: self._set_value(item))
                checkbox.name = item.path.name
                checkbox.model.set_value(item.value)
                self._checkboxes[checkbox.name] = checkbox
