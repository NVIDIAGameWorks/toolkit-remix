"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import os
from typing import Callable

import carb
import omni.client
from omni.kit.widget.filebrowser import FileBrowserItem
from omni.kit.window.filepicker import FilePickerDialog


def on_filter_item(dialog: FilePickerDialog, item: FileBrowserItem) -> bool:
    if not item or item.is_folder:
        return True
    if dialog.current_filter_option == 0:
        # Show only files with listed extensions
        _, ext = os.path.splitext(item.path)
        return ext in [".usd", ".usda", ".usdc"]
    else:
        # Show All Files (*)
        return True


def on_click_save(dialog: FilePickerDialog, filename: str, dirname: str, callback: Callable):
    """
    The meat of the App is done in this callback when the user clicks 'Accept'. This is
    a potentially costly operation so we implement it as an async operation.  The inputs
    are the filename and directory name. Together they form the fullpath to the selected
    file.
    """
    # Normally, you'd want to hide the dialog
    dialog.hide()
    if not filename:
        carb.log_warn("No filename provided!")
        return

    ok = False
    for ext in [".usd", ".usda", ".usdc"]:
        if filename.endswith(ext):
            ok = True
            break
    if not ok:
        filename = filename + ".usd"

    if dirname:
        fullpath = f"{dirname}/{filename}"
    else:
        fullpath = filename
    callback(omni.client.normalize_url(fullpath))


def on_click_cancel(dialog: FilePickerDialog, filename: str, dirname: str, callback: Callable):
    # Normally, you'd want to hide the dialog
    dialog.hide()
    if not filename:
        carb.log_warn("No filename provided!")
        return

    ok = False
    for ext in [".usd", ".usda", ".usdc"]:
        if filename.endswith(ext):
            ok = True
            break
    if not ok:
        filename = filename + ".usd"

    if dirname:
        fullpath = f"{dirname}/{filename}"
    else:
        fullpath = filename
    callback(omni.client.normalize_url(fullpath))


def open_file_picker(callback_save: Callable, callback_cancel: Callable):
    item_filter_options = ["USD Files (*.usd, *.usda, *.usdc)", "All Files (*)"]

    dialog = FilePickerDialog(
        "Open Game Workspace",
        allow_multi_selection=False,
        apply_button_label="Open",
        click_apply_handler=lambda filename, dirname: on_click_save(dialog, filename, dirname, callback_save),
        click_cancel_handler=lambda filename, dirname: on_click_cancel(dialog, filename, dirname, callback_cancel),
        item_filter_options=item_filter_options,
        item_filter_fn=lambda item: on_filter_item(dialog, item),
    )
