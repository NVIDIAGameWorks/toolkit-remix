"""
* Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
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
