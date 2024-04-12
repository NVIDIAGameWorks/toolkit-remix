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
import os

import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .tree import delegate, model

_ICONS_DIR = os.path.dirname(__file__)
for _ in range(3):
    _ICONS_DIR = os.path.dirname(_ICONS_DIR)

_ICONS_DIR = os.path.join(_ICONS_DIR, "data", "icons")
DICT_ICONS = {
    "search": os.path.join(_ICONS_DIR, "search.svg"),
    "cross": os.path.join(_ICONS_DIR, "cross.svg"),
}


class AssetCaptureLocalizerWindow:
    def __init__(self):
        self.__default_attr = {
            "_model": None,
            "_delegate": None,
            "_window": None,
            "_tree": None,
            "_action_search_attr": None,
            "_label_search": None,
            "_cross_image": None,
            "_label_no_item": None,
        }
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self._delegate = delegate.Delegate()
        self._model = model.ListModel()

        self.__create_ui()

    def __create_ui(self):
        """Create the main UI"""
        window_name = "Asset capture localizer"
        self._window = ui.Window(window_name, name=window_name, width=1500, height=600, visible=False)

        with self._window.frame:
            with ui.VStack(spacing=8):
                with ui.HStack(height=22):
                    ui.Spacer()
                    with ui.ZStack(width=ui.Percent(25)):
                        with ui.HStack():
                            with ui.ZStack(width=20):
                                ui.Rectangle(name="Search")
                                ui.Image(str(DICT_ICONS["search"]), name="Search")
                            with ui.ZStack():
                                self._action_search_attr = ui.StringField()
                                self._action_search_attr.model.add_value_changed_fn(lambda m: self._filter_content())
                                with ui.HStack():
                                    ui.Spacer(width=8)
                                    self._label_search = ui.Label("Search", name="Search")
                            with ui.ZStack(width=20):
                                ui.Rectangle(name="Search")
                                self._cross_image = ui.Image(
                                    str(DICT_ICONS["cross"]),
                                    name="Cross",
                                    mouse_pressed_fn=lambda x, y, b, m: self._on_search_cross_clicked(),
                                    visible=False,
                                )
                            ui.Spacer(width=24)
                            self._label_no_item = ui.Label("No item found", visible=False, style={"color": 0xFF0000FF})
                    ui.Spacer()
                with ui.ScrollingFrame(
                    style_type_name_override="TreeView",
                ):
                    self._tree = ui.TreeView(
                        self._model,
                        delegate=self._delegate,
                        root_visible=False,
                        header_visible=True,
                        columns_resizable=True,
                        column_widths=[ui.Percent(40), ui.Percent(20), ui.Percent(5), ui.Percent(35)],
                    )
                ui.Button("Refresh", clicked_fn=self._on_refresh, height=24)

    def _filter_content(self):
        """Filter content by name"""
        filter_content_title_value = self._action_search_attr.model.as_string
        self._label_search.visible = not bool(filter_content_title_value)
        self._cross_image.visible = bool(filter_content_title_value)
        self._model.set_filter(filter_content_title_value)
        self._model.filter_items()
        self._show_no_item_label()

    def _show_no_item_label(self):
        items = self._model.get_item_children(None)
        self._label_no_item.visible = not bool(items)

    def _on_search_cross_clicked(self):
        """Called when the cross from the search box is clicked"""
        self._action_search_attr.model.set_value("")
        self._filter_content()

    def _on_refresh(self):
        self._model.refresh()
        self._show_no_item_label()

    def toggle_window(self):
        if self._window:
            self._window.visible = not self._window.visible
            if self._window.visible:
                self._on_refresh()

    def destroy(self):
        _reset_default_attrs(self)
