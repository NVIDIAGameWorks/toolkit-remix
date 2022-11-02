"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import Callable

import carb
import omni.ui as ui
from lightspeed.error_popup.window import ErrorPopup as _ErrorPopup
from lightspeed.export.core import LightspeedExporterCore as _LightspeedExporterCore
from lightspeed.layer_manager.constants import LSS_LAYER_MOD_NOTES
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.progress_popup.window import ProgressPopup as _ProgressPopup
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker
from omni.flux.utils.widget.label import create_label_with_font as _create_label_with_font


class SetupUI:
    def __init__(self, context_name: str = ""):
        self._default_attr = {
            "_exporter": None,
            "_layer_manager": None,
            "_progress_popup": None,
            "_error_popup": None,
            "_file_title_provider": None,
            "_notes_title_provider": None,
            "_mod_output_dir_field": None,
            "_overlay_mod_output_label": None,
            "_notes_field": None,
            "_export_widget": None,
            "_disabled_export_widget": None,
            "_sub_mod_output_dir_field_changed": None,
            "_sub_progress_changed": None,
            "_sub_progress_text_changed": None,
            "_sub_finish_export": None,
            "_sub_export_readonly_error": None,
            "_sub_dependency_errors": None,
            "_sub_dependency_errors_yes": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._exporter = _LightspeedExporterCore(context_name=context_name)
        self._layer_manager = _LayerManagerCore(context_name=context_name)

        self._progress_popup = None

        self._sub_progress_changed = self._exporter.subscribe_progress_changed(self._on_progress_changed)
        self._sub_progress_text_changed = self._exporter.subscribe_progress_text_changed(self._on_progress_text_changed)
        self._sub_finish_export = self._exporter.subscribe_finish_export(self._on_finish_export)
        self._sub_export_readonly_error = self._exporter.subscribe_export_readonly_error(self._on_export_readonly_error)
        self._sub_dependency_errors = self._exporter.subscribe_dependency_errors(self._on_dependency_errors)

        self.__on_directory_changed = _Event()

        self.__create_ui()

    def __create_ui(self):
        with ui.VStack():
            ui.Spacer(height=ui.Pixel(16))
            self._file_title_provider, _, _ = _create_label_with_font("Directory", "PropertiesPaneSectionTitle")
            ui.Spacer(height=ui.Pixel(8))
            with ui.HStack():
                with ui.ZStack():
                    self._mod_output_dir_field = ui.StringField(height=ui.Pixel(18), name="USDPropertiesWidgetValue")
                    self._sub_mod_output_dir_field_changed = (
                        self._mod_output_dir_field.model.subscribe_value_changed_fn(
                            self._on_mod_output_dir_field_changed
                        )
                    )
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8))
                        with ui.Frame(horizontal_clipping=True):
                            self._overlay_mod_output_label = ui.Label(
                                "Mod output file path...",
                                name="USDPropertiesWidgetValueOverlay",
                                width=0,
                                height=ui.Pixel(24),
                            )
                ui.Spacer(width=ui.Pixel(8))
                with ui.VStack(width=ui.Pixel(20)):
                    ui.Spacer()
                    ui.Image(
                        "",
                        name="OpenFolder",
                        height=ui.Pixel(20),
                        mouse_pressed_fn=lambda x, y, b, m: self._on_output_dir_pressed(b),
                    )
                    ui.Spacer()
            ui.Spacer(height=ui.Pixel(16))
            self._notes_title_provider, _, _ = _create_label_with_font("Notes", "PropertiesPaneSectionTitle")
            ui.Spacer(height=ui.Pixel(8))
            self._notes_field = ui.StringField(multiline=True, height=ui.Pixel(90))
            ui.Spacer(height=ui.Pixel(8))
            with ui.HStack():
                ui.Spacer(height=0)
                self._export_widget = ui.Button(
                    "Export", name="ExportButton", width=ui.Pixel(64), clicked_fn=self._on_export_pressed
                )

    def refresh(self):
        self._get_default_output_dir()
        self._export_widget.enabled = self._validate_output_path(self._mod_output_dir_field.model)

    def _get_default_output_dir(self):
        default_path = self._exporter.get_default_export_path(create_if_not_exist=True)
        if default_path and not self._mod_output_dir_field.model.get_value_as_string():
            self._mod_output_dir_field.model.set_value(default_path)
        self._directory_changed(self._mod_output_dir_field.model.get_value_as_string())

    def _validate_output_path(self, model):
        output_dir = model.get_value_as_string()
        if output_dir is None or not output_dir.strip():
            return False
        return self._exporter.check_export_path(output_dir, lambda _, message: carb.log_error(message))

    def _on_mod_output_dir_field_changed(self, model):
        self._overlay_mod_output_label.visible = not model.get_value_as_string()
        is_valid = self._validate_output_path(model)
        self._export_widget.enabled = is_valid
        self._mod_output_dir_field.style_type_name_override = "Field" if is_valid else "FieldError"
        self._directory_changed(model.get_value_as_string())

    def _on_output_dir_pressed(self, button):
        if button != 0:
            return
        current_path = self._mod_output_dir_field.model.get_value_as_string()
        _open_file_picker(
            "Select Mod Output Directory",
            self._on_directory_selected,
            lambda *args: None,
            current_path,
            select_directory=True,
            validate_selection=lambda dirname, _: self._exporter.check_export_path(dirname, self._show_error_popup),
        )

    def _on_directory_selected(self, dirname):
        self._mod_output_dir_field.model.set_value(dirname)

    def _show_error_popup(self, title, message):
        self._error_popup = _ErrorPopup(title, message, "", window_size=(400, 120))
        self._error_popup.show()
        carb.log_error(message)

    def _on_export_pressed(self, validate_dependencies=True):
        output_dir = self._mod_output_dir_field.model.get_value_as_string()
        output_notes = self._notes_field.model.get_value_as_string()

        self._exporter.set_layer_custom_data(LSS_LAYER_MOD_NOTES, output_notes)

        # Show progress bar
        self._show_progress_popup()

        # Export saves the current stage
        self._exporter.export(output_dir, validate_dependencies)

    def _show_progress_popup(self):
        if not self._progress_popup:
            self._progress_popup = _ProgressPopup("Exporting")
            self._progress_popup.set_cancel_fn(self._exporter.cancel)
        self._progress_popup.progress = 0
        self._progress_popup.show()

    def _on_progress_changed(self, progress: float):
        self._progress_popup.progress = progress

    def _on_progress_text_changed(self, text: str):
        self._progress_popup.status_text = text

    def _on_finish_export(self):
        self._progress_popup.hide()

    def _on_export_readonly_error(self, read_only_paths):
        self._progress_popup.hide()

        title = "Read-Only Error Occurred"
        message = (
            "One or more path in your export folder is read-only. "
            "Change the file or folder permissions to fix this issue."
        )
        details = "\n".join(read_only_paths)

        self._error_popup = _ErrorPopup(title, message, details)
        self._error_popup.show()

    def _on_dependency_errors(self, dependency_errors):
        self._progress_popup.hide()

        details = ""
        for type_error, data in dependency_errors.items():
            details += f"\n{type_error} ({len(data.keys())} errors):\n"
            for key, error_type in data.items():
                details += "-" * 100
                details += "\n"
                details += f"       {key}:\n                {error_type}\n"

        title = "Dependency Errors Occurred"
        message = (
            "There are dependencies in your stage that have errors, please double check. "
            "Do you want to continue the export?"
        )

        self._error_popup = _ErrorPopup(title, message, details, yes_no=True, window_size=(1000, 600))
        self._sub_dependency_errors_yes = self._error_popup.subscribe_yes_clicked(self._on_export_pressed(False))
        self._error_popup.show()

    def _directory_changed(self, new_directory: str):
        """Call the event object that has the list of functions"""
        self.__on_directory_changed(new_directory)

    def subscribe_directory_changed(self, func: Callable):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_directory_changed, func)

    def destroy(self):
        _reset_default_attrs(self)
