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

from asyncio import ensure_future
from functools import partial
from weakref import WeakSet

import carb.input
import omni
import omni.appwindow
import omni.ui as ui
import pyperclip
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .style import style as _style


class InfoIconWidget:
    __DEFAULT_UI_ICON_SIZE_PIXEL = 16

    def __init__(
        self,
        message: str,
        icon_size: int = __DEFAULT_UI_ICON_SIZE_PIXEL,
        max_width: int | None = None,
    ):
        """
        Create an info icon widget

        Args:
            message: what to show in a tooltip when hovering the i icon
            icon_size: size of the info icon in pixels
            max_width: optional max width for the tooltip (enables word wrap)

        Returns:
            The info icon object
        """

        self._default_attr = {
            "_message": None,
            "_icon_size": None,
            "_max_width": None,
            "_info_image": None,
            "_tooltip": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._message = message
        self._icon_size = icon_size
        self._max_width = max_width
        self.__create_ui()

    def __create_ui(self):
        self._info_image = ui.Image(
            name="PropertiesPaneSectionInfo",
            width=ui.Pixel(self._icon_size),
            height=ui.Pixel(self._icon_size),
            tooltip="",
            identifier="info_icon_image_id",
        )
        self._tooltip = TooltipWidget(self._info_image, self._message, max_width=self._max_width)

    def destroy(self):
        _reset_default_attrs(self)


class TooltipWidget:
    """Add a nice tooltip to any widget"""

    def __init__(self, widget: ui.Widget, message: str, max_width: int | None = None):
        self._default_attr = {
            "_message": None,
            "_max_width": None,
            "_tooltip_window": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._widget = widget
        self._message = message
        self._max_width = max_width

        self._tooltip_window = None

        self.__exit_task = False
        self.__info_hovered_task = None
        self.__create_ui()

    def __create_ui(self):
        self._widget.set_mouse_hovered_fn(partial(self.__on_info_hovered, self._widget, self._message))

    def __on_info_hovered(self, icon_widget, tooltip, hovered):
        self._tooltip_window = None
        if hovered:
            if self.__info_hovered_task:
                self.__info_hovered_task.cancel()
            self.__exit_task = False
            self.__info_hovered_task = ensure_future(self.__deferred_on_info_hovered(icon_widget, tooltip))
        else:
            self.__exit_task = True
            if self.__info_hovered_task:
                self.__info_hovered_task.cancel()

    @omni.usd.handle_exception
    async def __deferred_on_info_hovered(self, icon_widget, tooltip):
        if self.__exit_task:
            return
        flags = ui.WINDOW_FLAGS_POPUP
        flags |= ui.WINDOW_FLAGS_NO_TITLE_BAR
        flags |= ui.WINDOW_FLAGS_NO_DOCKING
        flags |= ui.WINDOW_FLAGS_NO_BACKGROUND
        flags |= ui.WINDOW_FLAGS_NO_RESIZE
        flags |= ui.WINDOW_FLAGS_NO_COLLAPSE
        flags |= ui.WINDOW_FLAGS_NO_CLOSE
        flags |= ui.WINDOW_FLAGS_NO_SCROLLBAR

        # Use max_width if specified, otherwise default to 600
        initial_width = self._max_width if self._max_width else 600

        self._tooltip_window = ui.Window(
            "Context Info",
            width=initial_width,
            height=100,
            visible=True,
            flags=flags,
            position_x=icon_widget.screen_position_x + icon_widget.computed_width,
            position_y=icon_widget.screen_position_y,
            padding_x=0,
            padding_y=0,
        )
        with self._tooltip_window.frame:
            with ui.ZStack():
                ui.Rectangle(name="PropertiesPaneSectionWindowBackground")
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(8))
                    with ui.VStack():
                        ui.Spacer(height=ui.Pixel(8))
                        # Enable word_wrap if max_width is set to constrain text
                        if self._max_width:
                            label = ui.Label(
                                tooltip,
                                height=0,
                                word_wrap=True,
                                identifier="context_tooltip",
                            )
                        else:
                            label = ui.Label(tooltip, height=0, width=0, identifier="context_tooltip")
                        ui.Spacer(height=ui.Pixel(8))
                    ui.Spacer(width=ui.Pixel(8))

        await omni.kit.app.get_app().next_update_async()

        # With max_width, keep the window at that width; otherwise size to content
        if self._max_width:
            self._tooltip_window.width = self._max_width
        else:
            self._tooltip_window.width = label.computed_width + 24
        self._tooltip_window.height = label.computed_height + 24

        app_window = omni.appwindow.get_default_app_window()
        size = app_window.get_size()
        dpi_scale = ui.Workspace.get_dpi_scale()

        # Override the right side of the screen, shift to the left
        if self._tooltip_window.width > size[0] / dpi_scale - self._tooltip_window.position_x - 8:
            self._tooltip_window.position_x = size[0] / dpi_scale - self._tooltip_window.width - 8
            # Override bottom of the screen, shift above icon
            if self._tooltip_window.height > size[1] / dpi_scale - self._tooltip_window.position_y - 8:
                self._tooltip_window.position_y = self._tooltip_window.position_y - 72
            # Otherwise shift under the icon
            else:
                self._tooltip_window.position_y = self._tooltip_window.position_y + 16

    def destroy(self):
        if self.__info_hovered_task:
            self.__info_hovered_task.cancel()
        _reset_default_attrs(self)
        self.__info_hovered_task = None


_ALL_SELECTABLE_TOOL_TIP_WINDOWS = WeakSet()


class SelectableToolTipWidget:
    _WINDOW_NAME = "Last message"
    _MIN_WINDOW_WIDTH = 800
    _MIN_WINDOW_HEIGHT = 200

    def __init__(self, widget: ui.Widget, message: str, follow_mouse_pointer: bool = False):
        """
        Show a popup window over an widget with a text that the user can copy

        Args:
            widget: the widget to use to show the popup window over it
            message: the message to show
            follow_mouse_pointer: the popup window will follow the mouse or not
        """
        self._default_attrs = {
            "_window": None,
            "_label": None,
        }
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)

        self._window = None
        self.__widget = widget
        self.__message = message
        self.__follow_mouse_pointer = follow_mouse_pointer
        self.__hovered = False

        if follow_mouse_pointer:
            self._carb_input = carb.input.acquire_input_interface()
            # doesnt work
            # self._mouse_sub = self._carb_input.subscribe_to_mouse_events(self._mouse, self._on_mouse_input)
            self._mouse = omni.appwindow.get_default_app_window().get_mouse()
            self._input_sub_id = self._carb_input.subscribe_to_input_events(
                self._on_input_event,
                carb.input.MouseEventType.MOVE,
                self._mouse,
                order=0,
            )

        self._default_style = _style
        self.__create_ui()

    def _on_input_event(self, event):
        if event.event.type == carb.input.MouseEventType.MOVE and self.__hovered and self._window:
            x, y = event.event.pixel_coords
            dpi_scale = ui.Workspace.get_dpi_scale()
            self._window.position_x = x / dpi_scale + 1  # + 1 to not have flickering
            self._window.position_y = y / dpi_scale + 1  # + 1 to not have flickering
            self.__fix_window_bigger_than_app()
        return True

    def __create_ui(self):
        self.__widget.set_mouse_hovered_fn(self._on_message_hovered)

    def set_message(self, message: str):
        self.__message = message

    def _get_current_mouse_coords(self):
        app_window = omni.appwindow.get_default_app_window()
        input_interface = carb.input.acquire_input_interface()
        dpi_scale = ui.Workspace.get_dpi_scale()
        pos_x, pos_y = input_interface.get_mouse_coords_pixel(app_window.get_mouse())
        return pos_x / dpi_scale, pos_y / dpi_scale

    def _on_message_hovered(self, hovered: bool):
        """
        When the field of a message is hovered, we show a bigger window to see the full message

        Args:
            hovered: hovered or not
        """
        self.__hovered = hovered
        if not hovered:
            return
        self.__create_window()
        self.__set_window_position()
        self.__fix_window_bigger_than_app()

        for window in _ALL_SELECTABLE_TOOL_TIP_WINDOWS:
            if window != self._window:
                window.visible = False

    def __set_window_position(self):
        mouse_coord = self._get_current_mouse_coords()
        self._window.position_x = mouse_coord[0] + 1  # + 1 to not have flickering
        self._window.position_y = mouse_coord[1] + 1  # + 1 to not have flickering

    def __create_window(self):
        flags = ui.WINDOW_FLAGS_NO_COLLAPSE
        flags |= ui.WINDOW_FLAGS_NO_CLOSE
        flags |= ui.WINDOW_FLAGS_NO_MOVE
        flags |= ui.WINDOW_FLAGS_NO_RESIZE
        flags |= ui.WINDOW_FLAGS_NO_SCROLLBAR
        flags |= ui.WINDOW_FLAGS_NO_DOCKING
        flags |= ui.WINDOW_FLAGS_NO_BACKGROUND
        flags |= ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE
        flags |= ui.WINDOW_FLAGS_NO_TITLE_BAR
        # flags |= ui.WINDOW_FLAGS_POPUP  # bug with tree selection

        mouse_coord = self._get_current_mouse_coords()
        app_window = omni.appwindow.get_default_app_window()
        size = app_window.get_size()
        dpi_scale = ui.Workspace.get_dpi_scale()
        window_height = size[1] / dpi_scale - mouse_coord[1]
        window_height = min(window_height, self._MIN_WINDOW_HEIGHT)
        window_width = size[0] / dpi_scale - mouse_coord[0]
        window_width = min(window_width, self._MIN_WINDOW_WIDTH)

        if self._window is None:
            self._window = ui.Window(
                f"{self._WINDOW_NAME}_{id(self.__widget)}",
                width=window_width,
                height=window_height,
                visible=True,
                flags=flags,
            )
            self._window.set_focused_changed_fn(self._on_focused_changed_fn)
            _ALL_SELECTABLE_TOOL_TIP_WINDOWS.add(self._window)
            if "Image::Copy" not in ui.Style.get_instance().default:
                self._window.frame.set_style(self._default_style)
            with self._window.frame:
                with ui.ZStack(mouse_hovered_fn=self.__on_message_hovered):
                    ui.Rectangle(name="PropertiesPaneSectionWindowBackground")
                    with ui.ScrollingFrame(
                        name="TreePanelBackground",
                        vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        scroll_y_max=0,
                    ):
                        with ui.VStack():
                            for _ in range(5):
                                with ui.HStack():
                                    for _ in range(4):
                                        ui.Image(
                                            "",
                                            name="TreePanelLinesBackground",
                                            fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                            height=ui.Pixel(256),
                                            width=ui.Pixel(256),
                                        )
                    with ui.Frame(separate_window=True):  # to keep the Z depth order
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(12))  # offset scrollbar
                            with ui.HStack():
                                ui.Spacer(width=ui.Pixel(12))  # offset scrollbar
                                with ui.ZStack(content_clipping=True):
                                    with ui.ScrollingFrame(
                                        name="PropertiesPaneSection",
                                    ):
                                        with ui.ZStack(content_clipping=True):
                                            ui.Rectangle(name="SelectableToolTipBackground")
                                            with ui.VStack():
                                                ui.Spacer(height=ui.Pixel(8))
                                                with ui.HStack():
                                                    ui.Spacer(width=ui.Pixel(8))
                                                    self._label = ui.Label(
                                                        self.__message or "No message",
                                                        word_wrap=True,
                                                        alignment=ui.Alignment.LEFT_TOP,
                                                        name="SelectableToolTip",
                                                    )
                                                    ui.Spacer(width=ui.Pixel(8))
                                                ui.Spacer(height=ui.Pixel(8))

                                    with ui.Frame(separate_window=True):  # to keep the Z depth order
                                        with ui.HStack():
                                            ui.Spacer()
                                            with ui.HStack(
                                                content_clipping=True,
                                                width=ui.Pixel(24),
                                                height=ui.Pixel(24),
                                            ):
                                                ui.Image(
                                                    "",
                                                    name="Copy",
                                                    tooltip="Copy text",
                                                    mouse_pressed_fn=lambda x, y, b, m: self.__copy_to_clipboard(b),
                                                )
                                            ui.Spacer(width=ui.Pixel(12 + 12))  # + 12 because of scrollbar
        else:
            self._window.width = window_width
            self._window.height = window_height
            self._label.text = self.__message
            self._window.visible = True

    def __fix_window_bigger_than_app(self):
        app_window = omni.appwindow.get_default_app_window()
        size = app_window.get_size()
        dpi_scale = ui.Workspace.get_dpi_scale()
        if self._window.width <= self._MIN_WINDOW_WIDTH:
            self._window.width = ui.Pixel(self._MIN_WINDOW_WIDTH)
        if self._window.width > size[0] / dpi_scale - self._window.position_x - 8:
            self._window.width = ui.Pixel(size[0] / dpi_scale - self._window.position_x - 8)

        if self._window.height <= self._MIN_WINDOW_HEIGHT:
            self._window.height = ui.Pixel(self._MIN_WINDOW_HEIGHT)
        if self._window.height > size[1] / dpi_scale - self._window.position_y - 8:
            self._window.height = ui.Pixel(size[1] / dpi_scale - self._window.position_y - 8)

    def __copy_to_clipboard(self, button):
        if button != 0:
            return
        pyperclip.copy(self.__message)

    def __on_message_hovered(self, hovered):
        self._window.visible = hovered

    def _on_focused_changed_fn(self, focused):
        self._window.visible = focused

    def destroy(self):
        if self.__follow_mouse_pointer:
            self._carb_input.unsubscribe_to_input_events(self._input_sub_id)
        _reset_default_attrs(self)
