"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import Any, Callable

from omni.kit.viewport.menubar.camera import SingleCameraMenuItemBase


def lss_single_camera_menu_item(*args, lss_option_clicked: Callable[[str], Any] = None, **kwargs):
    class LssSingleCameraMenuItem(SingleCameraMenuItemBase):
        def _option_clicked(self):
            lss_option_clicked(self.camera_path.pathString)

    return LssSingleCameraMenuItem(*args, **kwargs)
