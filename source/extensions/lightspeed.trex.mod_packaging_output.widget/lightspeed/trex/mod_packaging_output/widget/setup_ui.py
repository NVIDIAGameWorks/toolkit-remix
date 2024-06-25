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

import omni.ui as ui
import omni.usd
from lightspeed.common.constants import REGEX_VALID_PATH as _REGEX_VALID_PATH
from lightspeed.common.constants import REMIX_PACKAGE_FOLDER as _REMIX_PACKAGE_FOLDER
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.utils.common.path_utils import open_file_using_os_default
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker


class ModPackagingOutputWidget:
    def __init__(self, context_name: str = ""):
        self._default_attr = {
            "_context_name": None,
            "_last_valid_path": None,
            "_override_checkbox": None,
            "_output_field": None,
            "_sub_output_field_changed": None,
            "_sub_output_field_end": None,
            "_overlay_label": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._last_valid_path = ""

        self.__output_validity_changed = _Event()

        self.__create_ui()

    @property
    def output_path(self) -> str:
        """
        Get the dired mod output path
        """
        return self._output_field.model.get_value_as_string()

    def show(self, value: bool):
        """
        Show or hide this widget.
        This will trigger refreshes on show.
        """
        if value:
            self._update_default_values()
            self._update_output_valid()
            self._update_enable_state()
            self._update_open_button_state()

    def __create_ui(self):
        with ui.VStack(height=0):
            ui.Spacer(height=ui.Pixel(8))

            with ui.HStack():
                self._override_checkbox = ui.CheckBox(width=0, identifier="enable_override")
                ui.Spacer(height=0, width=ui.Pixel(8))
                ui.Label("Override output path")
            self._override_checkbox.model.add_value_changed_fn(self._update_enable_state)

            ui.Spacer(height=ui.Pixel(8))

            with ui.ZStack():
                with ui.HStack():
                    with ui.ZStack():
                        self._output_field = ui.StringField(
                            height=ui.Pixel(18), style_type_name_override="Field", identifier="output_field"
                        )
                        self._sub_output_field_changed = self._output_field.model.subscribe_value_changed_fn(
                            self._on_output_field_changed
                        )
                        self._sub_output_field_end = self._output_field.model.subscribe_end_edit_fn(
                            self._on_output_field_end_edit
                        )
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(8))
                            with ui.Frame(horizontal_clipping=True):
                                self._overlay_label = ui.Label(
                                    "Package output path...",
                                    name="USDPropertiesWidgetValueOverlay",
                                    width=0,
                                    height=ui.Pixel(24),
                                )
                    ui.Spacer(width=ui.Pixel(8))
                    with ui.VStack(width=ui.Pixel(20)):
                        ui.Spacer()
                        self._open_file_picker_button = ui.Image(
                            "",
                            name="OpenFolder",
                            height=ui.Pixel(20),
                            mouse_pressed_fn=lambda x, y, b, m: self._on_output_pressed(b),
                            identifier="file_picker_button",
                        )
                        ui.Spacer()
                self._output_overlay = ui.Rectangle(name="DisabledOverlay", identifier="disabled_overlay")

            ui.Spacer(height=ui.Pixel(8))

            self._open_button = ui.Button(
                "Open in Explorer",
                clicked_fn=self._open_output_path,
                height=ui.Pixel(32),
                identifier="open_in_explorer_button",
            )

    def _open_output_path(self):
        if not self._update_open_button_state():
            return
        open_file_using_os_default(self._output_field.model.get_value_as_string())

    def _update_enable_state(self, *_):
        checked = self._override_checkbox.model.get_value_as_bool()
        if not checked:
            self._update_default_values()

        self._output_overlay.visible = not checked
        self._output_field.enabled = checked
        self._open_file_picker_button.enabled = checked

    def _update_default_values(self):
        context = omni.usd.get_context(self._context_name)
        if not context:
            return
        stage = context.get_stage()
        if not stage:
            return
        root_layer = stage.GetRootLayer()
        if not root_layer:
            return

        project_directory = str(_OmniUrl(_OmniUrl(root_layer.realPath).parent_url) / _REMIX_PACKAGE_FOLDER)
        self._output_field.model.set_value(project_directory)
        self._last_valid_path = project_directory

    def _update_output_valid(self):
        is_valid, error_message = self._validate_output_directory()
        self._output_field.style_type_name_override = "Field" if is_valid else "FieldError"
        self._output_field.tooltip = error_message
        self._output_validity_changed(is_valid)

        return is_valid

    def _update_open_button_state(self):
        output_dir_exists = _OmniUrl(self._output_field.model.get_value_as_string()).exists
        self._open_button.enabled = output_dir_exists
        self._open_button.tooltip = "" if output_dir_exists else "The output directory does not exist."

        return output_dir_exists

    def _on_output_field_changed(self, model):
        self._overlay_label.visible = not model.get_value_as_string()
        self._update_output_valid()

    def _on_output_field_end_edit(self, model):
        if self._update_output_valid():
            self._last_valid_path = model.get_value_as_string().strip()
        model.set_value(self._last_valid_path)

    def _on_output_directory_selected(self, output_dir: str):
        self._last_valid_path = output_dir
        self._output_field.model.set_value(output_dir)

    def _on_output_pressed(self, button):
        if button != 0 or not self._open_file_picker_button.enabled:
            return
        current_path = self._output_field.model.get_value_as_string()
        validation_error = ""

        def validate_selection(dirname, _):
            nonlocal validation_error

            is_valid, error_message = self._validate_output_directory(dirname)
            validation_error = error_message
            return is_valid

        def validation_failed(*_):
            nonlocal validation_error

            _TrexMessageDialog(
                validation_error,
                disable_cancel_button=True,
            )

        _open_file_picker(
            "Select a package output directory",
            self._on_output_directory_selected,
            lambda *args: None,
            current_file=current_path,
            select_directory=True,
            validate_selection=validate_selection,
            validation_failed_callback=validation_failed,
        )

    def _validate_output_directory(self, value: str = None):
        self._update_open_button_state()
        output_value = self._output_field.model.get_value_as_string() if value is None else value
        if not output_value or not output_value.strip():
            return False, "The output directory must be set"
        if not re.search(_REGEX_VALID_PATH, output_value):
            return False, "The output directory is not a valid path"
        return True, ""

    def _output_validity_changed(self, is_valid: bool):
        """Call the event object"""
        self.__output_validity_changed(is_valid)

    def subscribe_output_validity_changed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__output_validity_changed, function)

    def destroy(self):
        _reset_default_attrs(self)
