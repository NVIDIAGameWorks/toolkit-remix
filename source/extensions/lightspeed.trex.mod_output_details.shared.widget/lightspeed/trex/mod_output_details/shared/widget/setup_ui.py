"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio

import omni.client
import omni.ui as ui
import omni.usd
from lightspeed.trex.replacement.core.shared import Setup as _ReplacementCore
from omni.flux.property_widget_builder.model.file import CustomFileAttributeItem as _CustomFileAttributeItem
from omni.flux.property_widget_builder.model.file import FileAttributeItem as _FileAttributeItem
from omni.flux.property_widget_builder.model.file import FileDelegate as _FileDelegate
from omni.flux.property_widget_builder.model.file import FileModel as _FileModel
from omni.flux.property_widget_builder.widget import PropertyWidget as _PropertyWidget
from omni.flux.utils.common import async_wrap as _async_wrap
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.label import create_label_with_font as _create_label_with_font


class SetupUI:
    def __init__(self, context_name: str = ""):
        self._default_attr = {
            "_refresh_task": None,
            "_replacement_core": None,
            "_properties_frame": None,
            "_file_properties_widget": None,
            "_selected_directory": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._refresh_task = None
        self._replacement_core = _ReplacementCore(context_name=context_name)
        self._file_properties_widget = None
        self._selected_directory = None

        self.__create_ui()

    def __create_ui(self):
        with ui.VStack():
            ui.Spacer(height=ui.Pixel(16))
            self._properties_frame = ui.Frame()
            ui.Spacer(height=ui.Pixel(16))

    def set_selected_directory(self, value):
        directory = value
        # Makes sure omni.client attempts to list the directory files even if it doesn't end with a "/" or "\"
        if not directory.endswith("\\") and not directory.endswith("/"):
            directory = directory + "\\"
        self._selected_directory = directory
        self.refresh()

    def refresh(self):
        self.__create_text_ui("Reading existing mod file...")
        if self._refresh_task:
            self._refresh_task.cancel()
        self._refresh_task = asyncio.ensure_future(_async_wrap(self._refresh_async)())

    def _refresh_async(self):
        file_attributes = []
        mod_file_model = None
        mod_file_delegate = None
        no_file_message = "No existing mod file was found..."

        existing_mod_file = self._replacement_core.get_existing_mod_file(self._selected_directory)
        layer_notes = self._replacement_core.get_layer_notes(existing_mod_file) or "No notes"
        if existing_mod_file:
            multiline_notes = (True, 5) if "\n" in layer_notes else (False, 0)
            file_attributes.append(_CustomFileAttributeItem([layer_notes], "Notes", multiline_notes))

            for attr in [attr for attr in dir(omni.client.ListEntry) if not attr.startswith("_")]:
                file_attributes.append(
                    _FileAttributeItem(existing_mod_file, attr, display_attr_name=attr.replace("_", " ").capitalize())
                )

            mod_file_delegate = _FileDelegate()
            mod_file_model = _FileModel(existing_mod_file)
            mod_file_model.set_items(file_attributes)

        # If we find a mod file, display the attributes
        if file_attributes:
            self._properties_frame.clear()
            with self._properties_frame:
                self._file_properties_widget = _PropertyWidget(mod_file_model, mod_file_delegate)
        else:
            self.__create_text_ui(no_file_message)

    def __create_text_ui(self, message):
        self._properties_frame.clear()
        with self._properties_frame:
            with ui.HStack():
                ui.Spacer()
                _create_label_with_font(message, "PropertiesWidgetLabel", remove_offset=False)
                ui.Spacer()

    def destroy(self):
        _reset_default_attrs(self)
