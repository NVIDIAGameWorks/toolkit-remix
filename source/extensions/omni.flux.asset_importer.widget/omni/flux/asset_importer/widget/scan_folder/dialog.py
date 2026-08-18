"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
from collections.abc import Callable
from pathlib import Path

from omni import ui
from omni.flux.asset_importer.core.scan_folder.scanner import ScannerCore
from omni.flux.asset_importer.core.data_models.constants import (
    SUPPORTED_ASSET_EXTENSIONS as _SUPPORTED_ASSET_EXTENSIONS,
)
from omni.flux.asset_importer.core.data_models.constants import (
    SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS,
)
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.file_pickers import open_file_picker as _open_file_picker
from omni.flux.utils.widget.hover import hover_helper as _hover_helper
from omni.flux.utils.widget.tree_widget import TreeWidget as _TreeWidget

from .model.delegate import Delegate
from .model.model import Model

_scanner_dialog = None


class ScanFolderWidget:
    """Build and coordinate controls for scanning and selecting directory files."""

    _LABEL_WIDTH = 64
    _ROW_HEIGHT = 24
    _ICON_WIDTH = 24
    _WIDGET_PADDING = 8
    _LINE_HEIGHT = 2
    _MANIPULATOR_HEIGHT = 4
    _SIZE_PERCENT_MANIPULATOR_WIDTH = 24

    def __init__(self, window, core):
        """Initialize the scanner controls.

        Args:
            window: Dialog controller that owns these controls.
            core: Scanner service used to find and dispatch selected files.
        """
        self._default_attr = {
            "_window": None,
            "_select_button": None,
            "_core": None,
            "_input_folder_field": None,
            "_input_folder_subscription": None,
            "_input_folder_tooltip": None,
            "_search_term_field": None,
            "_search_term_tooltip": None,
            "_found_items_layout": None,
            "_scan_button": None,
            "_model": None,
            "_delegate": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._window = window
        self._core = core
        self._model = Model()
        self._delegate = Delegate()

    def _scan_folder(self):
        """Scan the configured directory and display matching files."""
        input_folder = self._input_folder_field.model.get_value_as_string()
        if not input_folder or input_folder == ".":
            self._show_input_folder_error()
            return

        search_term = self._search_term_field.model.get_value_as_string()
        try:
            found = self._core.get_valid_files(Path(input_folder), search_term)
        except OSError:
            self._show_input_folder_error()
            return
        except re.error:
            self.refresh_ui()
            self._input_folder_field.style_type_name_override = "Field"
            self._input_folder_field.tooltip = self._input_folder_tooltip
            self._search_term_field.style_type_name_override = "FieldError"
            self._search_term_field.tooltip = "Enter a valid regular expression or clear the Search field."
            return

        self._input_folder_field.style_type_name_override = "Field"
        self._input_folder_field.tooltip = self._input_folder_tooltip
        self._search_term_field.style_type_name_override = "Field"
        self._search_term_field.tooltip = self._search_term_tooltip

        self._delegate.refresh()
        self._model.set_items(found)
        if found:
            self._select_button.enabled = True
        else:
            self._select_button.enabled = False

    def _show_input_folder_error(self):
        """Clear stale results and mark the directory field with actionable guidance."""
        self.refresh_ui()
        self._search_term_field.style_type_name_override = "Field"
        self._search_term_field.tooltip = self._search_term_tooltip
        self._input_folder_field.style_type_name_override = "FieldError"
        self._input_folder_field.tooltip = "Select a directory that exists and can be read."

    def refresh_ui(self):
        """Clear scan results and reset the dialog actions."""
        self._model.refresh()
        self._delegate.refresh()
        self._window.select_button.enabled = False
        if not self._input_folder_field.model.get_value_as_string():
            self._scan_button.enabled = False

    def send_paths(self):
        """Dispatch selected files by ingest type and close the dialog."""
        image_paths = []
        mesh_paths = []
        for item in self._model.get_item_children(None):
            value = item.value
            if not value:
                continue
            suffix = item.path.suffix.lower()
            if suffix in _SUPPORTED_ASSET_EXTENSIONS:
                mesh_paths.append(str(item.path))
            elif suffix in _SUPPORTED_TEXTURE_EXTENSIONS:
                image_paths.append(str(item.path))

        if image_paths:
            self._core.do("texture_import", image_paths)
        if mesh_paths:
            self._core.do("file_import", mesh_paths)

        self._window.close_dialog()

    def _set_input_folder(self, path):
        """Set the directory to scan and enable scanning when it is non-empty.

        Args:
            path: Directory selected by the file picker.
        """
        self._input_folder_field.model.set_value(path)

    def _on_input_folder_changed(self, model):
        """Synchronize Scan availability with the editable directory field.

        Args:
            model: Directory field value model.
        """
        self._scan_button.enabled = bool(model.get_value_as_string())

    def _get_input_directory(self):
        """Open a directory picker for the scan input."""
        _open_file_picker(
            "Select Directory to Scan",
            self._set_input_folder,
            lambda *_: None,
            apply_button_label="Select",
            select_directory=True,
        )

    def set_select_button(self, button):
        """Connect the result selection state to the dialog action button.

        Args:
            button: Select button enabled when at least one result is checked.
        """
        self._select_button = button
        self._delegate.selection_button = button

    def build_fields(self):
        """Build the directory, search, result, and scroll controls."""
        # Add horizontal padding
        with ui.HStack(spacing=self._WIDGET_PADDING):
            ui.Spacer(width=0, height=0)
            # Add vertical padding
            with ui.VStack(spacing=self._WIDGET_PADDING):
                ui.Spacer(width=0, height=0)
                # Build Folder row
                with ui.HStack(height=ui.Pixel(self._ROW_HEIGHT), spacing=self._WIDGET_PADDING):
                    self._input_folder_tooltip = "Select a directory to scan."
                    ui.Label(
                        "Directory:",
                        tooltip=self._input_folder_tooltip,
                        width=ui.Pixel(self._LABEL_WIDTH),
                        name="PropertiesWidgetLabel",
                    )
                    self._input_folder_field = ui.StringField(
                        tooltip=self._input_folder_tooltip,
                        identifier="input_folder_field",
                    )
                    ui.Image(
                        "",
                        name="OpenFolder",
                        identifier="select_scan_folder",
                        height=ui.Pixel(self._ROW_HEIGHT),
                        width=ui.Pixel(self._ICON_WIDTH),
                        mouse_pressed_fn=lambda x, y, b, m: self._get_input_directory(),
                        tooltip=self._input_folder_tooltip,
                    )
                # Build Search row
                with ui.HStack(height=ui.Pixel(self._ROW_HEIGHT), spacing=self._WIDGET_PADDING):
                    self._search_term_tooltip = (
                        "Search term can be a regex or a regular string. "
                        "If none, then it will pull up all files in the directory."
                    )
                    ui.Label(
                        "Search:",
                        tooltip=self._search_term_tooltip,
                        width=self._LABEL_WIDTH,
                        name="PropertiesWidgetLabel",
                    )
                    self._search_term_field = ui.StringField(
                        tooltip=self._search_term_tooltip,
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
                    self._input_folder_subscription = self._input_folder_field.model.subscribe_value_changed_fn(
                        self._on_input_folder_changed
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
                            self._tree = _TreeWidget(
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

    def _on_slide_x_changed(self, x: ui.Length) -> None:
        """Synchronize result-row scrolling with the horizontal manipulator.

        Args:
            x: Horizontal offset value emitted by the manipulator placer.
        """
        size_manip = self._manip_frame.computed_width / 100 * self._SIZE_PERCENT_MANIPULATOR_WIDTH
        max_offset_x = self._manip_frame.computed_width - size_manip
        offset_x = min(max(x.value, 0), max_offset_x)
        if offset_x != x.value:
            self._slide_placer.offset_x = offset_x

        item_path_scroll_frames = self._delegate.scroll_frames
        if item_path_scroll_frames and max_offset_x > 0:
            max_frame_scroll_x = max(frame.scroll_x_max for frame in item_path_scroll_frames.values())
            value = (max_frame_scroll_x / max_offset_x) * offset_x
            for frame in item_path_scroll_frames.values():
                frame.scroll_x = value

    def destroy(self) -> None:
        """Release subscriptions and UI references owned by the scanner controls."""
        # The owner is not a child resource; clearing it avoids recursively destroying ScanFolderUI.
        self._window = None
        _reset_default_attrs(self)


class ScanFolderUI:
    """Own the scan-directory dialog and its reusable scanner service."""

    _ROW_HEIGHT = 24
    _WIDGET_PADDING = 8
    _BUTTON_PADDING = 68
    _FRAME_WIDTH = 536

    def __init__(self, callbacks: dict[str, list[Callable]]):
        """Create the hidden scan dialog.

        Args:
            callbacks: Lists of callbacks keyed by the scanner actions that dispatch them.
        """
        self._core = ScannerCore(callbacks)
        self._default_attr = {
            "_window": None,
            "_widget": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._build_ui()

    def add_callback(self, callback: dict[str, list[Callable]]):
        """Register additional callbacks with the scanner service.

        Args:
            callback: Additional callback lists keyed by scanner action.
        """
        self._core.add_callback(callback)

    def close_dialog(self):
        """Hide the scan dialog."""
        self._window.visible = False

    def _build_ui(self):
        """Build the scan dialog and its action buttons."""
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
        """Reset and show the scan dialog."""
        self._widget.refresh_ui()
        self._window.visible = True

    def destroy(self):
        """Release references owned by the scan dialog."""
        if self._window is not None:
            self._window.destroy()
        _reset_default_attrs(self)


def destroy_scanner_dialog():
    """Destroy the shared scan dialog if it exists."""
    global _scanner_dialog
    if _scanner_dialog is not None:
        _scanner_dialog.destroy()
        _scanner_dialog = None


def scan_folder():
    """Show the shared scan dialog if it has been configured."""
    if _scanner_dialog is not None:
        _scanner_dialog.show()


def setup_scanner_dialog(callback: dict[str, list[Callable]]):
    """Create the shared scan dialog or extend its callbacks.

    Args:
        callback: Lists of callbacks keyed by the scanner actions that dispatch them.
    """
    global _scanner_dialog
    if _scanner_dialog is None:
        _scanner_dialog = ScanFolderUI(callbacks=callback)
    else:
        _scanner_dialog.add_callback(callback=callback)
