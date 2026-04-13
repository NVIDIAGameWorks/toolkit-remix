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

from typing import TypeVar
from unittest.mock import Mock, patch

import omni.kit.test
import omni.kit.ui_test
import omni.kit.window.about
import omni.kit.window.preferences
from lightspeed.trex.menu.workfile.extension import get_instance
from lightspeed.trex.menu.workfile.setup_ui import SetupUI

# NOTE: This can be swapped out with typing.Self once we update our version of typing.
AsyncTestMenuT = TypeVar("AsyncTestMenuT", bound="AsyncTestMenu")


class AsyncTestMenu:
    """
    Helper context manager for testing the menu workfile burger menu.

    Example
    -------
    >>> async with AsyncTestMenu() as menu:
    ...     menu.click('properties')
    """

    _MENU_PATH_BY_IDENTIFIER = {
        "preferences": "Edit/Preferences",
        "about": "Help/About",
        "logs": "Help/Show Logs",
        "empty_stage": "File/Close Project",
    }

    def __init__(self):
        self._is_built = False

        # Populated in `build` below.
        self._ui_builder: SetupUI | None = None

    @property
    def ui_builder(self) -> SetupUI:
        if self._ui_builder is None:
            raise RuntimeError("Need to build the menu first.")
        return self._ui_builder

    async def build(self):
        # Reuse the live extension instance so the test drives the actual menu entries registered
        # during extension startup.
        self._ui_builder = get_instance()
        if self._ui_builder is None:
            raise RuntimeError("Workfile menu extension is not loaded.")

        await omni.kit.ui_test.human_delay(10)
        self._is_built = True

    async def destroy(self):
        await omni.kit.ui_test.human_delay(10)
        self._ui_builder = None
        self._is_built = False

    async def __aenter__(self) -> AsyncTestMenuT:
        await self.build()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.destroy()

    async def click(self, identifier: str):
        """
        Helper to click a workfile menu entry through the real app menubar.
        """
        if not self._is_built:
            raise RuntimeError("Need to build the menu first.")

        await omni.kit.ui_test.menu_click(self._MENU_PATH_BY_IDENTIFIER[identifier], human_delay_speed=4)
        await omni.kit.ui_test.human_delay(10)


class TestWorkFileBurgerMenu(omni.kit.test.AsyncTestCase):
    async def test_properties(self):
        async with AsyncTestMenu() as menu:
            await menu.click("preferences")

            inst = omni.kit.window.preferences.get_instance()
            self.assertTrue(inst._window_is_visible)
            # NOTE: Use this helper to destroy the window to ensure the preferences instance keeps the proper state.
            inst.hide_preferences_window()
            await omni.kit.ui_test.human_delay(10)

    async def test_about(self):
        async with AsyncTestMenu() as menu:
            await menu.click("about")

            inst = omni.kit.window.about.get_instance()
            self.assertTrue(inst._is_visible())
            # NOTE: The about extension doesn't create/destroy the window just toggles its visibility.
            inst.show(False)
            await omni.kit.ui_test.human_delay(10)

    async def test_show_logs(self):
        with patch("lightspeed.trex.menu.workfile.setup_ui.open_file_using_os_default") as mock_open:
            async with AsyncTestMenu() as menu:
                await menu.click("logs")
        self.assertEqual(1, mock_open.call_count)

    async def test_unload_stage(self):
        async with AsyncTestMenu() as menu:
            on_new_workfile = Mock()
            subscription = menu.ui_builder.subscribe_create_new_workfile(on_new_workfile)

            await menu.click("empty_stage")

            self.assertEqual(1, on_new_workfile.call_count)
            del subscription
