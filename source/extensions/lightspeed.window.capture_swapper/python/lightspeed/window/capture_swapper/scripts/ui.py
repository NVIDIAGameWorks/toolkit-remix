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
from typing import Optional

import carb
import omni.appwindow
import omni.kit.menu.utils
import omni.kit.widget.layers as layers
import omni.ui as ui
from lightspeed.widget.content_viewer.scripts.core import ContentData
from lightspeed.widget.game_captures.scripts.core import GameCapturesCore
from lightspeed.widget.game_captures.scripts.ui import GameCapturesViewer

from .core import CaptureSwapperCore


class CaptureSwapperWindow:

    WINDOW_NAME = "Lightspeed Capture Swapper"

    def __init__(self, extension_path):
        """Window to list all entities"""
        self._extension_path = extension_path
        self._style = {
            "Button::new": {"background_color": 0xFF23211F, "border_color": 0xFF606060, "border_width": 1},
            "Button::new:hovered": {"background_color": 0xFF664B0C, "border_color": 0xFFBF8C15, "border_width": 1},
            "Rectangle::main_frame": {"background_color": 0xFF23211F},
        }
        self.__default_attr = {
            "_core": None,
            "_window": None,
            "_subcription_app_window_size_changed": None,
            "_frame_new_game_workspace": None,
            "_game_capture_core": None,
            "_game_capture_viewer": None,
            "_menu_subscription": None,
        }
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self.__layer_to_swap = None
        self._core = CaptureSwapperCore()

        self._game_capture_core = GameCapturesCore()
        self._game_capture_viewer = GameCapturesViewer(self._game_capture_core, self._extension_path)

        self.__create_ui()
        self.__add_layer_menu()

    def __add_layer_menu(self):
        self._menu_subscription = layers.ContextMenu.add_menu(
            [
                {"name": ""},
                {
                    "name": "Swap capture layer...",
                    "glyph": "menu_refresh.svg",
                    "show_fn": [
                        layers.ContextMenu.is_layer_item,
                        layers.ContextMenu.is_not_missing_layer,
                        layers.ContextMenu.is_layer_and_parent_unmuted,
                        self._core.is_capture_layer,
                    ],
                    "onclick_fn": self.show_for_game_capture_folder,
                },
            ]
        )

    def _get_icon(self, name) -> Optional[str]:
        """Get icon path"""
        icon_path = Path(self._extension_path).joinpath("icons", f"{name}.svg")
        if icon_path.exists():
            return str(icon_path)
        return None

    def center_window(self):
        window_width = ui.Workspace.get_main_window_width()
        window_height = ui.Workspace.get_main_window_height()
        width, height = self._generate_window_size()
        self._window.width = width
        self._window.height = height
        self._window.position_x = window_width / 2 - self._window.width / 2
        self._window.position_y = window_height / 2 - self._window.height / 2

    def show_frame_new_game_workspace(self, value):
        self._frame_new_game_workspace.visible = value

    def __create_ui_new_game_workspace(self):
        self._frame_new_game_workspace = ui.Frame()
        border_percent = 5
        with self._frame_new_game_workspace:
            with ui.ZStack():
                ui.Rectangle(name="main_frame")
                with ui.VStack():
                    ui.Spacer(height=ui.Percent(border_percent))
                    with ui.HStack():
                        ui.Spacer(width=ui.Percent(border_percent))
                        with ui.VStack(spacing=16):
                            ui.Label("Game Workspace(s)", height=0)
                            self._game_capture_viewer.create_ui()
                            with ui.HStack(height=20):
                                ui.Spacer()
                                ui.Button(
                                    "Swap current with the selected",
                                    name="new",
                                    width=ui.Percent(30),
                                    clicked_fn=self._on_swap_current_with_selected,
                                )
                                ui.Button("Cancel", name="new", width=ui.Percent(20), clicked_fn=self.close)
                        ui.Spacer(width=ui.Percent(border_percent))
                    ui.Spacer(height=ui.Percent(border_percent))

    def _generate_window_size(self):
        window_width = ui.Workspace.get_main_window_width()
        window_height = ui.Workspace.get_main_window_height()
        percent = 55
        if window_width < window_height:
            height = window_height / 100 * percent
            width = height * 1.3
        else:
            width = window_width / 100 * percent
            height = width / 1.3
        return width, height

    def __create_ui(self):
        """Create the main UI"""
        width, height = self._generate_window_size()

        flags = ui.WINDOW_FLAGS_NO_RESIZE
        flags |= ui.WINDOW_FLAGS_NO_SCROLLBAR
        # flags |= ui.WINDOW_FLAGS_MODAL  # can't be modal, bug with file picker over it
        flags |= ui.WINDOW_FLAGS_NO_DOCKING
        flags |= ui.WINDOW_FLAGS_NO_TITLE_BAR
        self._window = ui.Window(
            self.WINDOW_NAME, name=self.WINDOW_NAME, width=width, height=height, flags=flags, style=self._style
        )
        self._window.set_visibility_changed_fn(self._on_visibility_changed)
        self.center_window()

        with self._window.frame:
            with ui.VStack(style=self._style):
                self.__create_ui_new_game_workspace()

        appwindow_stream = omni.appwindow.get_default_app_window().get_window_resize_event_stream()
        self._subcription_app_window_size_changed = appwindow_stream.create_subscription_to_pop(
            self._on_app_window_size_changed, name="On app window resized", order=0
        )

        self.close()

    def _on_app_window_size_changed(self, event: carb.events.IEvent):
        self.center_window()

    def _on_swap_current_with_selected(self):
        current_capture = self._game_capture_core.get_current_capture()
        if not current_capture:
            carb.log_warn('Please select a "capture"')
            return
        self._core.swap_current_capture_layer_with(self.__layer_to_swap, current_capture)
        self.__layer_to_swap = None
        self.close()

    def close(self):
        self._window.visible = False

    def show_for_game_capture_folder(self, objects):
        """Find the current game using the current replacement layer"""
        game_name, capture_folder = self._core.game_current_game_capture_folder()
        if game_name:
            current_game_capture_folder = ContentData(title=game_name, path=capture_folder)
            self._game_capture_core.set_current_game_capture_folder(current_game_capture_folder)
            self._game_capture_core.refresh_content()

            item = objects["item"]
            self.__layer_to_swap = item().layer
            self.show()
        else:
            self.__layer_to_swap = None

    def show(self):
        self._window.visible = True

    def _on_visibility_changed(self, visible):
        """Change the menu"""
        self.center_window()
        omni.kit.menu.utils.rebuild_menus()

    def _toggle_window(self):
        if self._window:
            self._window.visible = not self._window.visible

    def destroy(self):
        for attr, value in self.__default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()  # noqa PLE1102
                del m_attr
                setattr(self, attr, value)
