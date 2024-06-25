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
import math

import carb
import omni.appwindow
import omni.kit.app
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import WINDOW_NAME
from omni.kit.mainwindow import get_main_window

_HIDE_MENU = "/exts/lightspeed.trex.app.setup/hide_menu"
_APP_WINDOW_SETTING = "/app/window/enabled"  # setting affected by "--no-window" arg


class SetupUI:

    _WINDOW_NAME = WINDOW_NAME

    def __init__(self):
        """Setup the main Lightspeed Trex window"""
        self._window = None
        self._flags = ui.WINDOW_FLAGS_NO_COLLAPSE
        self._flags |= ui.WINDOW_FLAGS_NO_CLOSE
        self._flags |= ui.WINDOW_FLAGS_NO_MOVE
        self._flags |= ui.WINDOW_FLAGS_NO_RESIZE
        self._flags |= ui.WINDOW_FLAGS_NO_SCROLLBAR
        self._flags |= ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE
        self._flags |= ui.WINDOW_FLAGS_NO_TITLE_BAR

        self.__settings = carb.settings.get_settings()

        if self.__settings.get(_HIDE_MENU):
            # hide the menu
            self._hide_menu()

        self._create_ui()
        appwindow_stream = omni.appwindow.get_default_app_window().get_window_resize_event_stream()
        self._subcription_app_window_size_changed = appwindow_stream.create_subscription_to_pop(
            self._on_app_window_size_changed, name="On app window resized", order=0
        )

    def _hide_menu(self):
        # old menu
        asyncio.ensure_future(self._deferred_hide_menu())

    @omni.usd.handle_exception
    async def _deferred_hide_menu(self):
        timeout = 60
        i = 0
        imported = False
        while i < timeout:
            try:
                import omni.kit.ui  # noqa PLC0415, PLW0621

                imported = True
                break
            except ImportError:
                await omni.kit.app.get_app().next_update_async()  # noqa PLE0601
                i += 1
        if not imported:
            carb.log_error("Can't import omni.kit.ui to hide menus")
            return
        editor_menu = omni.kit.ui.get_editor_menu()
        active_menus = editor_menu.active_menus.copy().keys()
        for menu in active_menus:
            editor_menu.remove_item(menu)
        main_menu_bar = get_main_window().get_main_menu_bar()
        main_menu_bar.visible = False

    def _on_app_window_size_changed(self, event: carb.events.IEvent):
        asyncio.ensure_future(self._deferred_on_app_window_size_changed())

    @omni.usd.handle_exception
    async def _deferred_on_app_window_size_changed(self):
        """Tricks: re-dock to have the main window updating his size"""
        self._window.flags = self._flags
        main_dockspace = ui.Workspace.get_window("DockSpace")
        self._window.dock_in(main_dockspace, ui.DockPosition.SAME)
        await omni.kit.app.get_app().next_update_async()
        self._resize_app_window_to_multiple_two()
        await self.setup_render_settings_window()

    def _resize_app_window_to_multiple_two(self):
        # we don't want to have the size of the window to not be a multiple of 2.
        app_window = omni.appwindow.get_default_app_window()
        size = app_window.get_size()
        size = (2 * math.ceil(size[0] / 2), 2 * math.ceil(size[1] / 2))
        app_window.resize(*size)

    @omni.usd.handle_exception
    async def _dock(self) -> None:
        """Dock the main Flux window into the DockSpace."""
        # Wait for the DockSpace
        frame = 0
        while True:
            await omni.kit.app.get_app().next_update_async()
            main_dockspace = ui.Workspace.get_window("DockSpace")
            if main_dockspace is not None:
                break
            frame += 1
            if frame == 100:
                raise TimeoutError("Can't set the workspace, missing DockSpace window")

        # Setup the docking Space:
        self._window.dock_in(main_dockspace, ui.DockPosition.SAME)
        await omni.kit.app.get_app().next_update_async()
        await self.setup_render_settings_window(hide=True)
        self._window.flags = self._flags
        await omni.kit.app.get_app().next_update_async()
        self._window.dock_tab_bar_visible = False
        self._window.dock_tab_bar_enabled = False

    @omni.usd.handle_exception
    async def setup_render_settings_window(self, hide=False):
        """Temp solution TODO: OM-72923"""
        # skip temp fix if app is launched with "--no-window" and there are no windows to find
        if not carb.settings.get_settings().get(_APP_WINDOW_SETTING):
            return
        # Wait for the render settings windows
        frame = 0
        while True:
            await omni.kit.app.get_app().next_update_async()
            render_settings = ui.Workspace.get_window("Render Settings")
            if render_settings is not None:
                break
            frame += 1
            if frame == 100:
                raise TimeoutError("Can't set the workspace, missing Render Settings window")

        render_settings.height = self._window.height * 0.70
        render_settings.width = 400
        render_settings.position_x = self._window.width - render_settings.width
        render_settings.position_y = 150
        if hide:
            render_settings.visible = False

    def get_window(self):
        return self._window

    def _create_ui(self):
        self._window = ui.Window(self._WINDOW_NAME, name=self._WINDOW_NAME, visible=True, style=ui.Style.get_instance())
        asyncio.ensure_future(self._dock())

    def destroy(self):
        self._subcription_app_window_size_changed = None
        self._window = None
