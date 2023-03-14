"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from pathlib import Path
from typing import Callable, Optional

import carb
from lightspeed.common import constants as _constants
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni import ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.file_pickers import open_file_picker as _open_file_picker


class FilePickerWidget:
    def __init__(
        self,
        title: str,
        select_directory: bool,
        validate_callback: Callable[[str], Optional[str]],
        selected_callback: Callable[[Optional[str]], None],
        current_path: Optional[str] = None,
        apply_button_label: str = "Select",
        placeholder_label: str = "",
    ):
        self._default_attr = {
            "_title": None,
            "_select_directory": None,
            "_validate_callback": None,
            "_selected_callback": None,
            "_current_path": None,
            "_apply_button_label": None,
            "_placeholder_label": None,
            "_validation_error": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._title = title
        self._select_directory = select_directory
        self._validate_callback = validate_callback
        self._selected_callback = selected_callback
        self._current_path = current_path
        self._apply_button_label = apply_button_label
        self._placeholder_label = placeholder_label

        self._validation_error = False

        self._create_ui()

    def set_validation_error(self, error: str):
        if not self._dir_field:
            return

        self._dir_field.style_type_name_override = "FieldError" if error else "Field"
        self._dir_field.tooltip = f"ERROR: {error}" if error else ""

    def _create_ui(self):
        with ui.HStack(height=0):
            with ui.ZStack():
                self._dir_field = ui.StringField(
                    height=ui.Pixel(18), style_type_name_override="Field", identifier="FilePickerInput"
                )
                self._sub_dir_field_changed = self._dir_field.model.subscribe_value_changed_fn(
                    self.__validate_field_selection
                )
                self._sub_dir_field_end = self._dir_field.model.subscribe_end_edit_fn(self.__field_item_changed)
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(8))
                    with ui.Frame(horizontal_clipping=True):
                        self._placeholder = ui.Label(
                            self._placeholder_label,
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
                    identifier="FilePickerIcon",
                    height=ui.Pixel(20),
                    mouse_pressed_fn=self.__open_dialog,
                )
                ui.Spacer()

        if self._current_path:
            self._dir_field.model.set_value(str(self._current_path))

    def __path_selected_callback(self, path: str):
        self._dir_field.model.set_value(path)
        self._selected_callback(path)

    def __validate_dialog_selection(self, dirname: str, filename: str):
        self._validation_error = self._validate_callback(str(Path(dirname) / filename))
        return not bool(self._validation_error)

    def __validate_field_selection(self, model):
        self._placeholder.visible = not bool(model.get_value_as_string())
        self._validation_error = self._validate_callback(model.get_value_as_string())
        self.set_validation_error(self._validation_error)

    def __field_item_changed(self, model):
        if self._validation_error:
            carb.log_error(
                f"The selected {'directory' if self._select_directory else 'file'} is invalid: {self._validation_error}"
            )
            self._selected_callback(None)
        else:
            self._selected_callback(model.get_value_as_string())

    def __show_validation_failed_dialog(self, *_):
        _TrexMessageDialog(
            f"The selected {'directory' if self._select_directory else 'file'} is invalid: {self._validation_error}",
            disable_cancel_button=True,
        )

    def __open_dialog(self, _x, _y, b, _m):
        if b != 0:
            return
        _open_file_picker(
            self._title,
            self.__path_selected_callback,
            lambda *_: None,
            apply_button_label=self._apply_button_label,
            file_extension_options=[] if self._select_directory else _constants.SAVE_USD_FILE_EXTENSIONS_OPTIONS,
            select_directory=self._select_directory,
            validate_selection=self.__validate_dialog_selection,
            validation_failed_callback=self.__show_validation_failed_dialog,
        )

    def destroy(self):
        """Destroy."""
        _reset_default_attrs(self)
