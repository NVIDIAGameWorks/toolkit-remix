"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
import uuid
from typing import Optional, TypeVar

import omni.kit.test
import omni.kit.ui_test
import omni.kit.window.about
import omni.kit.window.preferences
import omni.ui as ui
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

    WINDOW_TITLE_ROOT = "TestBurgerMenu"

    def __init__(self):
        self._is_built = False

        # These are populated in `build` below.
        self._window: Optional[ui.Window] = None
        self._ui_builder: Optional[SetupUI] = None

    async def build(self):
        # Used to generate unique window title names
        salt = str(uuid.uuid1())
        self._window = ui.Window(
            f"{self.WINDOW_TITLE_ROOT}_{salt}",
            height=0,
            width=100,
            position_x=0,
            position_y=0,
        )
        with self._window.frame:
            self._ui_builder = SetupUI()
            self._ui_builder.show_at(self._window.width, 0)

        await asyncio.sleep(0.1)
        self._is_built = True

    async def destroy(self):
        self._ui_builder.menu.destroy()
        self._ui_builder.destroy()
        self._window.destroy()
        self._is_built = False

    async def __aenter__(self) -> AsyncTestMenuT:
        await self.build()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.destroy()

    def _get_menu_item(self, identifier: str) -> omni.kit.ui_test.WidgetRef:
        """
        Helper method to get a MenuItem for the provided identifier.

        Raises:
            ValueError: If the MenuItem with the provided identifier can not be found.
        """
        if not self._is_built:
            raise RuntimeError("Need to build the menu first.")

        result = omni.kit.ui_test.find(f"{self._window.title}//Frame/**/MenuItem[*].identifier=='{identifier}'")
        if result is None:
            raise ValueError(f"No MenuItem with identifier {identifier:!r}")
        return result

    async def click(self, identifier: str):
        """
        Helper to find and click a MenuItem.
        """
        menu_item = self._get_menu_item(identifier)

        # NOTE: Don't use .click() here due to the call to .focus() which will hide the widget.
        await omni.kit.ui_test.emulate_mouse_move_and_click(menu_item.center)


class TestWorkFileBurgerMenu(omni.kit.test.AsyncTestCase):
    async def test_properties(self):
        async with AsyncTestMenu() as menu:
            await menu.click("preferences")

            inst = omni.kit.window.preferences.get_instance()
            self.assertTrue(inst._window_is_visible)  # noqa PLW0212
            # NOTE: Use this helper to destroy the window to ensure the preferences instance keeps the proper state.
            inst.hide_preferences_window()

    async def test_about(self):
        async with AsyncTestMenu() as menu:
            await menu.click("about")

            inst = omni.kit.window.about.get_instance()
            self.assertTrue(inst._is_visible())  # noqa PLW0212
            # NOTE: The about extension doesn't create/destroy the window just toggles its visibility.
            inst.show(False)
