"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from pathlib import Path
from typing import Callable

import carb
from lightspeed.common.constants import GAME_READY_ASSETS_FOLDER
from omni.kit.widget.filebrowser import FileBrowserItem
from omni.kit.window.filepicker import FilePickerDialog


def on_filter_item(dialog: FilePickerDialog, item: FileBrowserItem) -> bool:
    if not item or item.is_folder:
        return True
    return False


def on_click_open(dialog: FilePickerDialog, filename: str, dirname: str, callback: Callable):
    """
    The meat of the App is done in this callback when the user clicks 'Accept'. This is
    a potentially costly operation so we implement it as an async operation.  The inputs
    are the filename and directory name. Together they form the fullpath to the selected
    file.
    """
    if not dirname or not Path(dirname).exists() or str(Path(dirname).stem) != GAME_READY_ASSETS_FOLDER:
        carb.log_error(f'Please select a folder named "{GAME_READY_ASSETS_FOLDER}"')
        return
    # Normally, you'd want to hide the dialog
    dialog.hide()
    callback(dirname)


def on_click_cancel(dialog: FilePickerDialog, filename: str, dirname: str, callback: Callable):
    # Normally, you'd want to hide the dialog
    dialog.hide()
    callback(dirname)


def open_file_picker(callback: Callable, callback_cancel: Callable, current_directory: str = None):
    dialog = FilePickerDialog(
        "Directory picker",
        apply_button_label="Select",
        click_apply_handler=lambda filename, dirname: on_click_open(dialog, filename, dirname, callback),
        click_cancel_handler=lambda filename, dirname: on_click_cancel(dialog, filename, dirname, callback_cancel),
        item_filter_fn=lambda item: on_filter_item(dialog, item),
        current_directory=current_directory,
    )
