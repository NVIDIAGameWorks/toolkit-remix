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
    def on_okay_clicked(dialog: TrexMessageDialog):
        dialog.hide()
        callback()

    def on_cancel_clicked(dialog: TrexMessageDialog):
        dialog.hide()

    message = f"Are you sure you want to overwrite this mod file?\n\n{path}"

    dialog = TrexMessageDialog(
        message=message,
        ok_handler=on_okay_clicked,
        cancel_handler=on_cancel_clicked,
        ok_label="Overwrite",
        disable_cancel_button=False,
    )
    dialog.show()


def __on_click_open(full_path: str, callback: Callable):
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


def open_file_picker_create(callback: Callable, callback_cancel: Callable, current_file: str = None):
    _open_file_picker(
        "Create a new mod file",
        lambda full_path: __on_click_open(full_path, callback),
        callback_cancel,
        apply_button_label="Create",
        current_file=current_file,
        file_extension_options=SAVE_USD_FILE_EXTENSIONS_OPTIONS,
    )
