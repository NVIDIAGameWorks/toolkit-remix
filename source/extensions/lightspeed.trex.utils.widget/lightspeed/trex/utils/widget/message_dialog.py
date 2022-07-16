"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.ui as ui
from omni.kit.window.popup_dialog import MessageDialog


class TrexMessageDialog(MessageDialog):
    WINDOW_FLAGS = ui.WINDOW_FLAGS_NO_RESIZE
    WINDOW_FLAGS |= ui.WINDOW_FLAGS_POPUP
    WINDOW_FLAGS |= ui.WINDOW_FLAGS_NO_SCROLLBAR
    WINDOW_FLAGS |= ui.WINDOW_FLAGS_NO_BACKGROUND
