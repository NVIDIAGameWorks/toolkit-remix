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
import functools

import omni
import omni.ext
import omni.kit.menu.utils as omni_utils
import omni.usd
from lightspeed.color_to_roughness.core import ColorToRoughnessCore
from lightspeed.common import constants
from lightspeed.error_popup.window import ErrorPopup
from lightspeed.layer_helpers import LightspeedTextureProcessingCore
from lightspeed.progress_popup.window import ProgressPopup
from omni.kit.menu.utils import MenuItemDescription

# processing_method = UpscalerCore.perform_upscale
# input_texture_type = constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE
# output_texture_type = constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE
# output_suffix = "_upscaled4x.png"
processing_config = (
    ColorToRoughnessCore.perform_conversion,
    constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
    constants.MATERIAL_INPUTS_REFLECTIONROUGHNESS_TEXTURE,
    "_color2roughness.png",
)
processing_config_overwrite = (
    functools.partial(ColorToRoughnessCore.perform_conversion, overwrite=True),
    constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
    constants.MATERIAL_INPUTS_REFLECTIONROUGHNESS_TEXTURE,
    "_color2roughness.png",
)


class LightspeedColorToNormalMenuExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self.__create_save_menu()
        self._progress_bar = None

    def __create_save_menu(self):

        sub_menu = [
            MenuItemDescription(
                name="Skip already converted one",
                onclick_fn=self.__clicked,
                glyph="none.svg",
            ),
            MenuItemDescription(
                name="Overwrite all textures (re-convert everything)",
                onclick_fn=self.__clicked_overwrite,
                glyph="none.svg",
            ),
        ]

        self._tools_manager_menus = [
            MenuItemDescription(
                name="Batch Convert All Game Capture Color Textures to Roughness Maps",
                glyph="none.svg",
                sub_menu=sub_menu,
            )
        ]
        omni_utils.add_menu_items(self._tools_manager_menus, "Batch Tools")

    def on_shutdown(self):
        omni_utils.remove_menu_items(self._tools_manager_menus, "Batch Tools")

    def _batch_upscale_set_progress(self, progress):
        if not self._progress_bar:
            self._progress_bar = ProgressPopup(title="Converting")
            self._progress_bar.show()
        self._progress_bar.set_progress(progress)

    @omni.usd.handle_exception
    async def _run_batch_upscale(self, config):
        if not self._progress_bar:
            self._progress_bar = ProgressPopup(title="Converting")
        self._progress_bar.set_progress(0)
        self._progress_bar.show()
        error = await LightspeedTextureProcessingCore.lss_async_batch_process_entire_capture_layer(
            config, progress_callback=self._batch_upscale_set_progress
        )
        if error:
            self._error_popup = ErrorPopup("An error occurred while converting", error, window_size=(350, 150))
            self._error_popup.show()
        if self._progress_bar:
            self._progress_bar.hide()
            self._progress_bar = None

    def __clicked(self):
        asyncio.ensure_future(self._run_batch_upscale(processing_config))

    def __clicked_overwrite(self):
        asyncio.ensure_future(self._run_batch_upscale(processing_config_overwrite))
