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
from typing import TYPE_CHECKING

from lightspeed.common import constants
from omni.flux.utils.common import path_utils as _path_utils

if TYPE_CHECKING:
    from pxr import Sdf


def is_usd_file_path_valid_for_filepicker(dirname: str, filename: str) -> bool:
    """
    Check is a file path is a USD file, called from the file picker

    Args:
        dirname: the selected directory name that the filepicker gives
        filename: the selected file name that the filepicker gives

    Returns:
        True is valid
    """
    return is_usd_file_path_valid(f"{dirname}/{filename}", layer=None)


def is_usd_file_path_valid(path: str, layer: "Sdf.Layer" = None, log_error: bool = True) -> bool:
    """
    Check is a file path is a USD file

    Args:
        path: the file path to check
        layer: the file path can be relative to this layer
        log_error: log an error or not

    Returns:
        True is valid
    """
    if Path(path).suffix not in constants.USD_EXTENSIONS:
        return False
    return _path_utils.is_file_path_valid(path, layer=layer, log_error=log_error)
