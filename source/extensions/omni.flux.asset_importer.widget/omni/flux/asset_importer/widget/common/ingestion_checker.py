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

import omni.kit
import omni.ui as ui
from omni.flux.asset_importer.core.data_models import SUPPORTED_ASSET_EXTENSIONS as _SUPPORTED_ASSET_EXTENSIONS
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.kit.widget.prompt import PromptButtonInfo, PromptManager

DIALOG_TITLE = "Invalid Selection"


class IngestionValidationFailureDialog:
    _BUTTON_HEIGHT = ui.Pixel(16)
    _BUTTON_WIDTH = ui.Pixel(64)
    _ERROR_WINDOW_HEIGHT = 400
    _ERROR_WINDOW_WIDTH = 600
    _ICON_SIZE = ui.Pixel(16)
    _MIN_FILE_LIST_HEIGHT = 200
    _SPACING_PIXELS = ui.Pixel(8)

    def __init__(self):
        self._error_window = None
        self._content = None
        self._callback = None

    async def destroy_dialog(self):
        if self._error_window:
            self._error_window.destroy()
        if self._callback:
            self._callback()

    def _close_window(self):
        if self._error_window:
            self._error_window.visible = False
            asyncio.ensure_future(self.destroy_dialog())

    def _copy_paths(self):
        omni.kit.clipboard.copy(self._content)

    def show_error_dialog(self, bad_exts, bad_dirs, supported_extensions, callback=None):
        msg_lines = []
        content_lines = []
        self._callback = callback

        if bad_dirs:
            msg_lines.append("Directories cannot be ingested")
            content_lines.extend([str(bad) for bad in bad_dirs])
        if bad_exts:
            msg_lines.append("The following file types are supported:")
            msg_lines.append(", ".join(supported_extensions))
            content_lines.extend([str(bad) for bad in bad_exts])

        self._content = "\r\n".join(content_lines)
        # Calculate the expected visual height to display the file list
        num_lines = len(content_lines)
        file_list_height = self._MIN_FILE_LIST_HEIGHT if num_lines < 12 else ((16 * num_lines) + 24)

        self._error_window = ui.Window(
            DIALOG_TITLE,
            height=self._ERROR_WINDOW_HEIGHT,
            width=self._ERROR_WINDOW_WIDTH,
            dockPreference=ui.DockPreference.DISABLED,
            flags=(
                ui.WINDOW_FLAGS_NO_COLLAPSE
                | ui.WINDOW_FLAGS_NO_MOVE
                | ui.WINDOW_FLAGS_NO_RESIZE
                | ui.WINDOW_FLAGS_NO_CLOSE
                | ui.WINDOW_FLAGS_MODAL
            ),
        )
        with self._error_window.frame:
            with ui.HStack(spacing=self._SPACING_PIXELS):
                ui.Spacer(height=0, width=0)
                with ui.VStack(spacing=self._SPACING_PIXELS):
                    ui.Spacer(height=0, width=0)
                    for pos, msg in enumerate(msg_lines):
                        ui.Label(
                            msg,
                            identifier=f"msg_label{pos}",
                            name="PropertiesWidgetLabel",
                            height=0,
                        )
                    ui.Spacer(height=0)
                    ui.Line(name="PropertiesPaneSectionTitle", height=0)
                    ui.Spacer(height=0)
                    with ui.HStack(height=0):
                        ui.Label(
                            f"Invalid file path{'s' if len(content_lines) > 1 else ''}",
                            height=0,
                            identifier="bad_label",
                        )
                        ui.Image(
                            "",
                            name="Duplicate",
                            tooltip="Copy path list",
                            identifier="copy_paths_button",
                            height=self._ICON_SIZE,
                            width=self._ICON_SIZE,
                            mouse_released_fn=lambda *args: self._copy_paths(),
                        )
                        ui.Spacer(width=2 * self._SPACING_PIXELS)
                    with ui.ScrollingFrame(name="TreePanelBackground"):
                        content_field = ui.StringField(
                            name="TreePanelBackground",
                            read_only=True,
                            height=ui.Pixel(max(self._MIN_FILE_LIST_HEIGHT, file_list_height)),
                            identifier="content_string_field",
                            style_type_name_override="Rectangle",
                        )
                        content_field.model.set_value(self._content)
                    with ui.HStack(height=0):
                        ui.Spacer()
                        ui.Button(
                            "Okay",
                            clicked_fn=self._close_window,
                            width=self._BUTTON_WIDTH,
                            height=self._BUTTON_HEIGHT,
                            alignment=ui.Alignment.CENTER,
                            identifier="ingestion_error_ok_button",
                        )
                        ui.Spacer()
                    ui.Spacer(height=0, width=0)
                ui.Spacer(height=0, width=0)


def _validate_selection(filenames, supported_extensions=None, return_values=False):
    file_paths = [_OmniUrl(filename) for filename in filenames]
    bad_exts = [pth for pth in file_paths if pth.suffix and pth.suffix.lower() not in supported_extensions]
    bad_dirs = [pth for pth in file_paths if pth.is_directory]
    if return_values:
        return (bad_exts, bad_dirs)
    return not any([bad_exts, bad_dirs])


def _validation_failed_callback(filenames, supported_extensions=None, callback=None):
    if len(filenames) == 0:
        PromptManager.post_simple_prompt(
            "Nothing selected",
            "No file was selected",
            ok_button_info=PromptButtonInfo("Okay", None),
            modal=True,
        )
        return
    # Get the failures
    bad_exts, bad_dirs = _validate_selection(filenames, supported_extensions, return_values=True)
    handler = IngestionValidationFailureDialog()
    handler.show_error_dialog(bad_exts, bad_dirs, supported_extensions, callback=callback)


validate_file_selection = functools.partial(_validate_selection, supported_extensions=_SUPPORTED_ASSET_EXTENSIONS)
validate_texture_selection = functools.partial(_validate_selection, supported_extensions=_SUPPORTED_TEXTURE_EXTENSIONS)
file_validation_failed_callback = functools.partial(
    _validation_failed_callback, supported_extensions=_SUPPORTED_ASSET_EXTENSIONS
)
texture_validation_failed_callback = functools.partial(
    _validation_failed_callback, supported_extensions=_SUPPORTED_TEXTURE_EXTENSIONS
)
