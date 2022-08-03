"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import Callable, Dict

import omni.ui as ui
from omni.flux.utils.widget.resources import get_icons as _get_icons
from omni.flux.welcome_pad.widget.model import Item


class NewWorkFileItem(Item):
    """Item of the model"""

    def __init__(self, on_mouse_pressed_callback: Callable):
        super().__init__()
        self._on_mouse_pressed_callback = on_mouse_pressed_callback
        self.__is_hovered = False

    def get_image(self) -> str:
        return _get_icons("new_workfile")

    def on_mouse_pressed(self):
        return

    def on_mouse_released(self):
        if self.__is_hovered:
            self._on_mouse_pressed_callback()

    def on_hovered(self, hovered):
        """Action that will be called when the item is hovered on"""
        self.__is_hovered = hovered

    def on_description_scrolled_x(self, x):
        """Action that will be called when the description is scrolled on x"""
        return

    def on_description_scrolled_y(self, y):
        """Action that will be called when the description is scrolled on y"""
        return

    @property
    def title(self):
        return "New WorkFile"

    @property
    def description(self):
        return "Build a fresh Mod..."


class RecentWorkFileItem(Item):
    """Item of the model"""

    def __init__(
        self, title: str, description: Dict[str, str], image_fn: Callable, on_mouse_pressed_callback: Callable
    ):
        self.__title = title
        self.__description = description
        self.__image_fn = image_fn
        super().__init__()
        self.__is_hovered = False
        self.__is_scrolled = False
        self.use_description_override_delegate = True
        self._on_mouse_pressed_callback = on_mouse_pressed_callback

    def get_image(self) -> str:
        return self.__image_fn()

    def on_mouse_pressed(self):
        return

    def on_mouse_released(self):
        if self.__is_scrolled:
            self.__is_scrolled = False
            return
        if self.__is_hovered:
            self._on_mouse_pressed_callback()

    def on_hovered(self, hovered):
        """Action that will be called when the item is hovered on"""
        self.__is_hovered = hovered

    def on_description_scrolled_x(self, x):
        """Action that will be called when the description is scrolled on x"""
        self.__is_scrolled = True

    def on_description_scrolled_y(self, y):
        """Action that will be called when the description is scrolled on y"""
        self.__is_scrolled = True

    @property
    def title(self):
        return self.__title

    def description_override_delegate(self):
        """If use_description_override_delegate is True, this function will be executed to draw the description

        Returns:
            The created widget
        """
        stack = ui.VStack()
        with stack:
            for detail_key, detail_value in self.__description.items():
                with ui.HStack():
                    ui.Label(
                        f"{detail_key}:",
                        name="WelcomePadItemDescription",
                        checked=not self.enabled,
                        width=ui.Pixel(80),
                        alignment=ui.Alignment.RIGHT,
                    )
                    ui.Spacer(width=ui.Pixel(8))
                    ui.Label(str(detail_value), name="WelcomePadItemDescription", checked=not self.enabled)
        return stack

    @property
    def description(self):
        return ""


class ResumeWorkFileItem(Item):
    """Item of the model"""

    def __init__(self, on_mouse_pressed_callback: Callable):
        super().__init__()
        self._on_mouse_pressed_callback = on_mouse_pressed_callback
        self.enabled = False
        self.__is_hovered = False

    def get_image(self) -> str:
        return _get_icons("new_workfile")

    def on_mouse_pressed(self):
        return

    def on_mouse_released(self):
        if self.enabled and self.__is_hovered:
            self._on_mouse_pressed_callback()

    def on_hovered(self, hovered):
        """Action that will be called when the item is hovered on"""
        self.__is_hovered = hovered

    def on_description_scrolled_x(self, x):
        """Action that will be called when the description is scrolled on x"""
        return

    def on_description_scrolled_y(self, y):
        """Action that will be called when the description is scrolled on y"""
        return

    @property
    def title(self):
        return "Resume WorkFile"

    @property
    def description(self):
        return "Continue to work on your current opened workfile..."
