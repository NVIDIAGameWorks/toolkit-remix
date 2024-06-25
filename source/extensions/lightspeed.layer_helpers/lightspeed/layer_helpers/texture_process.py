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
from pathlib import Path
from typing import Optional

import omni.usd
from lightspeed.common import constants
from lightspeed.layer_manager.core import LayerManagerCore, LayerType


class LightspeedTextureProcessingCore:
    @staticmethod
    def lss_get_capture_textures_by_prim_paths(input_texture_type, prim_paths, context_name=""):
        layer_manager = LayerManagerCore(context_name)
        return layer_manager.get_layer_instance(LayerType.capture).get_textures_by_prim_paths(
            prim_paths, input_texture_type
        )

    @staticmethod
    def lss_collect_capture_textures(input_texture_type, context_name=""):
        layer_manager = LayerManagerCore(context_name)
        return layer_manager.get_layer_instance(LayerType.capture).get_textures(input_texture_type)

    @staticmethod
    @omni.usd.handle_exception
    async def async_batch_texture_process(
        processing_method, asset_absolute_paths, output_asset_absolute_paths, progress_callback=None
    ):
        loop = asyncio.get_event_loop()
        if len(asset_absolute_paths) != len(output_asset_absolute_paths):
            raise RuntimeError("List length mismatch.")
        total = len(asset_absolute_paths)
        for i, asset_absolute_path in enumerate(asset_absolute_paths):
            # perform upscale and place the output textures next to the enhancements layer location
            await loop.run_in_executor(None, processing_method, asset_absolute_path, output_asset_absolute_paths[i])
            if progress_callback:
                progress_callback((i + 1) / total)

    @staticmethod
    def blocking_batch_texture_process(processing_method, asset_absolute_paths, output_asset_absolute_paths):
        if len(asset_absolute_paths) != len(output_asset_absolute_paths):
            raise RuntimeError("List length mismatch.")
        for i, asset_absolute_path in enumerate(asset_absolute_paths):
            # perform upscale and place the output textures next to the enhancements layer location
            processing_method(asset_absolute_path, output_asset_absolute_paths[i])

    @staticmethod
    def lss_generate_populate_and_child_autoupscale_layer(
        output_texture_type, prim_paths, output_asset_relative_paths, context_name=""
    ):
        layer_manager = LayerManagerCore(context_name)
        # get/setup layers
        replacement_layer = layer_manager.get_layer(LayerType.replacement)
        # create/open and populate auto-upscale layer, placing it next to the enhancements layer
        enhancement_usd_dir = str(Path(replacement_layer.realPath).parent)
        auto_upscale_stage_absolute_path = str(Path(enhancement_usd_dir).joinpath(constants.AUTOUPSCALE_LAYER_FILENAME))
        if Path(auto_upscale_stage_absolute_path).exists():
            layer_manager.insert_sublayer(
                auto_upscale_stage_absolute_path, LayerType.autoupscale, False, -1, True, replacement_layer
            )
        else:
            layer_manager.create_new_sublayer(
                layer_type=LayerType.autoupscale,
                path=auto_upscale_stage_absolute_path,
                set_as_edit_target=False,
                parent_layer=replacement_layer,
            )
        layer_manager.get_layer_instance(LayerType.autoupscale).set_texture_attributes(
            output_texture_type, prim_paths, output_asset_relative_paths
        )

    @staticmethod
    def lss_filter_lists_for_file_existence(prim_paths, output_asset_absolute_paths, output_asset_relative_paths):
        return_prim_paths, return_output_asset_relative_paths = [], []
        if len(prim_paths) != len(output_asset_absolute_paths) or len(prim_paths) != len(output_asset_relative_paths):
            raise RuntimeError("List length mismatch.")
        for i, prim_path in enumerate(prim_paths):
            if Path(output_asset_absolute_paths[i]).exists():
                return_prim_paths.append(prim_path)
                return_output_asset_relative_paths.append(output_asset_relative_paths[i])
        return return_prim_paths, return_output_asset_relative_paths

    @staticmethod
    @omni.usd.handle_exception
    async def lss_async_batch_process_capture_layer(
        processing_config, prim_paths, abs_paths, rel_paths, progress_callback=None, context_name=""
    ) -> Optional[str]:
        """
        returns the error message if an error occurred
        """
        output_suffix = processing_config[3]
        processing_method = processing_config[0]
        output_texture_type = processing_config[2]
        replacement_layer = LayerManagerCore(context_name).get_layer(LayerType.replacement)
        if replacement_layer is None:
            return "No replacement layer was found. Make sure the opened USD file contains a replacement layer."
        replacement_layer_path = replacement_layer.realPath
        out_rel_paths = [path.replace(Path(path).suffix, output_suffix) for path in rel_paths]
        out_abs_paths = [
            str(Path(replacement_layer_path).parent.joinpath(out_rel_path)) for out_rel_path in out_rel_paths
        ]
        await LightspeedTextureProcessingCore.async_batch_texture_process(
            processing_method, abs_paths, out_abs_paths, progress_callback
        )
        prim_paths, out_rel_paths = LightspeedTextureProcessingCore.lss_filter_lists_for_file_existence(
            prim_paths, out_abs_paths, out_rel_paths
        )
        LightspeedTextureProcessingCore.lss_generate_populate_and_child_autoupscale_layer(
            output_texture_type, prim_paths, out_rel_paths, context_name
        )
        return None

    @staticmethod
    @omni.usd.handle_exception
    async def lss_async_batch_process_entire_capture_layer(
        processing_config, progress_callback=None, context_name=""
    ) -> Optional[str]:
        """
        returns the error message if an error occurred
        """
        LightspeedTextureProcessingCore.lss_workaround_gpu_crash()
        input_texture_type = processing_config[1]
        prim_paths, abs_paths, rel_paths = LightspeedTextureProcessingCore.lss_collect_capture_textures(
            input_texture_type, context_name
        )
        return await LightspeedTextureProcessingCore.lss_async_batch_process_capture_layer(
            processing_config, prim_paths, abs_paths, rel_paths, progress_callback, context_name
        )

    @staticmethod
    @omni.usd.handle_exception
    async def lss_async_batch_process_capture_layer_by_prim_paths(
        processing_config, prim_paths, progress_callback=None, context_name=""
    ) -> Optional[str]:
        """
        returns the error message if an error occurred
        """
        LightspeedTextureProcessingCore.lss_workaround_gpu_crash()
        input_texture_type = processing_config[1]
        abs_paths, rel_paths = LightspeedTextureProcessingCore.lss_get_capture_textures_by_prim_paths(
            input_texture_type, prim_paths, context_name
        )
        return await LightspeedTextureProcessingCore.lss_async_batch_process_capture_layer(
            processing_config, prim_paths, abs_paths, rel_paths, progress_callback, context_name
        )

    @staticmethod
    def lss_workaround_gpu_crash(context_name=""):
        LayerManagerCore(context_name).remove_layer(layer_type=LayerType.autoupscale)
