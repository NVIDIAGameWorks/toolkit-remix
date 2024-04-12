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
