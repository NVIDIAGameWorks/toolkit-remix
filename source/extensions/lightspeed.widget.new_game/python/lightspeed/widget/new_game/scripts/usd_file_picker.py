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
from lightspeed.common.constants import CAPTURE_FOLDER
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker


def __validate_selection(_: str, dirname: str):
    """
    The meat of the App is done in this callback when the user clicks 'Accept'. This is
    a potentially costly operation so we implement it as an async operation.  The inputs
    are the filename and directory name. Together they form the fullpath to the selected
    file.
    """
    if not dirname or not Path(dirname).exists() or str(Path(dirname).stem) != CAPTURE_FOLDER:
        carb.log_error(f'Please select a folder named "{CAPTURE_FOLDER}"')
        return False
    return True


def open_file_picker(callback: Callable, callback_cancel: Callable):
    _open_file_picker(
        "Select a capture directory",
        callback,
        callback_cancel,
        select_directory=True,
        validate_selection=__validate_selection,
    )
