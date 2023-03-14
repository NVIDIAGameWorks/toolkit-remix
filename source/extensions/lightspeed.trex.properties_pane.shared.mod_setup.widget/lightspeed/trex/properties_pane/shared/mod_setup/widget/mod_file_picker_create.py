"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
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
