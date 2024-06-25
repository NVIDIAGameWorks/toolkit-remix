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

from functools import partial
from typing import Callable

import omni.client
from lightspeed.common.constants import SAVE_USD_FILE_EXTENSIONS_OPTIONS
from lightspeed.trex.utils.widget import TrexMessageDialog
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker


def __confirm_override_dialog(path, callback):
    TrexMessageDialog(
        message=f"Are you sure you want to overwrite this mod file?\n\n{path}",
        ok_handler=callback,
        ok_label="Overwrite",
    )


def __on_click_open(callback: Callable, full_path: str):
    """
    The meat of the App is done in this callback when the user clicks 'Accept'. This is
    a potentially costly operation so we implement it as an async operation.  The inputs
    are the filename and directory name. Together they form the fullpath to the selected
    file.
    """
    result, entry = omni.client.stat(full_path)
    if result == omni.client.Result.OK and entry.flags & omni.client.ItemFlags.READABLE_FILE:
        __confirm_override_dialog(full_path, partial(callback, full_path))
    else:
        callback(full_path)


def open_file_picker_create(
    callback: Callable[[str], None],
    callback_cancel: Callable[[str], None],
    callback_validate: Callable[[str, str], bool],
    callback_validation_failed: Callable[[str, str], None],
    current_file: str = None,
):
    _open_file_picker(
        "Create a new mod file",
        partial(__on_click_open, callback),
        callback_cancel,
        apply_button_label="Create",
        current_file=current_file,
        file_extension_options=SAVE_USD_FILE_EXTENSIONS_OPTIONS,
        validate_selection=callback_validate,
        validation_failed_callback=callback_validation_failed,
    )
