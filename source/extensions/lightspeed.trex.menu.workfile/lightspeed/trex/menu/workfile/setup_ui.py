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

import carb.tokens
import omni.kit.window.about
import omni.kit.window.preferences
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.path_utils import open_file_using_os_default
from omni.kit.widget.prompt import PromptButtonInfo, PromptManager

from .delegate import Delegate as _Delegate


@omni.usd.handle_exception
async def async_focus_window(window_name: str):
    """
    Focus the provided window name.
    """
    window = ui.Workspace.get_window(window_name)
    if window is None:
        raise ValueError(f"Could not find window named {window_name:!r}")
    window.focus()


def error_prompt(message: str) -> None:
    """
    Show a simple prompt to notify the user of an error.
    """
    PromptManager.post_simple_prompt(
        title="An Error Occurred",
        message=message,
        ok_button_info=PromptButtonInfo("Okay", None),
        cancel_button_info=None,
        modal=True,
        no_title_bar=True,
    )


class SetupUI:
    def __init__(self):
        super().__init__()
        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._delegate = _Delegate()
        self._reload_stage_menu_item = None
        self.__on_show_menu = _Event()
        self.__on_save = _Event()
        self.__on_save_as = _Event()
        self.__on_new_workfile = _Event()
        self.__on_reload_last_workfile = _Event()
        self.__undo = _Event()
        self.__redo = _Event()
        self.__create_ui()

    def subscribe_show_menu(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_show_menu, function)

    def _save(self):
        """Call the event object that has the list of functions"""
        self.__on_save()

    def subscribe_save(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_save, function)

    def _save_as(self):
        """Call the event object that has the list of functions"""
        self.__on_save_as()

    def subscribe_save_as(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_save_as, function)

    def _create_new_workfile(self):
        self.__on_new_workfile()

    def subscribe_create_new_workfile(self, function):
        return _EventSubscription(self.__on_new_workfile, function)

    def _reload_last_workfile(self):
        self.__on_reload_last_workfile()

    def subscribe_reload_last_workfile(self, function):
        return _EventSubscription(self.__on_reload_last_workfile, function)

    def _undo(self):
        """Call the event object that has the list of functions"""
        self.__undo()

    def subscribe_undo(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__undo, function)

    def _redo(self):
        """Call the event object that has the list of functions"""
        self.__redo()

    def subscribe_redo(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__redo, function)

    @staticmethod
    def _show_preferences_window() -> None:
        inst = omni.kit.window.preferences.get_instance()
        if not inst:
            error_prompt("Preferences extension is not loaded yet")
            return

        inst.show_preferences_window()
        # Force the tab to be the active/focused tab (this currently needs to be done in async)
        asyncio.ensure_future(async_focus_window("Preferences"))

    @staticmethod
    def _show_about_window() -> None:
        inst = omni.kit.window.about.get_instance()
        if not inst:
            error_prompt("About extension is not loaded yet")
            return

        inst.show(True)
        # Force the tab to be the active/focused tab (this currently needs to be done in async)
        asyncio.ensure_future(async_focus_window("About"))

    @staticmethod
    def _open_logs_dir() -> None:
        log_folder = carb.tokens.get_tokens_interface().resolve("${logs}")
        open_file_using_os_default(log_folder)

    def __create_ui(self):
        def create_separator():
            ui.Separator(
                delegate=ui.MenuDelegate(
                    on_build_item=lambda _: ui.Line(
                        height=0, alignment=ui.Alignment.V_CENTER, style_type_name_override="Menu.Separator"
                    )
                )
            )

        self.menu = ui.Menu(
            "Burger Menu",
            menu_compatibility=False,
            delegate=self._delegate,
            style_type_name_override="MenuBurger",
        )

        with self.menu:
            ui.MenuItem(
                "Unload Stage",
                identifier="empty_stage",
                style_type_name_override="MenuBurgerItem",
                triggered_fn=self._create_new_workfile,
                tooltip="Create a new stage in the current session.",
            )
            self._reload_stage_menu_item = ui.MenuItem(
                "Reload Last Stage",
                identifier="reload_stage",
                style_type_name_override="MenuBurgerItem",
                triggered_fn=self._reload_last_workfile,
                tooltip="Reload the previous stage in the current session.",
            )
            create_separator()
            ui.MenuItem(
                "Save",
                identifier="save",
                style_type_name_override="MenuBurgerItem",
                triggered_fn=self._save,
                hotkey_text="Ctrl+S",
            )
            ui.MenuItem(
                "Save as",
                identifier="save_as",
                style_type_name_override="MenuBurgerItem",
                triggered_fn=self._save_as,
                hotkey_text="Ctrl+Shift+S",
            )
            create_separator()
            ui.MenuItem(
                "Undo",
                identifier="undo",
                style_type_name_override="MenuBurgerItem",
                triggered_fn=self._undo,
                hotkey_text="Ctrl+Z",
            )
            ui.MenuItem(
                "Redo",
                identifier="redo",
                style_type_name_override="MenuBurgerItem",
                triggered_fn=self._redo,
                hotkey_text="Ctrl+Y",
            )
            create_separator()
            ui.MenuItem(
                "Preferences",
                identifier="preferences",
                triggered_fn=self._show_preferences_window,
            )
            create_separator()
            ui.MenuItem(
                "Show Logs",
                identifier="logs",
                style_type_name_override="MenuBurgerItem",
                triggered_fn=self._open_logs_dir,
            )
            create_separator()
            ui.MenuItem(
                "About",
                identifier="about",
                style_type_name_override="MenuBurgerItem",
                triggered_fn=self._show_about_window,
            )

    def show_at(self, x, y):
        if self.menu.shown:
            return
        self.__on_show_menu(self._reload_stage_menu_item)
        self.menu.show_at(x, y)

    def destroy(self):
        _reset_default_attrs(self)
