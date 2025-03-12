# noqa PLC0302
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

import asyncio
import functools
import os
from pathlib import Path

import carb.input
import omni.appwindow
import omni.client
import omni.kit.usd.layers as _layers
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import GAME_READY_ASSETS_FOLDER as _GAME_READY_ASSETS_FOLDER
from lightspeed.common.constants import READ_USD_FILE_EXTENSIONS_OPTIONS as _READ_USD_FILE_EXTENSIONS_OPTIONS
from lightspeed.common.constants import REMIX_CAPTURE_FOLDER as _REMIX_CAPTURE_FOLDER
from lightspeed.error_popup.window import ErrorPopup as _ErrorPopup
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.capture.core.shared import Setup as CaptureCoreSetup
from lightspeed.trex.capture_tree.model import CaptureTreeDelegate, CaptureTreeModel
from lightspeed.trex.replacement.core.shared import Setup as ReplacementCoreSetup
from lightspeed.trex.utils.widget import TrexMessageDialog
from omni.flux.property_widget_builder.model.file import FileAttributeItem as _FileAttributeItem
from omni.flux.property_widget_builder.model.file import FileDelegate as _FileDelegate
from omni.flux.property_widget_builder.model.file import FileModel as _FileModel
from omni.flux.property_widget_builder.model.file import get_file_listener_instance as _get_file_listener_instance
from omni.flux.property_widget_builder.widget import PropertyWidget as _PropertyWidget
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.flux.utils.common.decorators import ignore_function_decorator_async as _ignore_function_decorator_async
from omni.flux.utils.common.decorators import sandwich_attrs_function_decorator as _sandwich_attrs_function_decorator
from omni.flux.utils.widget.collapsable_frame import (
    PropertyCollapsableFrameWithInfoPopup as _PropertyCollapsableFrameWithInfoPopup,
)
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker
from omni.flux.utils.widget.hover import hover_helper as _hover_helper

from .mod_file_picker_create import open_file_picker_create


class ModSetupPane:

    DEFAULT_CAPTURE_TREE_FRAME_HEIGHT = 200
    SIZE_PERCENT_MANIPULATOR_WIDTH = 50

    CAPTURE_MIN_GAME_ICON_SIZE = 48
    CAPTURE_MAX_GAME_ICON_SIZE = 96

    PROPERTY_NAME_COLUMN_WIDTH = ui.Pixel(150)

    def __init__(self, context_name: str):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {
            "_capture_detail_property_widget": None,
            "_capture_details_collapsable_frame": None,
            "_capture_details_delegate": None,
            "_capture_details_frame": None,
            "_capture_details_model": None,
            "_capture_details_scroll_frame": None,
            "_capture_dir_field": None,
            "_capture_file_collapsable_frame": None,
            "_capture_manip_frame": None,
            "_capture_manipulator_frame": None,
            "_capture_slide_placer": None,
            "_capture_slider_manip": None,
            "_capture_tree_delegate": None,
            "_capture_tree_hovered_task": None,
            "_capture_tree_model": None,
            "_capture_tree_view": None,
            "_capture_tree_view_window": None,
            "_context_name": None,
            "_context": None,
            "_last_capture_tree_view_window_selection": None,
            "_overlay_capture_label": None,
            "_root_frame": None,
            "_tree_capture_scroll_frame": None,
            "_window_capture_tree": None,
            "_game_icon_hovered_task": None,
            "_mod_file_collapsable_frame": None,
            "_mod_file_details_collapsable_frame": None,
            "_mod_file_frame": None,
            "_mod_file_details_frame": None,
            "_mod_file_field": None,
            "_core_capture": None,
            "_core_replacement": None,
            "_mod_details_model": None,
            "_mod_details_delegate": None,
            "_mod_detail_property_widget": None,
            "_sub_stage_event": None,
            "_sub_layer_event": None,
            "_sub_mod_field_changed": None,
            "_sub_capture_dir_field_begin_edit": None,
            "_sub_capture_dir_field_end_edit": None,
            "_sub_capture_dir_field_changed": None,
            "_tree_capture_window_scroll_frame": None,
            "_capture_loading_frame": None,
            "_refresh_capture_detail_panel_callback_task": None,
            "_error_popup": None,
            "_fake_frame_for_scroll": None,
            "_validation_error_msg": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        self.__last_capture_field_value = None
        self.__import_existing_mod_file = True
        self.__ignore_current_capture_layer = False
        self._capture_tree_hovered_task = None
        self._game_icon_hovered_task = None
        self._refresh_capture_detail_panel_callback_task = None
        self._ignore_capture_window_tree_selection_changed = False
        self._ignore_capture_tree_selection_changed = False
        self.__ignore_capture_tree_hovered = False
        self._ignore_capture_detail_refresh = False
        self._ignore_mod_file_field_changed = False
        self._ignore_mod_detail_refresh = False
        self.__ignore_import_capture_layer = False
        self._capture_tree_model = CaptureTreeModel(context_name)
        self._capture_tree_delegate = CaptureTreeDelegate()
        self._capture_tree_delegate_window = CaptureTreeDelegate()
        self.__capture_field_is_editing = False
        self._core_capture = CaptureCoreSetup(context_name)
        self._core_replacement = ReplacementCoreSetup(context_name)

        self._sub_model_changed = self._capture_tree_model.subscribe_progress_updated(self._refresh_trees)

        self._sub_stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_stage_event, name="StageChanged"
        )

        self._layers = _layers.get_layers()
        self._sub_layer_event = self._layers.get_event_stream().create_subscription_to_pop(
            self.__on_layer_event, name="LayerChange"
        )

        self.__file_listener_instance = _get_file_listener_instance()

        self.__on_select_vehicle_pressed_event = _Event()
        self.__on_import_capture_layer = _Event()
        self.__on_import_replacement_layer = _Event()

        self._validation_error_msg = ""

        self.__create_ui()

    def __on_layer_event(self, event):
        payload = _layers.get_layer_event_payload(event)
        if not payload:
            return
        if payload.event_type == _layers.LayerEventType.SUBLAYERS_CHANGED:
            self.__on_event()

    def __on_stage_event(self, event):
        if event.type in [
            int(omni.usd.StageEventType.CLOSED),
            int(omni.usd.StageEventType.OPENED),
        ]:
            self.__on_event()

    def __on_event(self):
        self.refresh_capture_detail_panel()
        self.refresh_mod_detail_panel()

    @_ignore_function_decorator(attrs=["_ignore_capture_window_tree_selection_changed"])
    def _on_cancel_clicked(self):
        self._capture_tree_view_window.selection = (
            []
            if self._last_capture_tree_view_window_selection is None
            else self._last_capture_tree_view_window_selection
        )

    def _import_capture_layer(self, path):
        def on_okay_clicked():
            self.__on_import_capture_layer(path)
            self._last_capture_tree_view_window_selection = self._capture_tree_view_window.selection

        TrexMessageDialog(
            message=f"Are you sure you want to load this capture layer?\n\n{path}",
            ok_handler=on_okay_clicked,
            cancel_handler=self._on_cancel_clicked,
            ok_label="Load",
        )

    def subscribe_import_capture_layer(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_import_capture_layer, function)

    def subscribe_import_replacement_layer(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_import_replacement_layer, function)

    def _select_vehicle_pressed(self):
        """Call the event object that has the list of functions"""
        self.__on_select_vehicle_pressed_event()

    def subscribe_select_vehicle_pressed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_select_vehicle_pressed_event, function)

    def __create_capture_tree_window(self):
        flags = ui.WINDOW_FLAGS_NO_COLLAPSE
        flags |= ui.WINDOW_FLAGS_NO_CLOSE
        flags |= ui.WINDOW_FLAGS_NO_MOVE
        flags |= ui.WINDOW_FLAGS_NO_RESIZE
        flags |= ui.WINDOW_FLAGS_NO_DOCKING
        flags |= ui.WINDOW_FLAGS_NO_BACKGROUND
        flags |= ui.WINDOW_FLAGS_NO_TITLE_BAR
        # flags |= ui.WINDOW_FLAGS_MODAL  # OM-49102

        self._window_capture_tree = ui.Window(
            "Capture tree window",
            width=self._tree_capture_scroll_frame.computed_width,
            height=self._tree_capture_scroll_frame.computed_height,
            visible=False,
            flags=flags,
        )
        self._window_capture_tree.frame.set_mouse_hovered_fn(self._on_capture_tree_hovered)
        with self._window_capture_tree.frame:
            self._tree_capture_window_scroll_frame = ui.ScrollingFrame(
                name="PropertiesPaneSection",
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                scroll_y_changed_fn=self._on_scroll_y_window_capture_tree_changed,
            )
            with self._tree_capture_window_scroll_frame:
                with ui.ZStack():
                    ui.Rectangle(name="PropertiesPaneSectionWindowCaptureBackground")
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8))
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            # TODO BUG OM-52829: TreeView vertical size does not account for header visibility
                            self._capture_tree_view_window = ui.TreeView(
                                self._capture_tree_model,
                                delegate=self._capture_tree_delegate_window,
                                root_visible=False,
                                header_visible=True,
                                columns_resizable=False,
                                name="PropertiesPaneSectionCapture",
                                selection_changed_fn=self._on_capture_window_tree_selection_changed,
                            )
                            ui.Spacer(height=ui.Pixel(32))  # TODO: Set to 8 pixels once OM-52829 is resolved
                        ui.Spacer(width=ui.Pixel(8))
        self._window_capture_tree.frame.set_computed_content_size_changed_fn(
            functools.partial(
                self._resize_capture_tree_columns, self._capture_tree_view_window, self._window_capture_tree.frame
            )
        )

        self._window_capture_tree.frame.set_build_fn(
            functools.partial(
                self._resize_capture_tree_columns, self._capture_tree_view_window, self._window_capture_tree.frame
            )
        )

    def _on_scroll_y_window_capture_tree_changed(self, y):
        if self._tree_capture_scroll_frame:
            self._tree_capture_scroll_frame.scroll_y = y

    def __create_ui(self):
        self._root_frame = ui.Frame()
        with self._root_frame:
            with ui.ScrollingFrame(
                name="PropertiesPaneSection",
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            ):
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(56))

                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8), height=ui.Pixel(0))
                        with ui.VStack():
                            self._capture_file_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "CAPTURE FILE",
                                info_text=(
                                    "The capture file loads the captured scene from the game.\n"
                                    "This will be used as the base scene for modifications created in the system."
                                ),
                            )
                            with self._capture_file_collapsable_frame:
                                with ui.VStack():
                                    ui.Spacer(height=ui.Pixel(8))
                                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                                        ui.Label(
                                            "Capture Directory",
                                            name="PropertiesWidgetLabel",
                                            tooltip="Path of the capture",
                                            width=0,
                                        )
                                        with ui.HStack():
                                            ui.Spacer(width=ui.Pixel(4))
                                            with ui.ZStack():
                                                self._capture_dir_field = ui.StringField(
                                                    name="CapturePathField",
                                                    height=ui.Pixel(18),
                                                    style_type_name_override="Field",
                                                )
                                                with ui.HStack():
                                                    ui.Spacer(width=ui.Pixel(8))
                                                    with ui.Frame(width=ui.Pixel(134), horizontal_clipping=False):
                                                        self._overlay_capture_label = ui.Label(
                                                            "Capture directory path...",
                                                            name="USDPropertiesWidgetValueOverlay",
                                                            width=0,
                                                        )
                                                self._sub_capture_dir_field_begin_edit = (
                                                    self._capture_dir_field.model.subscribe_begin_edit_fn(
                                                        self._on_capture_dir_field_begin
                                                    )
                                                )
                                                self._sub_capture_dir_field_end_edit = (
                                                    self._capture_dir_field.model.subscribe_end_edit_fn(
                                                        self._on_capture_dir_field_end
                                                    )
                                                )
                                                self._sub_capture_dir_field_changed = (
                                                    self._capture_dir_field.model.subscribe_value_changed_fn(
                                                        self._on_capture_dir_field_changed
                                                    )
                                                )
                                            ui.Spacer(width=ui.Pixel(8))
                                            with ui.VStack(width=ui.Pixel(20)):
                                                ui.Spacer()
                                                ui.Image(
                                                    "",
                                                    name="OpenFolder",
                                                    height=ui.Pixel(20),
                                                    tooltip="Open the file picker",
                                                    mouse_pressed_fn=lambda x, y, b, m: self._on_capture_dir_pressed(b),
                                                )
                                                ui.Spacer()
                                            ui.Spacer(width=ui.Pixel(8))
                                            with ui.VStack(width=ui.Pixel(20)):
                                                ui.Spacer()
                                                ui.Image(
                                                    "",
                                                    name="Refresh",
                                                    height=ui.Pixel(20),
                                                    tooltip="Refresh the capture list",
                                                    mouse_pressed_fn=lambda x, y, b, m: self.__on_event(),
                                                )
                                                ui.Spacer()

                                    self._capture_manipulator_frame = ui.Frame(visible=False)
                                    with self._capture_manipulator_frame:
                                        with ui.VStack():
                                            ui.Spacer(height=ui.Pixel(8))
                                            ui.Line(name="PropertiesPaneSectionTitle", height=0)
                                            ui.Spacer(height=ui.Pixel(8))
                                            size_manipulator_height = 4
                                            with ui.Frame():
                                                with ui.ZStack():
                                                    with ui.VStack():
                                                        with ui.ZStack():
                                                            self._tree_capture_scroll_frame = ui.ScrollingFrame(
                                                                name="PropertiesPaneSection",
                                                                # height=ui.Pixel(self.DEFAULT_CAPTURE_TREE_FRAME_HEIGHT),  # noqa E501
                                                                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,  # noqa E501
                                                                identifier="TreeCaptureScrollFrame",
                                                            )
                                                            with self._tree_capture_scroll_frame:
                                                                with ui.ZStack():
                                                                    self._capture_tree_view = ui.TreeView(
                                                                        self._capture_tree_model,
                                                                        delegate=self._capture_tree_delegate,
                                                                        root_visible=False,
                                                                        header_visible=True,
                                                                        columns_resizable=False,
                                                                        mouse_hovered_fn=self._on_capture_tree_hovered,
                                                                        selection_changed_fn=self._on_capture_tree_selection_changed,  # noqa E501
                                                                    )
                                                                    self._fake_frame_for_scroll = ui.Frame()
                                                            self._tree_capture_scroll_frame.set_build_fn(
                                                                functools.partial(
                                                                    self._resize_capture_tree_columns,
                                                                    self._capture_tree_view,
                                                                    self._tree_capture_scroll_frame,
                                                                )
                                                            )
                                                            self._tree_capture_scroll_frame.set_computed_content_size_changed_fn(  # noqa E501
                                                                functools.partial(
                                                                    self._resize_capture_tree_columns,
                                                                    self._capture_tree_view,
                                                                    self._tree_capture_scroll_frame,
                                                                )
                                                            )

                                                            self._capture_loading_frame = ui.Frame(
                                                                visible=False,
                                                                separate_window=True,
                                                                build_fn=self._resize_capture_loading_frame,
                                                            )
                                                            with self._capture_loading_frame:
                                                                with ui.ZStack():
                                                                    ui.Rectangle(
                                                                        name="LoadingBackground",
                                                                        tooltip="Updating capture list",
                                                                    )
                                                                    with ui.VStack(spacing=ui.Pixel(4)):
                                                                        ui.Spacer(width=0)
                                                                        ui.Image("", name="TimerStatic", height=24)
                                                                        ui.Label(
                                                                            "Updating",
                                                                            name="LoadingLabel",
                                                                            height=0,
                                                                            alignment=ui.Alignment.CENTER,
                                                                        )
                                                                        ui.Spacer(width=0)

                                                        ui.Spacer(height=ui.Pixel(8))
                                                        ui.Line(name="PropertiesPaneSectionTitle")
                                                        ui.Spacer(height=ui.Pixel(8))
                                                        ui.Spacer(height=size_manipulator_height)

                                                    with ui.VStack():
                                                        ui.Spacer()
                                                        self._capture_manip_frame = ui.Frame(
                                                            height=size_manipulator_height
                                                        )
                                                        with self._capture_manip_frame:
                                                            self._capture_slide_placer = ui.Placer(
                                                                draggable=True,
                                                                height=size_manipulator_height,
                                                                offset_x_changed_fn=self._on_capture_slide_x_changed,
                                                                offset_y_changed_fn=functools.partial(
                                                                    self._on_capture_slide_y_changed,
                                                                    size_manipulator_height,
                                                                ),
                                                            )
                                                            # Body
                                                            with self._capture_slide_placer:
                                                                self._capture_slider_manip = ui.Rectangle(
                                                                    width=ui.Percent(
                                                                        self.SIZE_PERCENT_MANIPULATOR_WIDTH
                                                                    ),
                                                                    name="PropertiesPaneSectionTreeManipulator",
                                                                )
                                                                _hover_helper(self._capture_slider_manip)

                            ui.Spacer(height=ui.Pixel(16))

                            self._capture_details_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "CAPTURE DETAILS",
                                info_text="Details from the capture layer file loaded in this stage",
                                collapsed=True,
                                enabled=False,
                            )
                            with self._capture_details_collapsable_frame:
                                self._capture_details_frame = ui.Frame()

                            ui.Spacer(height=ui.Pixel(16))
                            self._mod_file_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "MOD FILE",
                                info_text=(
                                    "The mod file modify the capture file above.\n"
                                    "This will be used as a layer over the capture file.\n"
                                    "You can load an existing mod file or create a new one.\n"
                                    "Each time that you create/load a mod file, it will replace the existing one in the"
                                    " stage."
                                ),
                                enabled=False,
                            )
                            with self._mod_file_collapsable_frame:
                                with ui.VStack(spacing=ui.Pixel(8)):
                                    with ui.HStack(height=ui.Pixel(32)):
                                        ui.Button("Load Existing File", clicked_fn=self._on_load_existing_mod)
                                        ui.Spacer(width=ui.Pixel(8))
                                        ui.Button("Create New File", clicked_fn=self._on_create_mod)

                                    self._mod_file_frame = ui.Frame()
                                    with self._mod_file_frame:
                                        with ui.HStack():
                                            ui.Label(
                                                "Mod File Path",
                                                name="PropertiesWidgetLabel",
                                                tooltip="Path of the mod",
                                                width=0,
                                            )
                                            ui.Spacer(width=ui.Pixel(8))
                                            with ui.HStack():
                                                ui.Spacer(width=ui.Pixel(8))
                                                self._mod_file_field = ui.StringField(
                                                    read_only=True, height=0, identifier="mod_file_field"
                                                )
                                                self._mod_file_field.model.set_value("...")
                                                self._sub_mod_field_changed = (
                                                    self._mod_file_field.model.subscribe_value_changed_fn(
                                                        self._on_mod_file_field_changed
                                                    )
                                                )

                            ui.Spacer(height=ui.Pixel(16))

                            self._mod_file_details_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "MOD DETAILS",
                                info_text="Details from the mod layer file loaded in this stage",
                                collapsed=True,
                                enabled=False,
                            )
                            with self._mod_file_details_collapsable_frame:
                                self._mod_file_details_frame = ui.Frame()

                            ui.Spacer(height=ui.Pixel(16))

                    ui.Spacer()

    def _set_mod_file_field(self, path):
        self._mod_file_field.model.set_value(path)

    def _validate_file_path(self, existing_file, dirname, filename):
        valid = self._core_replacement.is_path_valid(
            omni.client.normalize_url(omni.client.combine_urls(dirname, filename)), existing_file=existing_file
        )
        if not valid:
            return False

        if existing_file:
            layer_manager = _LayerManagerCore(self._context_name)
            valid = layer_manager.is_valid_layer_type(str(Path(dirname, filename)), _LayerType.replacement)
            if not valid:
                self._validation_error_msg = (
                    f"Existing mod file is not the correct type, {_LayerType.replacement.value}."
                )

        return valid

    def _on_load_existing_mod(self):
        value = self._mod_file_field.model.get_value_as_string()
        current_file = value if value.strip() else None
        if current_file:
            result, entry = omni.client.stat(current_file)
            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.READABLE_FILE:
                current_file = None
        self.__import_existing_mod_file = True

        _open_file_picker(
            "Select an existing mod file",
            self._set_mod_file_field,
            lambda *args: None,
            current_file=current_file,
            file_extension_options=_READ_USD_FILE_EXTENSIONS_OPTIONS,
            validate_selection=functools.partial(self._validate_file_path, True),
            validation_failed_callback=lambda *_: self._on_validation_error(True),
        )

    def _on_create_mod(self):
        value = self._mod_file_field.model.get_value_as_string()
        current_file = value if value.strip() else None
        if current_file:
            result, entry = omni.client.stat(current_file)
            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.READABLE_FILE:
                current_file = None
        self.__import_existing_mod_file = False

        open_file_picker_create(
            self._set_mod_file_field,
            lambda *args: None,
            functools.partial(self._validate_file_path, False),
            lambda *_: self._on_validation_error(True),
            current_file=current_file,
        )

    def _on_validation_error(self, read_file: bool):
        fill_word = "selected" if read_file else "created"
        message = f"The {fill_word} mod file is not valid.\n\n"
        if self._validation_error_msg:
            message = f"{message}{self._validation_error_msg}"
        else:
            message = (
                f"{message}Make sure the {fill_word} mod file is a writable USD file and is not located in a "
                f'"{_GAME_READY_ASSETS_FOLDER}" or "{_REMIX_CAPTURE_FOLDER}" directory.'
            )
        TrexMessageDialog(
            message=message,
            disable_cancel_button=True,
        )

    def _enable_panels(self):
        value = bool(self._core_capture.get_layer())
        if not value:
            self._capture_file_collapsable_frame.root.collapsed = False
            self._capture_details_collapsable_frame.root.collapsed = True
            self._mod_file_collapsable_frame.root.collapsed = False
            self._mod_file_details_collapsable_frame.root.collapsed = True
        self._capture_details_collapsable_frame.enabled = value
        self._mod_file_collapsable_frame.enabled = value
        self._mod_file_details_collapsable_frame.enabled = value

    @_sandwich_attrs_function_decorator(attrs=["_ignore_mod_file_field_changed"])
    @_ignore_function_decorator(attrs=["_ignore_mod_detail_refresh"])
    def refresh_mod_detail_panel(self):
        if not self._root_frame.visible:
            return
        self._mod_file_details_frame.clear()
        capture_layer = self._core_replacement.get_layer()
        if capture_layer is None:
            self._set_mod_file_field("...")
            return
        current_file = omni.client.normalize_url(capture_layer.realPath)
        if not current_file or not self._core_replacement.is_path_valid(current_file):
            return
        self._set_mod_file_field(current_file)
        self._destroy_mod_properties()

        items = []
        for attr in [attr for attr in dir(omni.client.ListEntry) if not attr.startswith("_")]:
            items.append(_FileAttributeItem(current_file, attr, display_attr_name=attr.replace("_", " ").capitalize()))

        self._mod_details_model = _FileModel(current_file)
        self._mod_details_model.set_items(items)
        self._mod_details_delegate = _FileDelegate(right_aligned_labels=False)
        self.__file_listener_instance.add_model(self._mod_details_model)

        with self._mod_file_details_frame:
            with ui.VStack():
                ui.Spacer(height=ui.Pixel(8))
                self._mod_detail_property_widget = _PropertyWidget(
                    self._mod_details_model,
                    self._mod_details_delegate,
                    tree_column_widths=[self.PROPERTY_NAME_COLUMN_WIDTH, ui.Fraction(1)],
                    columns_resizable=True,
                )

    def _refresh_trees(self, *_):
        if self._capture_tree_view_window:
            self._capture_tree_view_window.dirty_widgets()
        if self._capture_tree_view:
            self._capture_tree_view.dirty_widgets()

    def __unselect_capture_items(self):
        self.__ignore_import_capture_layer = True
        self._capture_tree_view_window.selection = []
        self._capture_tree_view.selection = self._capture_tree_view_window.selection
        self.__ignore_import_capture_layer = False

    def __show_capture_loading_frames(self, value):
        if self._capture_loading_frame:
            self._capture_loading_frame.visible = value
            self._capture_loading_frame.rebuild()

    @_ignore_function_decorator(attrs=["_ignore_capture_detail_refresh"])
    def refresh_capture_detail_panel(self):
        """
        Refresh the panel with the given paths
        """

        if not self._root_frame.visible:
            return
        if not self._capture_tree_view_window:
            self.__create_capture_tree_window()
        self._enable_panels()

        # update capture tree from capture dir field
        self._capture_details_frame.clear()
        self._destroy_capture_properties()
        capture_layer = self._core_capture.get_layer()

        if capture_layer is None or self.__ignore_current_capture_layer:
            # grab from the field
            value = self._capture_dir_field.model.get_value_as_string()
            self.__ignore_current_capture_layer = False
        else:
            value = os.path.dirname(omni.client.normalize_url(capture_layer.realPath))
        capture_dir = value if value.strip() else None
        if not capture_dir or not self._core_capture.is_path_valid(capture_dir):
            self.__unselect_capture_items()
            return

        self.set_capture_dir_field(capture_dir)

        if not self._capture_manipulator_frame.visible:
            self._capture_manipulator_frame.visible = True
            self._tree_capture_scroll_frame.height = ui.Pixel(self.DEFAULT_CAPTURE_TREE_FRAME_HEIGHT)
        self.__show_capture_loading_frames(True)

        if self._refresh_capture_detail_panel_callback_task:
            self._refresh_capture_detail_panel_callback_task.cancel()
        self._refresh_capture_detail_panel_callback_task = asyncio.ensure_future(
            self._core_capture.deferred_get_capture_files(
                functools.partial(self.__refresh_capture_detail_panel_callback, capture_layer)
            )
        )

    @omni.usd.handle_exception
    @_ignore_function_decorator_async(attrs=["_ignore_capture_detail_refresh"])
    async def __refresh_capture_detail_panel_callback(self, capture_layer, capture_files):
        def set_game_icon(widget, image_path):
            if not image_path:
                return
            widget.source_url = image_path

        @omni.usd.handle_exception
        async def deferred_on_game_icon_hovered(widget, hovered):
            current_size = widget.computed_width
            final_size = current_size
            if hovered:
                while final_size <= self.CAPTURE_MAX_GAME_ICON_SIZE:
                    await asyncio.sleep(0.04)
                    final_size += 10
                    widget.width = ui.Pixel(final_size)
                    widget.height = ui.Pixel(final_size)
            else:
                while final_size >= self.CAPTURE_MIN_GAME_ICON_SIZE:
                    await asyncio.sleep(0.04)
                    final_size -= 10
                    widget.width = ui.Pixel(final_size)
                    widget.height = ui.Pixel(final_size)

        def on_game_icon_hovered(widget, hovered):
            if self._game_icon_hovered_task:
                self._game_icon_hovered_task.cancel()
            self._game_icon_hovered_task = asyncio.ensure_future(deferred_on_game_icon_hovered(widget, hovered))

        self.__show_capture_loading_frames(False)
        self._capture_tree_model.refresh([(path, self._core_capture.get_capture_image(path)) for path in capture_files])

        # check if there is current capture layer
        if capture_layer is None:
            self.__unselect_capture_items()
            return
        capture_path = omni.client.normalize_url(capture_layer.realPath)

        found_current_layer = False
        for item in self._capture_tree_model.get_item_children(None):
            if omni.client.normalize_url(item.path) == omni.client.normalize_url(capture_layer.realPath):
                self.__ignore_import_capture_layer = True
                self._capture_tree_view_window.selection = [item]
                self._capture_tree_view.selection = self._capture_tree_view_window.selection
                await self.scroll_to_item(item)
                self.__ignore_import_capture_layer = False
                found_current_layer = True
                break
        if not found_current_layer:
            self.__unselect_capture_items()

        items = []
        for attr in [attr for attr in dir(omni.client.ListEntry) if not attr.startswith("_")]:
            items.append(_FileAttributeItem(capture_path, attr, display_attr_name=attr.replace("_", " ").capitalize()))

        self._capture_details_model = _FileModel(capture_path)
        self._capture_details_model.set_items(items)
        self._capture_details_delegate = _FileDelegate(right_aligned_labels=False)
        self.__file_listener_instance.add_model(self._capture_details_model)

        with self._capture_details_frame:
            with ui.VStack():
                ui.Spacer(height=ui.Pixel(8))
                with ui.HStack(height=ui.Pixel(self.CAPTURE_MIN_GAME_ICON_SIZE)):
                    with ui.HStack(width=self.PROPERTY_NAME_COLUMN_WIDTH):
                        ui.Spacer(width=ui.Pixel(32))
                        game_icon_widget = ui.Image("", width=ui.Pixel(self.CAPTURE_MIN_GAME_ICON_SIZE))
                        await self._core_capture.deferred_get_upscaled_game_icon_from_folder(
                            os.path.dirname(capture_path), functools.partial(set_game_icon, game_icon_widget)
                        )
                        game_icon_widget.set_mouse_hovered_fn(functools.partial(on_game_icon_hovered, game_icon_widget))
                        ui.Spacer()
                    with ui.VStack():
                        ui.Spacer()
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(8), height=0)
                            game_name = self._core_capture.get_game_name(capture_path)
                            ui.StringField(read_only=True, height=0).model.set_value(game_name)
                        ui.Spacer()
                ui.Spacer(height=ui.Pixel(8))
                self._capture_detail_property_widget = _PropertyWidget(
                    self._capture_details_model,
                    self._capture_details_delegate,
                    tree_column_widths=[self.PROPERTY_NAME_COLUMN_WIDTH, ui.Fraction(1)],
                    columns_resizable=True,
                )

    @omni.usd.handle_exception
    async def scroll_to_item(self, item):
        all_visible_items = self._capture_tree_model.get_item_children(None)
        idx_item = all_visible_items.index(item)
        await omni.kit.app.get_app().next_update_async()
        self._fake_frame_for_scroll.clear()
        with self._fake_frame_for_scroll:
            with ui.VStack():
                ui.Spacer(height=24)  # header
                ui.Spacer(height=idx_item * self._capture_tree_delegate.DEFAULT_IMAGE_ICON_SIZE)
                ui.Spacer(height=self._capture_tree_delegate.DEFAULT_IMAGE_ICON_SIZE)
                fake_spacer_for_scroll = ui.Spacer(height=self._capture_tree_delegate.DEFAULT_IMAGE_ICON_SIZE)
                ui.Spacer()

        fake_spacer_for_scroll.scroll_here_y(0.5)

    @_ignore_function_decorator(attrs=["_ignore_capture_window_tree_selection_changed"])
    def _on_capture_window_tree_selection_changed(self, items):
        if len(items) > 1:
            self._capture_tree_view_window.selection = [items[0]]
        if self._capture_tree_view_window.selection and not self.__ignore_import_capture_layer:
            self._import_capture_layer(items[0].path)
        else:
            self.refresh_capture_detail_panel()

    @_ignore_function_decorator(attrs=["_ignore_capture_tree_selection_changed"])
    def _on_capture_tree_selection_changed(self, items):
        if not self._capture_tree_view_window:
            self.__create_capture_tree_window()
        self._capture_tree_view_window.selection = items

    def _on_capture_tree_hovered(self, hovered):
        # if the left click is pushed, we ignore (because it can come from the property/viewport splitter)
        iinput = carb.input.acquire_input_interface()
        app_window = omni.appwindow.get_default_app_window()
        mouse = app_window.get_mouse()
        mouse_value = iinput.get_mouse_value(mouse, carb.input.MouseInput.LEFT_BUTTON)
        if mouse_value:
            return

        if self._capture_loading_frame.visible:
            return

        if self._window_capture_tree is None:
            self.__create_capture_tree_window()
        if self.__ignore_capture_tree_hovered:
            return
        if self._capture_tree_hovered_task:
            self._capture_tree_hovered_task.cancel()
        self._capture_tree_hovered_task = asyncio.ensure_future(self.__deferred_on_capture_tree_hovered(hovered))

    @omni.usd.handle_exception
    async def __deferred_on_capture_tree_hovered(self, hovered):
        await omni.kit.app.get_app_interface().next_update_async()
        item_path_scroll_frames = self._capture_tree_delegate.get_path_scroll_frames()
        if not item_path_scroll_frames:
            return
        self._window_capture_tree.position_x = self._tree_capture_scroll_frame.screen_position_x - 12
        self._window_capture_tree.position_y = self._tree_capture_scroll_frame.screen_position_y - 12
        if hovered and not self._window_capture_tree.visible:
            self.__ignore_capture_tree_hovered = True
            self._window_capture_tree.visible = hovered
            app_window = omni.appwindow.get_default_app_window()
            size = app_window.get_size()

            rows_size = (
                len(self._capture_tree_model.get_item_children(None))
                * self._capture_tree_delegate.DEFAULT_IMAGE_ICON_SIZE
            )
            final_value_h = rows_size + 40
            dpi_scale = ui.Workspace.get_dpi_scale()
            if final_value_h > size[1] / dpi_scale - self._tree_capture_scroll_frame.screen_position_y - 8:
                final_value_h = size[1] / dpi_scale - self._tree_capture_scroll_frame.screen_position_y - 8
            self._window_capture_tree.height = ui.Pixel(final_value_h + 8)
            self._window_capture_tree.width = ui.Pixel(self._tree_capture_scroll_frame.computed_width + 24)
            scroll_y_value = int(self._tree_capture_scroll_frame.scroll_y)
            for _ in range(2):  # 2 frame to have the scroll frame appear
                await omni.kit.app.get_app().next_update_async()  # wait the window to appear
            self._tree_capture_window_scroll_frame.scroll_y = scroll_y_value

            item_path_scroll_frames = self._capture_tree_delegate_window.get_path_scroll_frames()
            if item_path_scroll_frames:
                value = max(frame.scroll_x_max for frame in item_path_scroll_frames.values())
                if value != 0:  # no scroll max = we see everything
                    final_value_w = self._window_capture_tree.width + value
                    if final_value_w > size[0] / dpi_scale - self._tree_capture_scroll_frame.screen_position_x - 8:
                        final_value_w = size[0] / dpi_scale - self._tree_capture_scroll_frame.screen_position_x - 8
                    self._window_capture_tree.width = ui.Pixel(final_value_w + 32)
            self.__ignore_capture_tree_hovered = False
        elif (
            self._window_capture_tree.visible
            and not self._capture_tree_delegate_window.get_window_bigger_image().visible
        ):
            self._window_capture_tree.visible = hovered

    def _resize_capture_tree_columns(self, tree_view, frame):
        tree_view.column_widths = [
            ui.Percent(80),
            ui.Percent(20),
        ]

    def _resize_capture_loading_frame(self):
        self._capture_loading_frame.height = ui.Pixel(self._tree_capture_scroll_frame.computed_height)

    def _on_capture_slide_x_changed(self, x):
        size_manip = self._capture_manip_frame.computed_width / 100 * self.SIZE_PERCENT_MANIPULATOR_WIDTH
        if x.value < 0:
            self._capture_slide_placer.offset_x = 0
        elif x.value > self._capture_manip_frame.computed_width - size_manip:
            self._capture_slide_placer.offset_x = self._capture_manip_frame.computed_width - size_manip

        item_path_scroll_frames = self._capture_tree_delegate.get_path_scroll_frames()
        if item_path_scroll_frames:
            max_frame_scroll_x = max(frame.scroll_x_max for frame in item_path_scroll_frames.values())
            value = (max_frame_scroll_x / (self._capture_manip_frame.computed_width - size_manip)) * x
            for frame in item_path_scroll_frames.values():
                frame.scroll_x = value

    def _on_capture_slide_y_changed(self, size_manip, y):
        if y.value < 0:
            self._capture_slide_placer.offset_y = 0
        self._tree_capture_scroll_frame.height = ui.Pixel(self.DEFAULT_CAPTURE_TREE_FRAME_HEIGHT + y.value)
        self._resize_capture_loading_frame()

    def _on_capture_dir_pressed(self, button):
        if button != 0:
            return
        value = self._capture_dir_field.model.get_value_as_string()
        current_directory = value if value.strip() else None
        if current_directory:
            result, entry = omni.client.stat(current_directory)
            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
                current_directory = None
        self.__ignore_current_capture_layer = True

        def validate_selection(dirname, _):
            return self._core_capture.is_path_valid(dirname, self._show_error_popup)

        _open_file_picker(
            "Select a capture directory",
            self.set_capture_dir_field,
            lambda *args: None,
            current_file=current_directory,
            select_directory=True,
            validate_selection=functools.partial(validate_selection),
        )

    def _show_error_popup(self, title, message):
        self._error_popup = _ErrorPopup(title, message, window_size=(400, 120))
        self._error_popup.show()
        carb.log_error(message)

    def set_capture_dir_field(self, path):
        self._capture_dir_field.model.set_value(path)
        self._core_capture.set_directory(path)

    def _on_capture_dir_field_begin(self, model):
        self.__capture_field_is_editing = True

    def _on_capture_dir_field_end(self, model):
        self.__capture_field_is_editing = False
        self._on_capture_dir_field_changed(model)

    @_ignore_function_decorator(attrs=["_ignore_capture_dir_field_changed"])
    def _on_capture_dir_field_changed(self, model):
        path = model.get_value_as_string()
        self._overlay_capture_label.visible = not bool(path.strip())
        if not self._core_capture.is_path_valid(path):
            if not self.__capture_field_is_editing:
                self._capture_dir_field.style_type_name_override = "Field"
                self._capture_dir_field.model.set_value(self.__last_capture_field_value or "")
                self._overlay_capture_label.visible = False
                return
            self._capture_dir_field.style_type_name_override = "FieldError"
            return
        self._capture_dir_field.style_type_name_override = "Field"
        if self.__capture_field_is_editing:
            return
        self.__last_capture_field_value = path
        self.refresh_capture_detail_panel()

        # Sometimes, the capture field change happens in the middle of the hover process for the
        # capture tree window. If this isn't set back to False, it'll no longer trigger the hover action.
        self.__ignore_capture_tree_hovered = False

    @_ignore_function_decorator(attrs=["_ignore_mod_file_field_changed"])
    def _on_mod_file_field_changed(self, model):
        path = model.get_value_as_string()
        if self._core_replacement.is_path_valid(path, existing_file=self.__import_existing_mod_file):
            self.__on_import_replacement_layer(path, self.__import_existing_mod_file)
        self.refresh_mod_detail_panel()

    def _destroy_capture_properties(self):
        if self._window_capture_tree:
            self._window_capture_tree.visible = False
        if self.__file_listener_instance and self._capture_details_model and self._capture_details_delegate:
            self.__file_listener_instance.remove_model(self._capture_details_model)
        if self._capture_tree_hovered_task:
            self._capture_tree_hovered_task.cancel()
        if self._refresh_capture_detail_panel_callback_task:
            self._refresh_capture_detail_panel_callback_task.cancel()

    def _destroy_mod_properties(self):
        if self.__file_listener_instance and self._mod_details_model and self._mod_details_delegate:
            self.__file_listener_instance.remove_model(self._mod_details_model)

    def show(self, value):
        self._capture_tree_model.enable_listeners(value)
        self._root_frame.visible = value
        if value:
            self.refresh_capture_detail_panel()
            self.refresh_mod_detail_panel()
        else:
            self._capture_tree_model.cancel_tasks()
            self._destroy_mod_properties()
            self._destroy_capture_properties()

    def destroy(self):
        if self._capture_tree_hovered_task:
            self._capture_tree_hovered_task.cancel()
        if self._refresh_capture_detail_panel_callback_task:
            self._refresh_capture_detail_panel_callback_task.cancel()
        self._destroy_mod_properties()
        self._destroy_capture_properties()
        _reset_default_attrs(self)
        self.__file_listener_instance = None
