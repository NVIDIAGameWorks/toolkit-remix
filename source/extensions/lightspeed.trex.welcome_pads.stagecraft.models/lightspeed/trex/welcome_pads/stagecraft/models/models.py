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
from typing import Callable, Dict

import omni.client
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
        return "Setup Project"

    @property
    def description(self):
        return (
            "Launch the project wizard to:\n"
            "- Open an existing project\n"
            "- Create a new mod\n"
            "- Edit existing mods\n"
            "- Remaster existing mods"
        )


class RecentWorkFileItem(Item):
    """Item of the model"""

    def __init__(
        self, title: str, description: Dict[str, str], image_fn: Callable, on_mouse_pressed_callback: Callable, path
    ):
        self.__title = title
        self.__path = path
        self.__description = description
        self.__image_fn = image_fn
        super().__init__()
        self.__is_hovered = False
        self.__is_scrolled = False
        self.use_description_override_delegate = True
        self._on_mouse_pressed_callback = on_mouse_pressed_callback
        self.__init_enabled()

    def __init_enabled(self):
        result, entry = omni.client.stat(self.__path)
        self.enabled = result == omni.client.Result.OK and entry.flags & omni.client.ItemFlags.READABLE_FILE

    def get_image(self) -> str:
        return self.__image_fn()

    def on_mouse_pressed(self):
        return

    def on_mouse_released(self):
        if not self.enabled:
            return
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
            ui.Spacer(height=ui.Pixel(8))
            if not self.enabled:
                with ui.HStack(height=ui.Pixel(20)):
                    ui.Label(
                        "Status:",
                        width=ui.Pixel(80),
                        alignment=ui.Alignment.RIGHT,
                        style_type_name_override="FieldError",
                        height=0,
                    )
                    ui.Spacer(width=ui.Pixel(8), height=0)
                    ui.Label(
                        "Invalid file. Deleted?", enabled=self.enabled, style_type_name_override="FieldError", height=0
                    )
            for detail_key, detail_value in self.__description.items():
                with ui.HStack(height=ui.Pixel(20)):
                    ui.Label(
                        f"{detail_key}:",
                        name="WelcomePadItemDescription",
                        checked=not self.enabled,
                        width=ui.Pixel(80),
                        alignment=ui.Alignment.RIGHT,
                        height=0,
                    )
                    ui.Spacer(width=ui.Pixel(8), height=0)
                    ui.Label(str(detail_value), name="WelcomePadItemDescription", checked=not self.enabled, height=0)
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
        return "Resume Current Project"

    @property
    def description(self):
        return "Continue working on your currently opened project."


class LaunchRemixGameItem(Item):
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
        return "Launch Game with Remix"

    @property
    def description(self):
        return "Launch a game using the RTX Remix game launcher."
