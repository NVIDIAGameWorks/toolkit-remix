"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import json
import os
from pathlib import Path
from typing import Callable, Dict

import carb
import carb.tokens
import omni.client
from omni.kit.widget.filebrowser import FileBrowserItem
from omni.kit.window.filepicker import FilePickerDialog


class ReplacementPathUtils:
    def __get_recent_dir(self) -> str:
        """Return the file"""
        token = carb.tokens.get_tokens_interface()
        directory = token.resolve("${app_documents}")
        # FilePickerDialog needs the capital drive. In case it's linux, the
        # first letter will be / and it's still OK.
        return str(Path(directory[:1].upper() + directory[1:]).resolve())

    def __get_recent_file(self) -> str:
        """Return the file"""
        directory = self.__get_recent_dir()
        return f"{directory}/recent_replacement_paths.json"

    def save_recent_file(self, data):
        """Save the recent scenarios to the file"""
        file_path = self.__get_recent_file()
        with open(file_path, "w") as json_file:
            json.dump(data, json_file, indent=2)

        carb.log_info(f"Recent replacement paths file tracker saved to {file_path}")

    def append_path_to_recent_file(self, last_path: str, game: str, save: bool = True):
        """Append a scenario path to file"""
        current_data = self.get_recent_file_data()

        if game in current_data:
            del current_data[game]
        current_data[game] = {"last_path": last_path}
        current_data_max = list(current_data.keys())[:40]

        result = {}
        for current_path, current_data in current_data.items():
            if current_path in current_data_max:
                result[current_path] = current_data
        if save:
            self.save_recent_file(result)
        return result

    def is_recent_file_exist(self):
        file_path = self.__get_recent_file()
        if not Path(file_path).exists():
            carb.log_info(f"Recent replacement paths file tracker doesn't exist: {file_path}")
            return False
        return True

    def get_recent_file_data(self):
        """Load the recent scenarios from the file"""
        if not self.is_recent_file_exist():
            return {}
        file_path = self.__get_recent_file()
        carb.log_info(f"Get recent replacement paths file(s) from {file_path}")
        with open(file_path) as json_file:
            return json.load(json_file)


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


def open_file_picker(
    callback: Callable,
    callback_cancel: Callable,
    show_folder_only=False,
    current_directory: str = None,
    bookmarks: Dict = None,
):
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
        current_directory=current_directory,
    )
    if current_directory:
        dialog.navigate_to(current_directory)
    if bookmarks:
        for k, v in bookmarks.items():
            dialog.toggle_bookmark_from_path(k, v, True)
