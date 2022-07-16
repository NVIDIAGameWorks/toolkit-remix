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
import omni.client
from lightspeed.trex.utils.widget import TrexMessageDialog
from omni.kit.widget.filebrowser import FileBrowserItem
from omni.kit.window.filepicker import FilePickerDialog


def _confirm_override_dialog(path, callback):
    def on_okay_clicked(dialog: TrexMessageDialog):
        dialog.hide()
        callback()

    def on_cancel_clicked(dialog: TrexMessageDialog):
        dialog.hide()

    message = f"Are you sure you want to override this mod file?\n{path}\nOverriding will erase the current file."

    dialog = TrexMessageDialog(
        width=600,
        message=message,
        ok_handler=on_okay_clicked,
        cancel_handler=on_cancel_clicked,
        ok_label="Yes",
        disable_cancel_button=False,
    )
    dialog.show()


def on_filter_item(dialog: FilePickerDialog, item: FileBrowserItem) -> bool:
    if not item or item.is_folder:
        return True
    if dialog.current_filter_option == 0:
        # Show only files with listed extensions
        return str(Path(item.path).suffix) in [".usd", ".usda", ".usdc"]
    return True


def __generate_full_path(dirname, filename):
    if not filename:
        return None

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
    return omni.client.normalize_url(fullpath)


def on_click_open(dialog: FilePickerDialog, filename: str, dirname: str, callback: Callable):
    """
    The meat of the App is done in this callback when the user clicks 'Accept'. This is
    a potentially costly operation so we implement it as an async operation.  The inputs
    are the filename and directory name. Together they form the fullpath to the selected
    file.
    """

    def do():
        dialog.hide()
        callback(fullpath)

    fullpath = __generate_full_path(dirname, filename)
    if not fullpath:
        carb.log_error("Invalid filename!")
        return
    result, entry = omni.client.stat(fullpath)
    if result == omni.client.Result.OK and entry.flags & omni.client.ItemFlags.READABLE_FILE:
        _confirm_override_dialog(fullpath, do)
    else:
        do()


def on_click_cancel(dialog: FilePickerDialog, filename: str, dirname: str, callback: Callable):
    # Normally, you'd want to hide the dialog
    dialog.hide()
    fullpath = __generate_full_path(dirname, filename)
    if not fullpath:
        return
    callback(fullpath)


def open_file_picker_create(callback: Callable, callback_cancel: Callable, current_file: str = None):
    item_filter_options = ["USD Files (*.usd, *.usda, *.usdc)", "All Files (*)"]
    p_file = Path(current_file) if current_file else None
    dialog = FilePickerDialog(
        "Mod File create",
        apply_button_label="Create",
        click_apply_handler=lambda filename, dirname: on_click_open(dialog, filename, dirname, callback),
        click_cancel_handler=lambda filename, dirname: on_click_cancel(dialog, filename, dirname, callback_cancel),
        item_filter_fn=lambda item: on_filter_item(dialog, item),
        item_filter_options=item_filter_options,
        current_directory=str(p_file.parent) if p_file else None,
        current_filename=str(p_file.name) if p_file else None,
        allow_multi_selection=False,
    )
    if current_file:
        dialog.navigate_to(str(p_file))
