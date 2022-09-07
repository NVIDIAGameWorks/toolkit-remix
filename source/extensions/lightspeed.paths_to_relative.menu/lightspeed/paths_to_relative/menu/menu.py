"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import asyncio

import omni.ext
import omni.kit.menu.utils as omni_utils
import omni.usd
from lightspeed.paths_to_relative.window import get_instance
from omni.kit.menu.utils import MenuItemDescription


class LightspeedColorToNormalMenuExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self.__create_save_menu()

    def __create_save_menu(self):
        self._tools_manager_menus = [
            MenuItemDescription(
                name="Toggle paths to relative paths window",
                onclick_fn=self.__clicked,
                glyph="none.svg",
            )
        ]
        omni_utils.add_menu_items(self._tools_manager_menus, "Utils")

    def on_shutdown(self):
        omni_utils.remove_menu_items(self._tools_manager_menus, "Batch Tools")

    @omni.usd.handle_exception
    async def _show(self):
        get_instance().toggle_window()

    def __clicked(self):
        asyncio.ensure_future(self._show())
