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
import functools

import omni
import omni.ext
import omni.kit.menu.utils as omni_utils
import omni.usd
from lightspeed.common import constants
from lightspeed.layer_helpers import LightspeedTextureProcessingCore
from lightspeed.progress_popup.window import ProgressPopup
from lightspeed.upscale.core import UpscalerCore
from omni.kit.menu.utils import MenuItemDescription

# processing_method = UpscalerCore.perform_upscale
# input_texture_type = constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE
# output_texture_type = constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE
# output_suffix = "_upscaled4x.dds"
processing_config = (
    UpscalerCore.perform_upscale,
    constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
    constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
    "_upscaled4x.dds",
)
processing_config_overwrite = (
    functools.partial(UpscalerCore.perform_upscale, overwrite=True),
    constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
    constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
    "_upscaled4x.dds",
)


class LightspeedUpscalerMenuExtension(omni.ext.IExt):
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
            MenuItemDescription(name="Batch Upscale All Game Capture Textures", glyph="none.svg", sub_menu=sub_menu)
        ]
        omni_utils.add_menu_items(self._tools_manager_menus, "Batch Tools")

    def on_shutdown(self):
        omni_utils.remove_menu_items(self._tools_manager_menus, "Batch Tools")

    def _batch_upscale_set_progress(self, progress):
        if not self._progress_bar:
            self._progress_bar = ProgressPopup(title="Upscaling")
            self._progress_bar.show()
        self._progress_bar.set_progress(progress)

    @omni.usd.handle_exception
    async def _run_batch_upscale(self, config):
        if not self._progress_bar:
            self._progress_bar = ProgressPopup(title="Upscaling")
        self._progress_bar.set_progress(0)
        self._progress_bar.show()
        await LightspeedTextureProcessingCore.lss_async_batch_process_entire_capture_layer(
            config, progress_callback=self._batch_upscale_set_progress
        )
        if self._progress_bar:
            self._progress_bar.hide()
            self._progress_bar = None

    def __clicked(self):
        asyncio.ensure_future(self._run_batch_upscale(processing_config))

    def __clicked_overwrite(self):
        asyncio.ensure_future(self._run_batch_upscale(processing_config_overwrite))
