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
import os

import omni.ext
import omni.kit.window.content_browser
from lightspeed.upscale.core import UpscaleModels, UpscalerCore


class UpscalerContentBrowserMenuExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        win = omni.kit.window.content_browser.get_content_window()
        win.add_context_menu(
            "Upscale Texture",
            glyph="none.svg",
            click_fn=self.context_menu_on_click_upscale,
            show_fn=self.context_menu_can_show_menu_upscale,
            index=0,
        )

    def on_shutdown(self):
        win = omni.kit.window.content_browser.get_content_window()
        if win is not None:
            win.delete_context_menu("Upscale Texture")

    def upscale(self, source_path, dest_path):
        UpscalerCore.perform_upscale(UpscaleModels.ESRGAN.value, source_path, dest_path)

    def context_menu_on_click_upscale(self, menu, value):
        upscale_path = value.replace(os.path.splitext(value)[1], "_upscaled4x" + os.path.splitext(value)[1])
        asyncio.ensure_future(UpscalerCore.async_perform_upscale(UpscaleModels.ESRGAN.value, value, upscale_path))

    def context_menu_can_show_menu_upscale(self, path):
        if path.lower().endswith(".dds") or path.lower().endswith(".png"):
            return True
        return False
