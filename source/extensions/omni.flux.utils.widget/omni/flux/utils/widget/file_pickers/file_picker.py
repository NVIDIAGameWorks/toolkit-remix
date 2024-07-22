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

import fnmatch
import re
from pathlib import Path as _Path
from typing import Callable, Dict, List, Optional, Tuple, Union

import carb
import omni.client
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.kit.widget.filebrowser import FileBrowserItem as _FileBrowserItem
from omni.kit.widget.prompt import PromptButtonInfo, PromptManager
from omni.kit.window.filepicker import FilePickerDialog as _FilePickerDialog

LAST_SELECTED_DIRECTORY_SETTING = "/persistent/ext/omni.flux.utils.widget/last_selected_directory"
_file_picker_dialog = None


def _on_filter_item(
    dialog: _FilePickerDialog, item: _FileBrowserItem, extensions: List[str] = None, select_directory: bool = False
) -> bool:
    if not item or item.is_folder:
        return True
    if dialog.get_file_extension() != "*" and extensions:
        # Show only files with listed extensions
        return any(
            fnmatch.fnmatch(str(_Path(item.path).suffix), ext.strip()) for ext in dialog.get_file_extension().split(",")
        )
    return not select_directory


def _on_click_open(
    dialog: _FilePickerDialog,
    filename: str,
    dirname: str,
    callback: Callable[[Union[str, List[str]]], None],
    validate_selection: Optional[Union[Callable[[str, str], bool], Callable[[List[str]], bool]]],
    validation_failed_callback: Optional[Union[Callable[[str, str], None], Callable[[List[str]], None]]],
    extensions: List[str] = None,
    select_directory: bool = False,
    allow_multi_selection: bool = False,
):
    """
    The meat of the App is done in this callback when the user clicks 'Accept'. This is
    a potentially costly operation so we implement it as an async operation.  The inputs
    are the filename and directory name. Together they form the fullpath to the selected
    file.
    """
    if not dirname.endswith("/"):
        dirname = f"{dirname}/"

    selection_paths = dialog.get_current_selections()

    def fail_callback():
        if validation_failed_callback is not None:
            if allow_multi_selection:
                validation_failed_callback(selection_paths)
            else:
                validation_failed_callback(dirname, filename)
        else:
            carb.log_error("Validation failed")

    if not select_directory and not filename:
        fail_callback()
        return

    if not select_directory and not allow_multi_selection:
        # get_file_extension() will return something like "*.usd", or "*.usd*". If we have a simple extension like
        # "*.usda", or "*.usdc", or "*.jpg", we can auto add the extension
        # If we have something like "*.usd*" or "*.jpg, *.png, *.exr", we don't add an auto extension and show a message
        exts = dialog.get_file_extension().split(",")
        if not select_directory and exts and len(exts) == 1 and re.match("^\*.[a-zA-Z0-9]+$", exts[0].strip()):  # noqa
            if not select_directory and exts and not fnmatch.fnmatch(str(_Path(filename).suffix), exts[0].strip()):
                # we remove the *
                filename += exts[0].strip().replace("*", "")
        elif not select_directory and (
            not exts or (exts and not any(fnmatch.fnmatch(str(_Path(filename).suffix), ext.strip()) for ext in exts))
        ):
            PromptManager.post_simple_prompt(
                "Wrong file or extension",
                "Wrong file or please write the extension in your filename",
                ok_button_info=PromptButtonInfo("Okay", None),
                cancel_button_info=None,
                modal=True,
                no_title_bar=False,
            )
            return

    # Work around. If selection paths is empty but we have multi selection, we grab the path from the field.
    # It happens when something is written in the field, but nothing is selected in the UI.
    if allow_multi_selection and not selection_paths:
        result = __get_full_path(filename, dirname, select_directory)
        if result:
            selection_paths = [omni.client.normalize_url(result)]
        else:
            fail_callback()
            return

    if validate_selection is not None:
        if allow_multi_selection and not validate_selection(selection_paths):
            fail_callback()
            return
        if not allow_multi_selection and not validate_selection(dirname, filename):
            fail_callback()
            return

    # Normally, you'd want to hide the dialog
    dialog.hide()

    if allow_multi_selection:
        last_known_url = _OmniUrl(selection_paths[0])
        callback(selection_paths)
    else:
        selected_path = omni.client.normalize_url(__get_full_path(filename, dirname, select_directory))
        last_known_url = _OmniUrl(selected_path)
        callback(selected_path)

    # Set the last known directory
    if not select_directory:
        last_known_url = last_known_url.parent_url
    carb.settings.get_settings().set(LAST_SELECTED_DIRECTORY_SETTING, str(last_known_url))


def _on_click_cancel(
    dialog: _FilePickerDialog,
    filename: str,
    dirname: str,
    callback: Callable,
    select_directory: bool = False,
    allow_multi_selection: bool = False,
):
    # Normally, you'd want to hide the dialog
    dialog.hide()
    if allow_multi_selection:
        callback(dialog.get_current_selections())
    else:
        callback(omni.client.normalize_url(__get_full_path(filename, dirname, select_directory)))


def __get_full_path(filename, dirname, select_directory):
    if dirname:
        return f"{dirname}/{filename}" if not select_directory else dirname
    return filename if not select_directory else ""


def open_file_picker(
    title,
    callback: Callable[[Union[str, List[str]]], None],
    callback_cancel: Callable[[Union[str, List[str]]], None],
    apply_button_label: str = None,
    current_file: str = None,
    fallback=False,
    file_extension_options: List[Tuple[str, str]] = None,
    select_directory: bool = False,
    validate_selection: Optional[Union[Callable[[str, str], bool], Callable[[List[str]], bool]]] = None,
    validation_failed_callback: Optional[Union[Callable[[str, str], None], Callable[[List[str]], None]]] = None,
    bookmarks: Dict[str, str] = None,
    allow_multi_selection: bool = False,
):
    """
    Open a file picker

    Args:
        title: title of the window
        callback: function to execute when the user clicks on the select button. If allow_multi_selection is True,
            the input arg is a list of paths
        callback_cancel: function to execute when the user clicks on the cancel button. If allow_multi_selection is
            True, the input arg is a list of paths
        apply_button_label: The string to display in the "apply" button
        current_file: current file to select when the window is opened. If unset, the file browser will open at the last
                      known directory
        fallback: if True and if the file picker has a current folder, a default folder will be shown when the window
                  is opened
        file_extension_options: A list of filename extension options. Each list element is an (extension name,
                  description) pair.

                  Examples: ``(“*.usdc”, “Binary format”) or (“.usd*”, “USD format”) or (“*.png, *.jpg, *.exr”, “Image format”)``  # noqa
        select_directory: whether the file picker is used to select a directory or a file
        validate_selection: function to execute to validate the selected file/directory. If false, the window file will not be selected.
            If allow_multi_selection is True, the callback will take a list of file
        validation_failed_callback: function to call if the selection validation returns False.
            If allow_multi_selection is True, the callback will take a list of file
        bookmarks: Bookmarks to add to the file picker in the format { name: path }
        allow_multi_selection: Allow multi file selection in picker
    """
    global _file_picker_dialog
    if _file_picker_dialog is not None:
        destroy_file_picker()

    extensions = None
    # we copy the file_extension_options because if the value comes from a global variable, it will modify the global
    # variable
    tmp_file_extension_options = list(file_extension_options) if file_extension_options is not None else None
    if tmp_file_extension_options:
        extensions = [
            f".{ext.split('.')[-1]}" for ext_tuple in tmp_file_extension_options for ext in ext_tuple[0].split(",")
        ]
        all_files = ("*", "All Files (*)")
        if all_files not in tmp_file_extension_options:
            tmp_file_extension_options.append(all_files)
    elif select_directory:
        tmp_file_extension_options = [("", "")]
    else:
        tmp_file_extension_options = [("*", "All Files (*)")]
    file_path = _Path(current_file) if current_file else None
    # If not current file is given, try to get the last known directory
    navigate_to = current_file or carb.settings.get_settings().get(LAST_SELECTED_DIRECTORY_SETTING)
    dialog = _FilePickerDialog(
        title,
        apply_button_label=apply_button_label or "Select",
        click_apply_handler=lambda filename, dirname: _on_click_open(
            dialog,
            filename,
            dirname,
            callback,
            validate_selection,
            validation_failed_callback,
            extensions,
            select_directory,
            allow_multi_selection,
        ),
        click_cancel_handler=lambda filename, dirname: _on_click_cancel(
            dialog, filename, dirname, callback_cancel, select_directory, allow_multi_selection
        ),
        file_extension_options=tmp_file_extension_options,
        item_filter_fn=lambda item: _on_filter_item(dialog, item, extensions, select_directory),
        current_directory=str(file_path.parent if file_path.is_file() else file_path) if file_path else None,
        current_filename=str(file_path.name) if file_path and file_path.is_file() else None,
        allow_multi_selection=allow_multi_selection,
        enable_filename_input=not select_directory,
        show_grid_view=False,
    )
    dialog.hide()
    if fallback and dialog.get_current_directory():
        navigate_to = None
    if bookmarks:
        for name, path in bookmarks.items():
            dialog.toggle_bookmark_from_path(name, path, True)
    dialog.show(path=navigate_to)
    _file_picker_dialog = dialog


def destroy_file_picker(*args):
    global _file_picker_dialog
    if _file_picker_dialog is not None:
        _file_picker_dialog.destroy()
    _file_picker_dialog = None
