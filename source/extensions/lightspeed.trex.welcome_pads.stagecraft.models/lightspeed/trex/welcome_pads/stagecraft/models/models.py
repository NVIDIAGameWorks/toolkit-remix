"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import Callable

from omni.flux.utils.widget.resources import get_icons as _get_icons
from omni.flux.welcome_pad.widget.model import Item


class NewWorkFileItem(Item):
    """Item of the model"""

    def __init__(self, on_mouse_pressed_callback: Callable):
        super().__init__()
        self._on_mouse_pressed_callback = on_mouse_pressed_callback

    def get_image(self) -> str:
        return _get_icons("new_workfile")

    def on_mouse_pressed(self):
        self._on_mouse_pressed_callback()

    @property
    def title(self):
        return "New WorkFile"

    @property
    def description(self):
        return "Build a fresh Mod..."
