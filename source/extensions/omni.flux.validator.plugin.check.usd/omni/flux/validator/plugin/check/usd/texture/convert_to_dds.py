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

import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import carb
import carb.tokens
import omni.client
import omni.ui as ui
import omni.usd
from omni.flux.asset_importer.core.data_models import (
    TEXTURE_TYPE_CONVERTED_SUFFIX_MAP as _TEXTURE_TYPE_CONVERTED_SUFFIX_MAP,
)
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP as _TEXTURE_TYPE_INPUT_MAP
from omni.flux.asset_importer.core.data_models import TextureTypes as _TextureTypes
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.utils.common.path_utils import get_new_hash as _get_new_hash
from omni.flux.utils.common.path_utils import get_udim_sequence as _get_udim_sequence
from omni.flux.utils.common.path_utils import is_udim_texture as _is_udim_texture
from omni.flux.utils.common.path_utils import texture_to_udim as _texture_to_udim
from omni.flux.utils.common.path_utils import write_metadata as _write_metadata
from omni.flux.validator.factory import InOutDataFlow as _InOutDataFlow
from omni.flux.validator.factory import utils as _validator_factory_utils
from pxr import Sdf
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD  # noqa PLE0402


def _generate_out_path(in_path_str: str, suffix: str):
    parts = suffix.rpartition(".")
    in_path = Path(in_path_str)
    in_stem = in_path.stem
    if in_stem.endswith(parts[0]):
        return in_path.with_name(in_stem + "." + parts[-1])
    return in_path.with_name(in_stem + suffix)


class ConversionArgs(BaseModel):
    args: list[str]
    model_config = ConfigDict(extra="forbid")


class ConvertToDDS(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        conversion_args: dict[str, ConversionArgs] = Field(
            default={
                "inputs:diffuse_texture": ConversionArgs(
                    args=["--format", "bc7", "--mip-gamma-correct"],
                ),
                "inputs:normalmap_texture": ConversionArgs(
                    args=["--format", "bc5", "--no-mip-gamma-correct"],
                ),
                # TODO [REMIX-1018]: our MDL files don't support tangent textures yet.
                # "inputs:tangent_texture": ConversionArgs(
                #     args=["--format", "bc5", "--no-mip-gamma-correct"],
                # ),
                "inputs:reflectionroughness_texture": ConversionArgs(
                    args=["--format", "bc4", "--no-mip-gamma-correct"],
                ),
                "inputs:emissive_mask_texture": ConversionArgs(
                    args=["--format", "bc7", "--mip-gamma-correct"],
                ),
                "inputs:metallic_texture": ConversionArgs(
                    args=["--format", "bc4", "--no-mip-gamma-correct"],
                ),
                "inputs:height_texture": ConversionArgs(
                    args=["--format", "bc4", "--no-mip-gamma-correct", "--mip-filter", "max"],
                ),
                "inputs:transmittance_texture": ConversionArgs(
                    args=["--format", "bc7", "--mip-gamma-correct"],
                ),
            }
        )
        replace_udim_textures_by_empty: bool = Field(default=False)
        suffix: str = Field(default=".rtex.dds")

        _compatible_data_flow_names = ["InOutData"]
        data_flows: list[_InOutDataFlow] | None = Field(default=None)

        @field_validator("suffix", mode="before")
        @classmethod
        def dot_in_suffix(cls, v: str) -> str:
            if not v.startswith("."):
                return f".{v}"
            return v

    name = "ConvertToDDS"
    tooltip = "This plugin will ensure all textures are encoded as DDS"
    data_type = Data
    display_name = "Convert Textures to DDS"

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to check if asset paths on the selected prims in the attributes listed in schema
        data's `conversion_args` are dds encoded

        Note: This is intended to be run on Shader prims.

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        context = omni.usd.get_context(context_plugin_data)
        stage_url = context.get_stage_url()
        message = f"Stage: {stage_url}\nCheck:\n"
        all_pass = True
        for prim in selector_plugin_data:  # noqa
            for attr_name in schema_data.conversion_args:
                texture_paths = []
                attr = prim.GetAttribute(attr_name)
                if attr and attr.Get():
                    abs_path_str = attr.Get().resolvedPath
                    if not abs_path_str:
                        all_pass = False
                        message += f"- FAIL: {attr.GetPath()} = `{attr.Get()}`. Failed to resolve path.\n"
                        continue

                    abs_path_omni_url = _OmniUrl(abs_path_str)
                    abs_path_str = str(abs_path_omni_url.path)
                    is_udim = _is_udim_texture(abs_path_str)
                    texture_paths = [abs_path_str]
                    if is_udim:
                        if schema_data.replace_udim_textures_by_empty:
                            message += f"- REPLACE UDIM Texture: {attr.GetPath()} = `{attr.Get()}`.\n"
                        texture_paths = _get_udim_sequence(abs_path_str)
                        if not texture_paths:
                            all_pass = False
                            message += f"- FAIL: {attr.GetPath()} = `{attr.Get()}`. UDIM files don't exist.\n"
                            continue
                    elif not abs_path_omni_url.is_file:
                        all_pass = False
                        message += f"- FAIL: {attr.GetPath()} = `{attr.Get()}`. File doesn't exist.\n"
                        continue

                    for texture_path in texture_paths[:]:
                        suffix = self.__get_texture_type_suffix(attr_name)
                        suffixes = f".{suffix}{schema_data.suffix}" if suffix else schema_data.suffix
                        if not texture_path.endswith(suffixes):
                            all_pass = False
                            message += f"- FAIL: {attr.GetPath()} = `{attr.Get()}`. Incorrect suffix or extension.\n"
                            texture_paths.remove(texture_path)
                            continue

                if texture_paths:
                    _validator_factory_utils.push_output_data(schema_data, texture_paths)

                message += f"- PASS: {prim.GetPath()}\n"

        return all_pass, message, None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to triangulate the mesh prims (including geom subsets)

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        context = omni.usd.get_context(context_plugin_data)
        stage_url = context.get_stage_url()
        message = f"Stage: {stage_url}\nFix:\n"
        all_pass = True
        # collate all the files to generate
        files_needed = {}
        for prim in selector_plugin_data:
            for attr_name, settings in schema_data.conversion_args.items():
                attr = prim.GetAttribute(attr_name)
                if attr and attr.Get():
                    abs_path_str = attr.Get().resolvedPath
                    abs_path_omni_url = _OmniUrl(abs_path_str)
                    abs_path_str = str(abs_path_omni_url.path)
                    if not abs_path_str:
                        all_pass = False
                        message += f"- FAIL: {attr.GetPath()} = `{attr.Get()}`. Failed to resolve path.\n"
                        continue

                    is_udim = _is_udim_texture(abs_path_str)
                    texture_paths = [(abs_path_str, is_udim)]
                    if is_udim:
                        if schema_data.replace_udim_textures_by_empty:
                            message += f"- REPLACE UDIM Texture: {attr.GetPath()} = `{attr.Get()}`.\n"
                        texture_paths = [(texture_path, is_udim) for texture_path in _get_udim_sequence(abs_path_str)]
                        if not texture_paths:
                            all_pass = False
                            message += f"- FAIL: {attr.GetPath()} = `{attr.Get()}`. UDIM files don't exist.\n"
                            continue
                    elif not abs_path_omni_url.is_file:
                        all_pass = False
                        message += f"- FAIL: {attr.GetPath()} = `{attr.Get()}`. File doesn't exist.\n"
                        continue

                    for texture_path, is_udim in texture_paths:
                        out_path = texture_path
                        suffix = self.__get_texture_type_suffix(attr_name)
                        suffixes = f".{suffix}{schema_data.suffix}" if suffix else schema_data.suffix
                        if not texture_path.endswith(suffixes):
                            out_path = str(_generate_out_path(texture_path, suffixes))

                        if out_path in files_needed:
                            files_needed[out_path][-1].append(attr)
                        else:
                            files_needed[out_path] = (texture_path, is_udim, settings, [attr])

        # generate all the files
        processed_files = []
        futures = []
        executor = ThreadPoolExecutor(max_workers=4)
        nvtt_path = carb.tokens.get_tokens_interface().resolve("${omni.flux.resources}/deps/tools/nvtt/nvtt_export.exe")
        for out_path_str, (in_path_str, is_udim, settings, attrs) in files_needed.items():
            out_path = Path(out_path_str)
            src_hash = _get_new_hash(in_path_str, out_path_str)

            _validator_factory_utils.push_input_data(schema_data, [in_path_str])

            if not out_path.exists() or src_hash is not None:
                cmd = [nvtt_path, in_path_str, "--output", out_path_str] + settings.args
                carb.log_info("Queuing DDS conversion: " + str(cmd))
                future = executor.submit(
                    subprocess.run, cmd, check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL
                )
                future.original_command = cmd
                future.attrs = attrs
                future.out_path = out_path
                future.is_udim = is_udim
                future.src_hash = src_hash
                futures.append(future)
                processed_files.append(in_path_str)
            else:
                # compressed texture exists and doesn't need to be updated
                with Sdf.ChangeBlock():
                    for attr in attrs:
                        value = out_path_str
                        if is_udim:
                            if schema_data.replace_udim_textures_by_empty:
                                value = ""
                            else:
                                value = _texture_to_udim(out_path_str)
                        attr.Set(value)
                message += f"- PASS: reused existing compressed texture: {out_path_str}\n"

        # Update all the attributes as the files are generated.
        if futures:
            progress = 0
            self.on_progress(progress, "Start", True)
            to_add = 1 / len(futures)
            for future in as_completed(futures):
                progress += to_add
                try:
                    result = future.result()
                    carb.log_info("DDS command result: " + str(result))
                    out_path_str = str(future.out_path)
                    _write_metadata(out_path_str, "src_hash", future.src_hash)
                    with Sdf.ChangeBlock():
                        for attr in future.attrs:
                            value = out_path_str
                            if future.is_udim:
                                if schema_data.replace_udim_textures_by_empty:
                                    value = ""
                                else:
                                    value = _texture_to_udim(out_path_str)
                            attr.Set(value)

                    _validator_factory_utils.push_output_data(schema_data, [out_path_str])

                    message += f"- PASS: created compressed texture {future.out_path}\n"
                    self.on_progress(progress, f"Compressed to {future.out_path}", True)
                except subprocess.CalledProcessError as e:  # noqa
                    carb.log_error(
                        "Exception when converting texture to dds.\n"
                        f"cmd: {e.cmd}\noutput: {e.output}\nstdout: {e.stdout}\nstderr: {e.stderr}"
                    )
                    message += f"- FAIL: failure in dds compression command: {future.original_command}.\n"
                    self.on_progress(progress, f"Error from {future.out_path}", True)
                    all_pass = False

        executor.shutdown(wait=True)
        await omni.kit.app.get_app().next_update_async()

        return all_pass, message, None

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")

    def __get_texture_type_suffix(self, attr_name: str) -> str:
        """
        Get the expected suffix based on the texture type. Get the texture type from the attribute name.
        """

        texture_type = None

        for _texture_type, shader_input in _TEXTURE_TYPE_INPUT_MAP.items():
            if shader_input == attr_name:
                texture_type = _texture_type
                break

        # All normal types share the same input & suffix
        normal_types = [_TextureTypes.NORMAL_OGL, _TextureTypes.NORMAL_DX, _TextureTypes.NORMAL_OTH]

        # If texture is a normal type, look for the common suffix
        if texture_type in normal_types:
            suffix = ""
            for _suffix, _texture_type in _TEXTURE_TYPE_CONVERTED_SUFFIX_MAP.items():
                for normal_type in normal_types:
                    if _texture_type == normal_type:
                        suffix = _suffix
                        break
                if suffix != "":
                    break
        # Otherwise look for the suffix for the actual texture type
        else:
            suffix = ""
            for _suffix, _texture_type in _TEXTURE_TYPE_CONVERTED_SUFFIX_MAP.items():
                if _texture_type == texture_type:
                    suffix = _suffix
                    break

        return suffix
