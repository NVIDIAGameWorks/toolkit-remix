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

import omni
import omni.ext
import omni.kit.menu.utils as omni_utils
import omni.usd
from lightspeed.color_to_roughness.core import ColorToRoughnessCore
from lightspeed.common import constants
from lightspeed.layer_helpers import LightspeedTextureProcessingCore
from lightspeed.progress_popup.window import ProgressPopup
from omni.kit.menu.utils import MenuItemDescription

# processing_method = UpscalerCore.perform_upscale
# input_texture_type = constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE
# output_texture_type = constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE
# output_suffix = "_upscaled4x.dds"
processing_config = (
    ColorToRoughnessCore.perform_conversion,
    constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
    constants.MATERIAL_INPUTS_NORMALMAP_TEXTURE,
    "_color2roughness.dds",
)


class LightspeedColorToNormalMenuExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self.__create_save_menu()
        self._progress_bar = None

    def __create_save_menu(self):
        self._tools_manager_menus = [
            MenuItemDescription(
                name="Batch Convert All Game Capture Color Textures to Roughness Maps",
                onclick_fn=self.__clicked,
                glyph="none.svg",
            )
        ]
        omni_utils.add_menu_items(self._tools_manager_menus, "Batch Tools")

    def on_shutdown(self):
        omni_utils.remove_menu_items(self._tools_manager_menus, "Batch Tools")

    def _batch_upscale_set_progress(self, progress):
        self._progress_bar.set_progress(progress)

    @omni.usd.handle_exception
    async def _run_batch_upscale(self):
        if not self._progress_bar:
            self._progress_bar = ProgressPopup(title="Converting")
        self._progress_bar.set_progress(0)
        self._progress_bar.show()
        await LightspeedTextureProcessingCore.lss_async_batch_process_entire_capture_layer(
            processing_config, progress_callback=self._batch_upscale_set_progress
        )
        if self._progress_bar:
            self._progress_bar.hide()
            self._progress_bar = None

    def __clicked(self):
        asyncio.ensure_future(self._run_batch_upscale())
