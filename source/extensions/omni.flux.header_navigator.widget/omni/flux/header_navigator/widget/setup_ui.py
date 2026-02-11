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

import asyncio
from typing import Any
from collections.abc import Callable

import carb
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.label import create_label_with_font as _create_label_with_font

_INSTANCES = {}


class _SetupUI:
    """Header navigator UI"""

    def __init__(self, name):
        self._default_attr = {
            "_buttons": None,
            "_buttons_ui": None,
            "_main_frame": None,
            "_refresh_task": None,
            "_select_button_task": None,
            "_image_provider_title": None,
            "_logo_title_frame": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._header_title = name
        self._refresh_task = None
        self._select_button_task = None
        self._buttons = {}
        self._buttons_ui = {}
        self.__on_button_registered = _Event()
        self.__on_header_refreshed = _Event()

    def _button_registered(self, button: dict[str, tuple[ui.Widget, int]]):
        """Call the event object that has the list of functions"""
        self.__on_button_registered(button)

    def subscribe_button_registered(self, function: Callable[[str], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_button_registered, function)

    def _header_refreshed(self):
        """Call the event object that has the list of functions"""
        self.__on_header_refreshed()

    def subscribe_header_refreshed(self, function: Callable[[], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_header_refreshed, function)

    def register_button(self, button: dict[str, tuple[Callable[[], ui.Widget], int]]):
        """
        Register a new button

        Args:
            button: the button data: {name: (callback that create the ui, priority from left (low number) to right
                (high number))}
        """
        self._buttons.update(button)
        self.refresh()
        self._button_registered(button)

    def unregister_button(self, button: str):
        """
        Unregister a button

        Args:
            button: the button name to unregister
        """
        if button not in self._buttons or button not in self._buttons_ui:
            return
        self._buttons_ui.pop(button)
        self._buttons.pop(button)
        self.refresh()

    def get_registered_buttons(self) -> dict[str, tuple[Callable[[], ui.Widget]]]:
        """Get the list of registered buttons"""
        return self._buttons

    def select_button(self, button: str, value: bool = True):
        """
        Select a given button name

        Args:
            button: the button name
            value: select or not
        """
        if self._select_button_task:
            self._select_button_task.cancel()
        self._select_button_task = asyncio.ensure_future(self._deferred_select_button(button, value=value))

    @omni.usd.handle_exception
    async def _deferred_select_button(self, button: str, value: bool = True):
        if self._refresh_task:  # wait if there is a refresh going on
            while not self._refresh_task.done():
                await asyncio.sleep(0.001)
        if button not in self._buttons_ui:
            return
        for other_button in self._buttons_ui.values():
            other_button.selected = False
        self._buttons_ui[button].selected = value

    def create_ui(self):
        """Create the UI"""
        self._main_frame = ui.Frame(height=ui.Pixel(48))
        return self._main_frame

    def refresh(self):
        """Refresh the UI"""
        if self._refresh_task:
            self._refresh_task.cancel()
        self._refresh_task = asyncio.ensure_future(self._deferred_refresh())

    def show_logo_and_title(self, value):
        """
        Show or hide the logo

        Args:
            value: show or hide
        """
        if self._logo_title_frame:
            self._logo_title_frame.visible = value

    @omni.usd.handle_exception
    async def _deferred_refresh(self):
        if self._main_frame is None:
            return
        with self._main_frame:
            with ui.HStack():
                self._logo_title_frame = ui.Frame()
                with self._logo_title_frame:
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(16))
                        with ui.VStack(width=ui.Pixel(224)):
                            ui.Spacer(height=ui.Pixel(12))
                            with ui.HStack():
                                ui.Spacer()
                                image = ui.Image("", name="HeaderNavigatorLogo")
                                ui.Spacer(width=ui.Pixel(16))
                            ui.Spacer(height=ui.Pixel(12))
                        # line separator
                        with ui.VStack(width=ui.Pixel(1)):
                            ui.Spacer(height=ui.Pixel(8))
                            rect1 = ui.Rectangle(width=0, height=0)
                            ui.Spacer()
                            rect2 = ui.Rectangle(width=0, height=0)
                            ui.Spacer(height=ui.Pixel(8))
                        ui.FreeBezierCurve(
                            rect1,
                            rect2,
                            start_tangent_width=ui.Percent(1),
                            end_tangent_width=ui.Percent(1),
                            name="HeaderNvidiaLine",
                        )

                        ui.Spacer(width=ui.Pixel(16))

                        with ui.VStack(width=0):
                            ui.Spacer(height=ui.Pixel(12))

                            style = ui.Style.get_instance()
                            current_dict = style.default
                            if "ImageWithProvider::HeaderNavigatorTitle" not in current_dict:
                                # use regular labels
                                ui.Label(self._header_title)
                            else:
                                # use custom styled font
                                self._image_provider_title, _, _ = _create_label_with_font(
                                    self._header_title,
                                    "HeaderNavigatorTitle",
                                    remove_offset=False,
                                    quality_multiplier=1,
                                )
                            ui.Spacer(height=ui.Pixel(12))

                ui.Spacer()
                with ui.HStack(width=0):
                    for name, (ui_item, _) in sorted(self._buttons.items(), key=lambda x: x[1][1]):
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(12))
                            self._buttons_ui[name] = ui_item()
                            ui.Spacer(height=ui.Pixel(12))
                        ui.Spacer(width=ui.Pixel(32))
                # account icon
                with ui.VStack(width=ui.Pixel(24)):
                    ui.Spacer(height=ui.Pixel(12))
                    image = ui.Image("", name="Account")
                    image.set_mouse_pressed_fn(
                        lambda x, y, button, modifier, img=image: self.__on_account_clicked(button, img)
                    )
                    ui.Spacer(height=ui.Pixel(12))

                ui.Spacer(width=ui.Pixel(16))
        self._header_refreshed()

    def __on_account_clicked(self, button, img):
        if button != 0:
            return
        img.selected = not img.selected

    def destroy(self):
        _reset_default_attrs(self)


def create_instance(name: str) -> _SetupUI:
    """
    Create a header navigator instance

    Args:
        name: the name of the navigator

    Returns:
        The instance
    """
    if name in _INSTANCES:
        carb.log_warn(f"Instance of the header navigator with the name {name} already exist")
        return _INSTANCES[name]
    instance = _SetupUI(name)
    _INSTANCES[name] = instance
    return instance


def get_instances() -> dict[str, _SetupUI]:
    """Get the created instances"""
    return _INSTANCES
