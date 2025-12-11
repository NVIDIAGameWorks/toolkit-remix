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
from pathlib import Path

import omni.client
import omni.kit.usd.layers as _layers
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import GAME_READY_ASSETS_FOLDER as _GAME_READY_ASSETS_FOLDER
from lightspeed.common.constants import READ_USD_FILE_EXTENSIONS_OPTIONS as _READ_USD_FILE_EXTENSIONS_OPTIONS
from lightspeed.common.constants import REMIX_CAPTURE_FOLDER as _REMIX_CAPTURE_FOLDER
from lightspeed.common.constants import GlobalEventNames as _GlobalEventNames
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.layer_manager.core import LSS_LAYER_MOD_NAME as _LSS_LAYER_MOD_NAME
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.packaging.core import ModPackagingSchema as _ModPackagingSchema
from lightspeed.trex.replacement.core.shared import Setup as ReplacementCoreSetup
from lightspeed.trex.utils.widget import TrexMessageDialog, WorkspaceWidget
from omni.flux.property_widget_builder.model.file import FileAttributeItem as _FileAttributeItem
from omni.flux.property_widget_builder.model.file import FileDelegate as _FileDelegate
from omni.flux.property_widget_builder.model.file import FileModel as _FileModel
from omni.flux.property_widget_builder.model.file import get_file_listener_instance as _get_file_listener_instance
from omni.flux.property_widget_builder.widget import PropertyWidget as _PropertyWidget
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.flux.utils.common.decorators import sandwich_attrs_function_decorator as _sandwich_attrs_function_decorator
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.utils.widget.collapsable_frame import (
    PropertyCollapsableFrameWithInfoPopup as _PropertyCollapsableFrameWithInfoPopup,
)
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker

from .mod_file_picker_create import open_file_picker_create


class ProjectSetupPane(WorkspaceWidget):

    PROPERTY_NAME_COLUMN_WIDTH = ui.Pixel(150)

    def __init__(self, context_name: str):
        """Nvidia StageCraft Components Pane"""
        super().__init__()

        self._default_attr = {
            "_context_name": None,
            "_context": None,
            "root_widget": None,
            "_mod_name_field": None,
            "_sub_name_field_changed": None,
            "_sub_name_field_end": None,
            "_last_valid_name": None,
            "_mod_file_collapsable_frame": None,
            "_mod_file_details_collapsable_frame": None,
            "_mod_file_frame": None,
            "_mod_file_details_frame": None,
            "_mod_file_field": None,
            "_core_replacement": None,
            "_mod_details_model": None,
            "_mod_details_delegate": None,
            "_mod_detail_property_widget": None,
            "_sub_stage_event": None,
            "_sub_layer_event": None,
            "_sub_mod_field_changed": None,
            "_validation_error_msg": None,
            "_layer_manager": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        self._layer_manager = _LayerManagerCore(self._context_name)
        self._last_valid_name = ""
        self.__import_existing_mod_file = True
        self._ignore_mod_file_field_changed = False
        self._ignore_mod_detail_refresh = False
        self._core_replacement = ReplacementCoreSetup(context_name)

        self._layers = _layers.get_layers()

        # Subscriptions created/destroyed in show() based on visibility
        self._sub_stage_event = None
        self._sub_layer_event = None

        self.__file_listener_instance = _get_file_listener_instance()

        self._validation_error_msg = ""

        self.__create_ui()

    def __on_layer_event(self, event):
        """Layer event callback - subscription destroyed when window invisible."""
        payload = _layers.get_layer_event_payload(event)
        if not payload:
            return
        if payload.event_type == _layers.LayerEventType.SUBLAYERS_CHANGED:
            self.__on_event()

    def __on_stage_event(self, event):
        """Stage event callback - subscription destroyed when window invisible."""
        if event.type in [
            int(omni.usd.StageEventType.CLOSED),
            int(omni.usd.StageEventType.OPENED),
        ]:
            self.__on_event()

    def __on_event(self):
        self._update_mod_name_field()
        self.refresh_mod_detail_panel()

    def __create_ui(self):
        self.root_widget = ui.Frame()
        with self.root_widget:
            with ui.ScrollingFrame(
                name="WorkspaceBackground",
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            ):
                with ui.VStack(style={"margin": 5}):
                    with ui.HStack():
                        with ui.VStack(style={"margin": 0}):
                            with ui.HStack(height=ui.Pixel(18)):
                                ui.Label("Project Name", name="PropertiesPaneSectionTitle")
                                ui.Spacer(width=ui.Pixel(4))
                                self._mod_name_field = ui.StringField(
                                    identifier="project_name_field",
                                )
                                self._sub_name_field_changed = self._mod_name_field.model.subscribe_value_changed_fn(
                                    self._update_name_valid
                                )
                                self._sub_name_field_end = self._mod_name_field.model.subscribe_end_edit_fn(
                                    self._on_name_field_end_edit
                                )
                            ui.Spacer(height=ui.Pixel(16))
                            self._mod_file_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "MOD FILE",
                                info_text=(
                                    "The mod file modifies the capture file above.\n"
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
                        ui.Spacer(width=ui.Pixel(16))
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

    def _enable_panels(self, value: bool):
        if self._mod_name_field:
            self._mod_name_field.read_only = not value
        self._mod_file_collapsable_frame.enabled = value
        self._mod_file_details_collapsable_frame.enabled = value

    def _update_mod_name_field(self):
        if not self._mod_name_field:
            return
        replacement_layer = self._layer_manager.get_layer(_LayerType.replacement)
        if not replacement_layer:
            self._mod_name_field.model.set_value("")
            self._last_valid_name = ""
            return

        if _LSS_LAYER_MOD_NAME in replacement_layer.customLayerData:
            mod_name = replacement_layer.customLayerData[_LSS_LAYER_MOD_NAME]
        else:
            root_layer = self._context.get_stage().GetRootLayer() if self._context.get_stage() else None
            if root_layer:
                mod_name = _OmniUrl(root_layer.realPath).stem
            else:
                mod_name = _OmniUrl(replacement_layer.realPath).stem

        self._last_valid_name = mod_name
        self._mod_name_field.model.set_value(mod_name)

    def _update_name_valid(self, *_):
        error = None
        try:
            _ModPackagingSchema.is_not_empty(self._mod_name_field.model.get_value_as_string().strip())
        except ValueError as e:
            error = str(e)
        is_valid = not bool(error)

        self._mod_name_field.style_type_name_override = "Field" if is_valid else "FieldError"
        self._mod_name_field.tooltip = "" if is_valid else error
        return is_valid

    def _on_name_field_end_edit(self, model):
        if self._update_name_valid():
            new_name = model.get_value_as_string().strip()
            replacement_layer = self._layer_manager.get_layer(_LayerType.replacement)
            if replacement_layer:
                custom_data = replacement_layer.customLayerData
                custom_data[_LSS_LAYER_MOD_NAME] = new_name
                replacement_layer.customLayerData = custom_data
                replacement_layer.Save()
                self._last_valid_name = new_name
        model.set_value(self._last_valid_name)

    @_sandwich_attrs_function_decorator(attrs=["_ignore_mod_file_field_changed"])
    @_ignore_function_decorator(attrs=["_ignore_mod_detail_refresh"])
    def refresh_mod_detail_panel(self):
        if not self.root_widget.visible:
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

    @_ignore_function_decorator(attrs=["_ignore_mod_file_field_changed"])
    def _on_mod_file_field_changed(self, model):
        path = model.get_value_as_string()
        if self._core_replacement.is_path_valid(path, existing_file=self.__import_existing_mod_file):
            _get_event_manager_instance().call_global_custom_event(
                _GlobalEventNames.IMPORT_LAYER.value,
                _LayerType.replacement,
                path,
                self.__import_existing_mod_file,
            )
        self.refresh_mod_detail_panel()

    def _destroy_mod_properties(self):
        if self.__file_listener_instance and self._mod_details_model and self._mod_details_delegate:
            self.__file_listener_instance.remove_model(self._mod_details_model)

    def show(self, visible: bool):
        super().show(visible)
        self.root_widget.visible = visible
        self._enable_panels(visible)

        if visible:
            # Create subscriptions when window becomes visible
            if not self._sub_stage_event:
                self._sub_stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
                    self.__on_stage_event, name="StageChanged"
                )
            if not self._sub_layer_event:
                self._sub_layer_event = self._layers.get_event_stream().create_subscription_to_pop(
                    self.__on_layer_event, name="LayerChange"
                )
            self._update_mod_name_field()
            self.refresh_mod_detail_panel()
        else:
            # Destroy subscriptions when window becomes invisible
            self._sub_stage_event = None
            self._sub_layer_event = None
            self._destroy_mod_properties()

    def destroy(self):
        self._destroy_mod_properties()
        _reset_default_attrs(self)
        self.__file_listener_instance = None
