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
from pathlib import Path
from typing import Callable

import carb
from lightspeed.common.constants import CAPTURE_FOLDER
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker


def __validate_selection(dirname: str, _: str):
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
