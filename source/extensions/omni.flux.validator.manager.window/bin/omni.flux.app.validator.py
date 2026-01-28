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

import carb
import omni.appwindow
import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.flux.validator.manager.window import ValidatorManagerWindow as _ValidatorManagerWindow
from omni.flux.validator.manager.window import get_window_instance as _get_window_instance
from omni.kit.mainwindow import get_main_window


class StandaloneWindow:
    def __init__(self):
        self._flags = ui.WINDOW_FLAGS_NO_COLLAPSE
        self._flags |= ui.WINDOW_FLAGS_NO_CLOSE
        self._flags |= ui.WINDOW_FLAGS_NO_MOVE
        self._flags |= ui.WINDOW_FLAGS_NO_RESIZE
        self._flags |= ui.WINDOW_FLAGS_NO_SCROLLBAR
        self._flags |= ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE
        self._flags |= ui.WINDOW_FLAGS_NO_TITLE_BAR

        asyncio.ensure_future(self._deferred_hide_menu())
        asyncio.ensure_future(self._dock())

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

        # Wait for the validator window
        frame = 0
        while True:
            await omni.kit.app.get_app().next_update_async()
            validation_window = _get_window_instance()
            if validation_window is not None:
                break
            frame += 1
            if frame == 100:
                raise TimeoutError(f"Can't set the workspace, missing {_ValidatorManagerWindow.WINDOW_NAME} window")

        # Setup the docking Space:
        validation_window.dock_in(main_dockspace, ui.DockPosition.SAME)
        await omni.kit.app.get_app().next_update_async()
        validation_window.flags = self._flags
        await omni.kit.app.get_app().next_update_async()
        validation_window.dock_tab_bar_visible = False
        validation_window.dock_tab_bar_enabled = False

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


def main():
    StandaloneWindow()


if __name__ == "__main__":
    main()
