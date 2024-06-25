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

import functools
from typing import Optional

import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .model import HEADER_DICT  # noqa PLE0402


class Delegate(ui.AbstractItemDelegate):
    """Delegate of the tree"""

    def __init__(self):
        super().__init__()
        self._default_attrs = {
            "_item_stack": None,
            "_icon_stack": None,
            "_subs_item_enabled": None,
            "_subs_branch_item_enabled": None,
        }
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)
        self._icon_stack = {}
        self._item_stack = {}
        self._subs_item_enabled = {}
        self._subs_branch_item_enabled = {}

    def get_item_widget(self, item) -> Optional[ui.Widget]:
        return self._item_stack.get(id(item))

    def get_icon_item_widget(self, item) -> Optional[ui.Widget]:
        return self._icon_stack.get(id(item))

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        if column_id == 0:
            if self._icon_stack is None:
                self._icon_stack = {}
            self._icon_stack[id(item)] = ui.HStack(
                height=ui.Pixel(24),
                mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, item),
                mouse_pressed_fn=lambda x, y, b, m: self._on_item_mouse_pressed(b, item),
            )
            self._icon_stack[id(item)].enabled = item.enabled
            with self._icon_stack[id(item)]:
                ui.Spacer(width=ui.Pixel((16 * level) + (4 * level)))
                with ui.VStack(mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, item)):
                    ui.Spacer(height=ui.Pixel(4))
                    if model.can_item_have_children(item):
                        # Draw the +/- icon
                        image_name = "Expanded" if expanded else "Collapsed"
                        widget = ui.Image(
                            "", width=ui.Pixel(16), height=ui.Pixel(16), name=f"TreeViewBranch{image_name}"
                        )
                    else:
                        widget = ui.Image(
                            "", width=ui.Pixel(16), height=ui.Pixel(16), name=f"TreeViewBranch{item.component_type}"
                        )
                    self._on_branch_item_enabled(widget, item, item.enabled)
                    if id(item) not in self._subs_branch_item_enabled:
                        self._subs_branch_item_enabled[id(item)] = item.subscribe_item_enabled(
                            functools.partial(self._on_branch_item_enabled, widget, item)
                        )
                    ui.Spacer(height=ui.Pixel(4))
                ui.Spacer(width=ui.Pixel(4))

    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        if column_id == 0:
            if self._item_stack is None:
                self._item_stack = {}
            self._item_stack[id(item)] = ui.VStack(
                height=ui.Pixel(24),
                mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, item),
                mouse_pressed_fn=lambda x, y, b, m: self._on_item_mouse_pressed(b, item),
            )
            self._item_stack[id(item)].enabled = item.enabled
            with self._item_stack[id(item)]:
                ui.Spacer(height=ui.Pixel(4))
                title_label = ui.Label(item.title, name="TreePanelTitleItemTitle")
                self._on_item_enabled(title_label, item, item.enabled)
                ui.Spacer(height=ui.Pixel(4))
            if id(item) not in self._subs_item_enabled:
                self._subs_item_enabled[id(item)] = item.subscribe_item_enabled(
                    functools.partial(self._on_item_enabled, title_label, item)
                )

    def _on_item_enabled(self, title_label, item, enabled):
        title_label.style_type_name_override = "" if enabled else "TreePanelTitleItemTitleDisabled"
        self._item_stack[id(item)].enabled = enabled

    def _on_branch_item_enabled(self, title_label, item, enabled):
        title_label.style_type_name_override = "" if enabled else f"Image{title_label.name}Disabled"
        self._icon_stack[id(item)].enabled = enabled

    def _on_item_hovered(self, hovered, item):
        self._icon_stack[id(item)].checked = hovered
        self._item_stack[id(item)].checked = hovered

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
