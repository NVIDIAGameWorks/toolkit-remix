"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import os
import os.path
import asyncio

import omni
import omni.ext
import omni.kit.menu.utils as omni_utils
import omni.kit.window.content_browser
from omni.kit.menu.utils import MenuItemDescription
from omni.kit.tool.collect.progress_popup import ProgressPopup

from .upscale_core import LightspeedUpscalerCore


class LightspeedUpscalerExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self._batch_upscale_thread = None
        self.__create_save_menu()
        win = omni.kit.window.content_browser.get_content_window()
        win.add_context_menu(
            "Upscale Texture",
            glyph="none.svg",
            click_fn=self.context_menu_on_click_upscale,
            show_fn=self.context_menu_can_show_menu_upscale,
            index=0,
        )
        self._progress_bar = None

    def __create_save_menu(self):
        self._tools_manager_menus = [
            MenuItemDescription(
                name="Batch Upscale All Game Capture Textures", onclick_fn=self.__clicked, glyph="none.svg"
            )
        ]
        omni_utils.add_menu_items(self._tools_manager_menus, "Batch Tools")

    def on_shutdown(self):
        omni_utils.remove_menu_items(self._tools_manager_menus, "Batch Tools")
        win = omni.kit.window.content_browser.get_content_window()
        win.delete_context_menu("Upscale Texture")

    def context_menu_on_click_upscale(self, menu, value):
        upscale_path = value.replace(os.path.splitext(value)[1], "_upscaled4x.dds")
        LightspeedUpscalerCore.perform_upscale(value, upscale_path)

    def context_menu_can_show_menu_upscale(self, path):
        if path.lower().endswith(".dds") or path.lower().endswith(".png"):
            return True
        return False

    def _batch_upscale_set_progress(self, progress):
        self._progress_bar.set_progress(progress)

    async def _run_batch_upscale(self):
        if not self._progress_bar:
            self._progress_bar = ProgressPopup(title="Upscaling")
        self._progress_bar.set_progress(0)
        self._progress_bar.show()
        await LightspeedUpscalerCore.lss_async_batch_upscale_capture_layer(progress_callback=self._batch_upscale_set_progress)
        self._progress_bar.hide()
        self._progress_bar = None

    def __clicked(self):
        asyncio.ensure_future(self._run_batch_upscale())
