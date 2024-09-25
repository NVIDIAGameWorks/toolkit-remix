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

import carb
from omni import ui
from omni.flux.asset_importer.core.data_models.constants import (
    SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS,
)
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.file_pickers import open_file_picker as _open_file_picker
from omni.flux.utils.widget.hover import hover_helper as _hover_helper

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
    _LABEL_WIDTH = 64
    _ROW_HEIGHT = 24
    _ICON_WIDTH = 24
    _WIDGET_PADDING = 8
    _LINE_HEIGHT = 2
    _MANIPULATOR_HEIGHT = 4
    _SIZE_PERCENT_MANIPULATOR_WIDTH = 24

    def __init__(self, window, core):
        self._default_attr = {
            "_window": None,
            "_select_button": None,
            "_core": None,
            "_input_folder_field": None,
            "_search_term_field": None,
            "_found_items_layout": None,
            "_scan_button": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._window = window
        self._core = core
        self._model = Model()
        self._delegate = Delegate()

    def _scan_folder(self):
        input_folder = self._input_folder_field.model.get_value_as_string()
        if not input_folder or input_folder == ".":
            carb.log_warn("Input directory is either invalid or does not exist. Unable to scan directory.")
            return
        input_folder = Path(input_folder)

        search_term = self._search_term_field.model.get_value_as_string()
        search_exp = re.compile(search_term, re.IGNORECASE)

        found = []
        for file in input_folder.iterdir():
            if not file.is_file():
                continue
            if file.suffix == ".meta":
                continue
            match = search_exp.search(str(file.name))
            if not match:
                continue

            found.append(file)

        self.refresh_ui()
        for found_file in found:
            self._model.add_item(found_file)
        if found:
            self._select_button.enabled = True

    def refresh_ui(self):
        self._model.refresh()
        self._delegate.refresh()
        self._window.select_button.enabled = False
        if not self._input_folder_field.model.get_value_as_string():
            self._scan_button.enabled = False

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
        if path:
            self._scan_button.enabled = True

    def _get_input_directory(self):
        _open_file_picker(
            "Select Directory to Scan",
            self._set_input_folder,
            lambda *_: self._window.close_dialog,
            apply_button_label="Select",
            select_directory=True,
        )

    def set_select_button(self, button):
        self._select_button = button
        self._delegate.set_selection_button(button)

    def build_fields(self):
        # Add horizontal padding
        with ui.HStack(spacing=self._WIDGET_PADDING):
            ui.Spacer(width=0, height=0)
            # Add vertical padding
            with ui.VStack(spacing=self._WIDGET_PADDING):
                ui.Spacer(width=0, height=0)
                # Build Folder row
                with ui.HStack(height=ui.Pixel(self._ROW_HEIGHT), spacing=self._WIDGET_PADDING):
                    folder_tooltip = "Select a directory to scan."
                    ui.Label(
                        "Directory:",
                        tooltip=folder_tooltip,
                        width=ui.Pixel(self._LABEL_WIDTH),
                        name="PropertiesWidgetLabel",
                    )
                    self._input_folder_field = ui.StringField(
                        tooltip=folder_tooltip,
                        identifier="input_folder_field",
                    )
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
                with ui.HStack(height=ui.Pixel(self._ROW_HEIGHT), spacing=self._WIDGET_PADDING):
                    search_tooltip = (
                        "Search term can be a regex or a regular string. "
                        "If none, then it will pull up all files in the directory."
                    )
                    ui.Label("Search:", tooltip=search_tooltip, width=self._LABEL_WIDTH, name="PropertiesWidgetLabel")
                    self._search_term_field = ui.StringField(
                        tooltip=search_tooltip,
                        identifier="scan_search_field",
                    )
                # Build Scan button
                with ui.HStack(height=ui.Pixel(self._ROW_HEIGHT), spacing=self._WIDGET_PADDING):
                    ui.Spacer(width=ui.Pixel(self._LABEL_WIDTH))
                    self._scan_button = ui.Button(
                        "Scan",
                        height=self._ROW_HEIGHT,
                        clicked_fn=self._scan_folder,
                        identifier="scan_folder_button",
                        enabled=False,
                    )
                # Build Separator
                with ui.HStack(height=ui.Pixel(self._LINE_HEIGHT)):
                    ui.Line(height=0, name="PropertiesPaneSectionTitle")
                # Build Results
                with ui.HStack(spacing=ui.Pixel(self._WIDGET_PADDING)):
                    file_tooltip = "Select files to be added to ingestion queue."
                    ui.Label(
                        "Files:",
                        tooltip=file_tooltip,
                        width=self._LABEL_WIDTH,
                        alignment=ui.Alignment.LEFT_TOP,
                        name="PropertiesWidgetLabel",
                    )
                    with ui.ZStack():
                        with ui.HStack():
                            ui.Rectangle(name="TreePanelBackground", spacing=ui.Pixel(self._WIDGET_PADDING))
                        with ui.ScrollingFrame(
                            name="PropertiesPaneSection",
                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        ):
                            self._tree = ui.TreeView(
                                self._model,
                                delegate=self._delegate,
                                root_visible=False,
                                header_visible=False,
                                padding=self._WIDGET_PADDING,
                            )
                            self._tree.set_selection_changed_fn(self._model.set_items_selected)
                with ui.HStack(height=self._MANIPULATOR_HEIGHT, spacing=ui.Pixel(self._WIDGET_PADDING)):
                    ui.Spacer(height=0, width=self._LABEL_WIDTH)
                    with ui.VStack(height=self._MANIPULATOR_HEIGHT, spacing=ui.Pixel(self._WIDGET_PADDING)):
                        self._manip_frame = ui.Frame(height=self._MANIPULATOR_HEIGHT)
                        with self._manip_frame:
                            self._slide_placer = ui.Placer(
                                draggable=True, height=self._MANIPULATOR_HEIGHT, drag_axis=ui.Axis.X
                            )
                            self._slide_placer.set_offset_x_changed_fn(self._on_slide_x_changed)
                            # Body
                            with self._slide_placer:
                                self._slider_manip = ui.Rectangle(
                                    width=ui.Percent(self._SIZE_PERCENT_MANIPULATOR_WIDTH),
                                    name="PropertiesPaneSectionTreeManipulator",
                                )
                                _hover_helper(self._slider_manip)
                ui.Spacer(width=0, height=0)

    def _on_slide_x_changed(self, x):
        size_manip = self._manip_frame.computed_width / 100 * self._SIZE_PERCENT_MANIPULATOR_WIDTH
        if x.value < 0:
            self._slide_placer.offset_x = 0
        elif x.value > self._manip_frame.computed_width - size_manip:
            self._slide_placer.offset_x = self._manip_frame.computed_width - size_manip

        item_path_scroll_frames = self._delegate.get_scroll_frames()
        if item_path_scroll_frames:
            max_frame_scroll_x = max(frame.scroll_x_max for frame in item_path_scroll_frames.values())
            value = (max_frame_scroll_x / (self._manip_frame.computed_width - size_manip)) * x
            for frame in item_path_scroll_frames.values():
                frame.scroll_x = value


class ScanFolderUI:
    _ROW_HEIGHT = 24
    _WIDGET_PADDING = 8
    _BUTTON_PADDING = 68
    _FRAME_WIDTH = 536

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
        self._window = ui.Window(title="Scan Directory for Input Files", width=550, height=575)
        self._window.visible = False
        self._window.flags = ui.WINDOW_FLAGS_NO_RESIZE | ui.WINDOW_FLAGS_NO_COLLAPSE | ui.WINDOW_FLAGS_NO_SCROLLBAR
        self._widget = ScanFolderWidget(self, self._core)
        with self._window.frame:
            with ui.ZStack(spacing=ui.Pixel(self._WIDGET_PADDING)):
                ui.Rectangle(name="WorkspaceBackground")
                with ui.VStack(width=ui.Pixel(self._FRAME_WIDTH), spacing=ui.Pixel(self._WIDGET_PADDING)):
                    self._widget.build_fields()
                    with ui.HStack(height=ui.Pixel(self._ROW_HEIGHT), spacing=ui.Pixel(self._WIDGET_PADDING)):
                        ui.Spacer(width=ui.Pixel(self._BUTTON_PADDING))
                        self.select_button = ui.Button(
                            text="Select", clicked_fn=self._widget.send_paths, identifier="choose_scanned_files"
                        )
                        self._widget.set_select_button(self.select_button)
                        ui.Button(text="Cancel", clicked_fn=self.close_dialog, identifier="cancel")
                    ui.Spacer(height=0, width=0)

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
