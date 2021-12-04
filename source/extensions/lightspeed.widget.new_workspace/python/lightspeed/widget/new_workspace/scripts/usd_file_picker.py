"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb
import os
from typing import Callable
import omni.client

from omni.kit.widget.filebrowser import FileBrowserItem
from omni.kit.window.filepicker import FilePickerDialog


def on_filter_item(dialog: FilePickerDialog, item: FileBrowserItem, show_folder_only=False) -> bool:
    if not item or item.is_folder:
        return True
    if not show_folder_only:
        if dialog.current_filter_option == 0:
            # Show only files with listed extensions
            _, ext = os.path.splitext(item.path)
            return ext in [".usd", ".usda", ".usdc"]
        else:
            # Show All Files (*)
            return True
    return False


def on_click_open(dialog: FilePickerDialog, filename: str, dirname: str, callback: Callable, show_folder_only=False):
    """
    The meat of the App is done in this callback when the user clicks 'Accept'. This is
    a potentially costly operation so we implement it as an async operation.  The inputs
    are the filename and directory name. Together they form the fullpath to the selected
    file.
    """
    if not dirname:
        carb.log_error("Please select a directory")
        return
    # Normally, you'd want to hide the dialog
    dialog.hide()
    if show_folder_only:
        callback(dirname)
    else:
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


def on_click_cancel(dialog: FilePickerDialog, filename: str, dirname: str, callback: Callable, show_folder_only=False):
    # Normally, you'd want to hide the dialog
    dialog.hide()
    if show_folder_only:
        callback(dirname)
    else:
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


def open_file_picker(callback: Callable, callback_cancel: Callable, show_folder_only=False):
    item_filter_options = None if show_folder_only else ["USD Files (*.usd, *.usda, *.usdc)", "All Files (*)"]

    dialog = FilePickerDialog(
        "Directory picker",
        apply_button_label="Select",
        click_apply_handler=lambda filename, dirname: on_click_open(
            dialog, filename, dirname, callback, show_folder_only=show_folder_only
        ),
        click_cancel_handler=lambda filename, dirname: on_click_cancel(
            dialog, filename, dirname, callback_cancel, show_folder_only=show_folder_only
        ),
        item_filter_options=item_filter_options,
        item_filter_fn=lambda item: on_filter_item(dialog, item, show_folder_only=show_folder_only),
    )
