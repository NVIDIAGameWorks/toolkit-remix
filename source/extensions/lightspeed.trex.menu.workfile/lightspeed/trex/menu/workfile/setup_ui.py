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

import carb.input
import carb.tokens
import omni.flux.feature_flags.window
import omni.kit.app
import omni.kit.window.about
import omni.kit.window.preferences
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.path_utils import open_file_using_os_default
from omni.kit.menu import utils as _menu_utils
from omni.kit.menu.utils import build_submenu_dict as _build_submenu_dict
from omni.kit.widget.prompt import PromptButtonInfo, PromptManager


@omni.usd.handle_exception
async def async_focus_window(window_name: str):
    """
    Focus the provided window name.
    """
    window = ui.Workspace.get_window(window_name)
    if window is None:
        raise ValueError(f"Could not find window named {window_name}")
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
        self._default_attr = {"_menu_items": None, "_sub_app_ready": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self.__on_save = _Event()
        self.__on_save_as = _Event()
        self.__on_new_workfile = _Event()
        self.__undo = _Event()
        self.__redo = _Event()

        startup_event_stream = omni.kit.app.get_app().get_startup_event_stream()
        self._sub_app_ready = startup_event_stream.create_subscription_to_pop_by_type(
            omni.kit.app.EVENT_APP_READY, lambda *_: self.__register_menu_items(), name="Workfile Menu - App Ready"
        )

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
    def _show_feature_flags() -> None:
        inst = omni.flux.feature_flags.window.get_instance()
        if not inst:
            error_prompt("Feature flags extension is not loaded yet")
            return

        inst.show(True)
        # Force the tab to be the active/focused tab (this currently needs to be done in async)
        asyncio.ensure_future(async_focus_window(inst.window.title))

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

    def __register_menu_items(self):
        self._sub_app_ready = None

        menu_items = [
            _menu_utils.MenuItemDescription(
                name="File/Save",
                onclick_fn=self._save,
                hotkey=(carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL, carb.input.KeyboardInput.S),
            ),
            _menu_utils.MenuItemDescription(
                name="File/Save As...",
                onclick_fn=self._save_as,
                hotkey=(
                    carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL | carb.input.KEYBOARD_MODIFIER_FLAG_SHIFT,
                    carb.input.KeyboardInput.S,
                ),
            ),
            _menu_utils.MenuItemDescription(name="File/Close Project", onclick_fn=self._create_new_workfile),
            _menu_utils.MenuItemDescription(
                name="Edit/Undo",
                onclick_fn=self._undo,
                hotkey=(carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL, carb.input.KeyboardInput.Z),
            ),
            _menu_utils.MenuItemDescription(
                name="Edit/Redo",
                onclick_fn=self._redo,
                hotkey=(carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL, carb.input.KeyboardInput.Y),
            ),
            _menu_utils.MenuItemDescription(
                name="Edit/Preferences", onclick_fn=self._show_preferences_window, appear_after="Edit/Redo"
            ),
            _menu_utils.MenuItemDescription(name="Help/Optional Features", onclick_fn=self._show_feature_flags),
            _menu_utils.MenuItemDescription(name="Help/Show Logs", onclick_fn=self._open_logs_dir),
            _menu_utils.MenuItemDescription(name="Help/About", onclick_fn=self._show_about_window),
        ]

        self._menu_items = _build_submenu_dict(menu_items)
        for group in self._menu_items:
            _menu_utils.add_menu_items(self._menu_items[group], group)

        _menu_utils.set_default_menu_priority("File", -2)
        _menu_utils.set_default_menu_priority("Edit", -1)
        _menu_utils.set_default_menu_priority("Window", 0)
        _menu_utils.set_default_menu_priority("Help", 1)

    def destroy(self):
        if self._menu_items:
            for group in self._menu_items:
                _menu_utils.remove_menu_items(self._menu_items[group], group)
        _reset_default_attrs(self)
