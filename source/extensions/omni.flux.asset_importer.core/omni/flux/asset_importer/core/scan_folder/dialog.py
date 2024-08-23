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

import re
from pathlib import Path
from typing import Callable

from omni import ui
from omni.flux.asset_importer.core.data_models.constants import (
    SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS,
)
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.file_pickers import open_file_picker as _open_file_picker

from .model import Delegate, Model

_scanner_dialog = None


class ScannerCore:
    def __init__(self, callbacks: dict[str, list[Callable]]):
        self._callbacks = callbacks

    def add_callback(self, callback: dict[str, list[Callable]]):
        for key, value in callback.items():
            if key in self._callbacks:
                self._callbacks[key].extend(value)
            else:
                self._callbacks[key] = value

    def do(self, action_type: str, paths: list):
        for callback in self._callbacks[action_type]:
            callback(paths)


class ScanFolderWidget:
    _BUTTON_WIDTH = 64
    _LABEL_WIDTH = 64
    _FIELD_HEIGHT = 24
    _ROW_HEIGHT = 24
    _ICON_WIDTH = 24
    _FIELD_WIDTH = 124
    _WIDGET_PADDING = 10

    def __init__(self, window, core):
        self._default_attr = {
            "_window": None,
            "_core": None,
            "_input_folder_field": None,
            "_search_term_field": None,
            "_found_items_layout": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._window = window
        self._core = core
        self._model = Model()
        self._delegate = Delegate()

    def _scan_folder(self):
        input_folder = Path(self._input_folder_field.model.get_value_as_string())
        search_term = self._search_term_field.model.get_value_as_string()
        search_exp = re.compile(search_term, re.IGNORECASE)

        found = []
        for file in input_folder.iterdir():
            if not file.is_file():
                continue
            if file.suffix == "meta":
                continue
            match = search_exp.search(str(file.name))
            if not match:
                continue

            found.append(file)

        self.refresh_ui()
        for found_file in found:
            self._model.add_item(found_file)

    def refresh_ui(self):
        self._model.refresh()
        self._delegate.refresh()

    def send_paths(self):
        image_paths = []
        mesh_paths = []
        for item in self._model.get_item_children(None):
            value = item.value
            if not value:
                continue
            suffix = item.path.suffix
            if suffix in [".usd", ".usda", ".usdc"]:
                mesh_paths.append(str(item.path))
            elif suffix in _SUPPORTED_TEXTURE_EXTENSIONS:
                image_paths.append(str(item.path))

        if image_paths:
            self._core.do("texture_import", image_paths)
        if mesh_paths:
            self._core.do("file_import", mesh_paths)

        self._window.close_dialog()

    def _set_input_folder(self, path):
        self._input_folder_field.model.set_value(path)

    def _get_input_directory(self):
        _open_file_picker(
            "Choose Folder to Scan",
            self._set_input_folder,
            lambda *_: self._window.close_dialog,
            apply_button_label="Choose",
            select_directory=True,
        )

    def build_fields(self):
        # Add horizontal padding
        with ui.HStack(spacing=self._WIDGET_PADDING):
            ui.Spacer(width=0, height=0)
            # Add vertical padding
            with ui.VStack(spacing=self._WIDGET_PADDING):
                ui.Spacer(width=0, height=0)
                # Build Folder row
                with ui.HStack(height=self._ROW_HEIGHT, spacing=self._WIDGET_PADDING):
                    folder_tooltip = "Select a folder to search."
                    ui.Label("Folder: ", tooltip=folder_tooltip, width=ui.Pixel(self._LABEL_WIDTH))
                    self._input_folder_field = ui.StringField(tooltip=folder_tooltip, identifier="input_folder_field")
                    ui.Image(
                        "",
                        name="OpenFolder",
                        identifier="select_scan_folder",
                        height=ui.Pixel(self._ROW_HEIGHT),
                        width=ui.Pixel(self._ICON_WIDTH),
                        mouse_pressed_fn=lambda x, y, b, m: self._get_input_directory(),
                        tooltip=folder_tooltip,
                    )
                # Build Search row
                with ui.HStack(height=self._ROW_HEIGHT, spacing=self._WIDGET_PADDING):
                    search_tooltip = (
                        "Search term can be a regex or a regular string. "
                        "If none, then it will pull up all files in folder."
                    )
                    ui.Label("Search:", tooltip=search_tooltip, width=self._LABEL_WIDTH)
                    self._search_term_field = ui.StringField(tooltip=search_tooltip, identifier="scan_search_field")
                    ui.Spacer(width=ui.Pixel(self._ICON_WIDTH))
                # Build Scan button
                with ui.HStack(height=self._ROW_HEIGHT, spacing=self._WIDGET_PADDING):
                    ui.Spacer(width=ui.Pixel(self._LABEL_WIDTH - 2))
                    ui.Button(
                        "Scan",
                        height=self._ROW_HEIGHT,
                        clicked_fn=self._scan_folder,
                        identifier="scan_folder_button",
                    )
                    ui.Spacer(width=ui.Pixel(self._ICON_WIDTH))
                # Build Separator
                ui.Line(height=0)
                # Build Results
                with ui.HStack(spacing=self._WIDGET_PADDING):
                    file_tooltip = "Select files to be added to ingestion queue."
                    ui.Label(
                        "Files:",
                        tooltip=file_tooltip,
                        width=self._LABEL_WIDTH,
                        alignment=ui.Alignment.LEFT_TOP,
                    )
                    with ui.ScrollingFrame(style_type_name_override="TreeView", tooltip=file_tooltip):
                        self._tree = ui.TreeView(
                            self._model, delegate=self._delegate, root_visible=False, header_visible=False
                        )
                        self._tree.set_selection_changed_fn(self._model.set_items_selected)
                ui.Spacer(width=0, height=0)


class ScanFolderUI:
    _ROW_HEIGHT = 24
    _WIDGET_PADDING = 10

    def __init__(self, callbacks: dict[str, Callable]):
        self._core = ScannerCore(callbacks)
        self._default_attr = {
            "_window": None,
            "_widget": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._build_ui()

    def add_callback(self, callback):
        self._core.add_callback(callback)

    def close_dialog(self):
        self._window.visible = False

    def _build_ui(self):
        self._window = ui.Window(title="Scan Folder", width=850, height=375)
        self._window.visible = False
        self._window.flags = ui.WINDOW_FLAGS_NO_RESIZE | ui.WINDOW_FLAGS_NO_COLLAPSE | ui.WINDOW_FLAGS_NO_SCROLLBAR
        self._widget = ScanFolderWidget(self, self._core)
        with self._window.frame:
            with ui.ZStack():
                ui.Rectangle(name="WorkspaceBackground")
                with ui.VStack():
                    self._widget.build_fields()
                    ui.Spacer(width=0, height=0)
                    with ui.HStack(height=ui.Pixel(self._ROW_HEIGHT)):
                        ui.Spacer()
                        ui.Button(text="Select", clicked_fn=self._widget.send_paths, identifier="choose_scanned_files")
                        ui.Button(text="Cancel", clicked_fn=self.close_dialog)
                        ui.Spacer()
                    ui.Spacer(height=ui.Pixel(self._WIDGET_PADDING))

    def show(self):
        self._widget.refresh_ui()
        self._window.visible = True

    def destroy(self):
        _reset_default_attrs(self)


def destroy_scanner_dialog():
    global _scanner_dialog
    if _scanner_dialog is not None:
        _scanner_dialog.destroy()
        _scanner_dialog = None


def scan_folder():
    if _scanner_dialog is not None:
        _scanner_dialog.show()


def setup_scanner_dialog(callback: dict[str, Callable]):
    global _scanner_dialog
    if _scanner_dialog is None:
        _scanner_dialog = ScanFolderUI(callbacks=callback)
    else:
        _scanner_dialog.add_callback(callback=callback)
