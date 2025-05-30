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

import functools
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import IntEnum
from pathlib import Path
from typing import Any

import carb
import carb.tokens
import omni.client
import omni.ui as ui
import omni.usd
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.utils.common.path_utils import get_new_hash as _get_new_hash
from omni.flux.utils.common.path_utils import get_udim_sequence as _get_udim_sequence
from omni.flux.utils.common.path_utils import is_udim_texture as _is_udim_texture
from omni.flux.utils.common.path_utils import texture_to_udim as _texture_to_udim
from omni.flux.utils.common.path_utils import write_metadata as _write_metadata
from omni.flux.utils.octahedral_converter import OctahedralConverter
from omni.flux.validator.factory import InOutDataFlow as _InOutDataFlow
from omni.flux.validator.factory import utils as _validator_factory_utils
from pxr import Sdf
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD  # noqa PLE0402


# This should match the `normalmap_encoding` in AperturePBR_normal.mdl
class NormalMapEncodings(IntEnum):
    OCTAHEDRAL = 0
    TANGENT_SPACE_OGL = 1
    TANGENT_SPACE_DX = 2


def _generate_out_path(in_path_str: str, suffix: str, replace_suffix: str):
    in_path = Path(in_path_str)
    in_stem = in_path.stem
    if in_stem.endswith(suffix):
        return in_path
    if in_stem.endswith(replace_suffix):
        return in_path.with_name(in_stem[0 : -len(replace_suffix)] + suffix + in_path.suffix)  # noqa E203

    return in_path.with_name(in_stem + suffix + in_path.suffix)


class ConversionArgs(BaseModel):
    encoding_attr: str
    suffix: str
    replace_suffix: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("suffix", mode="before")
    @classmethod
    def dot_not_in_suffix(cls, v: str) -> str:
        if "." in v:
            raise ValueError("suffix cannot contain a `.`")
        return v

    @field_validator("replace_suffix", mode="before")
    @classmethod
    def dot_not_in_replace_suffix(cls, v: str) -> str:
        if "." in v:
            raise ValueError("replace_suffix cannot contain a `.`")
        return v


class ConvertToOctahedral(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        conversion_args: dict[str, ConversionArgs] = Field(
            default={
                "inputs:normalmap_texture": ConversionArgs(
                    encoding_attr="inputs:encoding",
                    suffix="_OTH_Normal",
                    replace_suffix="_Normal",
                ),
                # TODO [REMIX-1018]: our MDL files don't support tangent textures yet.
                # "inputs:tangent_texture": ConversionArgs(
                #     encoding_attr="inputs:tangent_encoding",
                #     suffix="_OTH_Tangent",
                #     replace_suffix="_Tangent",
                # ),
            }
        )
        replace_udim_textures_by_empty: bool = Field(default=False)

        _compatible_data_flow_names = ["InOutData"]
        data_flows: list[_InOutDataFlow] | None = Field(default=None)

    name = "ConvertToOctahedral"
    tooltip = "This plugin will ensure all normal maps are octahedral encoded"
    data_type = Data
    display_name = "Convert Normal Maps to Octahedral"

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to check if normal maps are octahedral encoded

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
            for attr_name, settings in schema_data.conversion_args.items():
                attr = prim.GetAttribute(attr_name)
                if not attr or not attr.HasValue():
                    continue

                abs_path_str = attr.Get().resolvedPath
                if not abs_path_str:
                    # no texture set!
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

                encoding_attr = prim.GetAttribute(settings.encoding_attr)
                if encoding_attr and encoding_attr.HasValue:
                    encoding = encoding_attr.Get()
                    if encoding != NormalMapEncodings.OCTAHEDRAL.value:
                        all_pass = False
                        message += f"- Fail: {attr.GetPath()} is not octahedral encoded.\n"
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
        Function that will be executed to convert normal maps to octahedral encoding

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
        for prim in selector_plugin_data:  # noqa
            for attr_name, settings in schema_data.conversion_args.items():
                attr = prim.GetAttribute(attr_name)
                if not attr or not attr.HasValue():
                    continue

                abs_path_str = attr.Get().resolvedPath
                if not abs_path_str:
                    # no texture set!
                    continue

                abs_path_omni_url = _OmniUrl(abs_path_str)
                abs_path_str = str(abs_path_omni_url.path)
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

                encoding_attr = prim.GetAttribute(settings.encoding_attr)
                if not encoding_attr or not encoding_attr.HasValue:
                    # pick default (if none exists, then must be DX normals)
                    encoding = NormalMapEncodings.TANGENT_SPACE_DX.value
                else:
                    encoding = encoding_attr.Get()

                if encoding != NormalMapEncodings.OCTAHEDRAL.value:
                    for texture_path, is_udim in texture_paths:
                        if not texture_path.endswith(settings.suffix):
                            # queue creation or conversion of texture
                            out_path = str(_generate_out_path(texture_path, settings.suffix, settings.replace_suffix))

                            if out_path in files_needed:
                                files_needed[out_path][-1].append((attr, encoding_attr))
                            else:
                                files_needed[out_path] = (texture_path, is_udim, encoding, [(attr, encoding_attr)])

        # generate all the files
        processed_files = []
        futures = []
        executor = ThreadPoolExecutor(max_workers=4)
        for out_path_str, (in_path_str, is_udim, encoding, attrs) in files_needed.items():
            out_path = Path(out_path_str)
            src_hash = _get_new_hash(in_path_str, out_path_str)

            _validator_factory_utils.push_input_data(schema_data, [in_path_str])

            if not out_path.exists() or src_hash is not None:
                future = None
                if encoding == NormalMapEncodings.TANGENT_SPACE_DX.value:
                    future = executor.submit(
                        functools.partial(OctahedralConverter.convert_dx_file_to_octahedral, in_path_str, out_path_str)
                    )
                elif encoding == NormalMapEncodings.TANGENT_SPACE_OGL.value:
                    future = executor.submit(
                        functools.partial(OctahedralConverter.convert_ogl_file_to_octahedral, in_path_str, out_path_str)
                    )
                if future:
                    future.attrs = attrs
                    future.is_udim = is_udim
                    future.out_path = out_path
                    future.src_hash = src_hash
                    futures.append(future)
                    processed_files.append(in_path_str)
            else:
                # octahedral texture exists and doesn't need to be updated
                with Sdf.ChangeBlock():
                    for attr, encoding_attr in attrs:
                        value = out_path_str
                        if is_udim:
                            if schema_data.replace_udim_textures_by_empty:
                                value = ""
                            else:
                                value = _texture_to_udim(out_path_str)
                        attr.Set(value)
                        encoding_attr.Set(NormalMapEncodings.OCTAHEDRAL.value)
                message += f"- PASS: reused existing octahedral map: {out_path}\n"

        if futures:
            # Update all the attributes as the files are generated.
            progress = 0
            self.on_progress(progress, "Start", True)
            to_add = 1 / len(futures)
            for future in as_completed(futures):
                progress += to_add
                try:
                    result = future.result()
                    carb.log_info("Octahedral command result: " + str(result))
                    out_path_str = str(future.out_path)
                    _write_metadata(out_path_str, "src_hash", future.src_hash)
                    with Sdf.ChangeBlock():
                        for attr, encoding_attr in future.attrs:
                            value = out_path_str
                            if future.is_udim:
                                if schema_data.replace_udim_textures_by_empty:
                                    value = ""
                                else:
                                    value = _texture_to_udim(out_path_str)
                            attr.Set(value)
                            encoding_attr.Set(NormalMapEncodings.OCTAHEDRAL.value)

                    _validator_factory_utils.push_output_data(schema_data, [out_path_str])

                    message += f"- PASS: created octahedral map {future.out_path}\n"
                    self.on_progress(progress, f"Compressed to {future.out_path}", True)
                except Exception:  # noqa
                    carb.log_error(
                        f"Exception when creating octahedral map at {future.out_path}.\n" + traceback.format_exc()
                    )
                    message += f"- FAIL: exception during octahedral conversion: {future.out_path}.\n"
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
