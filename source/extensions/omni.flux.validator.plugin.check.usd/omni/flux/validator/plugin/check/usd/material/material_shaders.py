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

from __future__ import annotations

import asyncio
import re
from collections import OrderedDict
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import carb
import omni.kit.app
import omni.kit.material.library
from omni import ui, usd
from omni.flux.utils.material_converter import MaterialConverterCore as _MaterialConverterCore
from omni.flux.utils.material_converter import NoneToAperturePBRConverterBuilder as _NoneToAperturePBRConverterBuilder
from omni.flux.utils.material_converter import (
    OmniGlassToAperturePBRConverterBuilder as _OmniGlassToAperturePBRConverterBuilder,
)
from omni.flux.utils.material_converter import (
    OmniPBRToAperturePBRConverterBuilder as _OmniPBRToAperturePBRConverterBuilder,
)
from omni.flux.utils.material_converter import (
    USDPreviewSurfaceToAperturePBRConverterBuilder as _USDPreviewSurfaceToAperturePBRConverterBuilder,
)
from omni.flux.utils.material_converter.utils import MaterialConverterUtils as _MaterialConverterUtils
from omni.flux.utils.material_converter.utils import SupportedShaderInputs as _SupportedShaderInputs
from omni.flux.utils.material_converter.utils import SupportedShaderOutputs as _SupportedShaderOutputs
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from pxr import UsdShade
from pydantic import Field, field_validator

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD

if TYPE_CHECKING:
    from pxr import Usd


@contextmanager
def disable_orphan_parameter_cleanup():
    """
    Disable orphan parameter cleanup temporarily
    """
    cleanup_orphan_parameters_path = "/exts/omni.usd/mdl/ignoreOrphanParametersCleanup"

    carb.log_info("Disable Orphan Parameter Cleanup")
    carb.settings.get_settings().set(cleanup_orphan_parameters_path, True)
    try:
        yield
    finally:
        carb.log_info("Enable Orphan Parameter Cleanup")
        carb.settings.get_settings().set(cleanup_orphan_parameters_path, False)


class MaterialShaders(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        # The first shader will be used by default when converting invalid materials
        context_name: str | None = Field(default=None)
        shader_subidentifiers: OrderedDict[str, str] = Field(...)
        ignore_not_convertable_shaders: bool = Field(default=False)

        @field_validator("shader_subidentifiers", mode="before")
        @classmethod
        def at_least_one(cls, v: OrderedDict[str, str]) -> OrderedDict[str, str]:
            if len(v) < 1:
                raise ValueError("There should at least be 1 item in shader_subidentifiers")
            return v

        @field_validator("shader_subidentifiers", mode="before")
        @classmethod
        def valid_subidentifier(cls, v: OrderedDict[str, str]) -> OrderedDict[str, str]:
            library_subidentifiers = [u.stem for u in _MaterialConverterUtils.get_material_library_shader_urls()]
            for key, _ in v.items():
                if key not in library_subidentifiers:
                    raise ValueError(
                        f"The subidentifier ({key}) does not exist in the material library. If using non-default"
                        f" shaders, add your shader path to the following setting "
                        f"'{_MaterialConverterUtils.MATERIAL_LIBRARY_SETTING_PATH}'. Currently available shaders are: "
                        f"{', '.join(library_subidentifiers) or 'None'}"
                    )
            return v

        @field_validator("shader_subidentifiers", mode="before")
        @classmethod
        def supported_shader_output(cls, v: OrderedDict[str, str]) -> OrderedDict[str, str]:
            for key, _ in v.items():
                if key not in [s.value for s in _SupportedShaderOutputs]:
                    raise ValueError(
                        f"The shader ({key}) is not currently a supported output shader. "
                        f"Supported shaders are: {', '.join([s.value for s in _SupportedShaderOutputs])}"
                    )
            return v

    name = "MaterialShaders"
    tooltip = "This plugin will ensure all materials in the stage use valid shaders"
    data_type = Data
    display_name = "Convert Material Shaders"

    def __init__(self):
        super().__init__()

        self._layers_invalid_paths = {}
        self.__fix_ran = False

    @usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns:
            bool: True if the check passed, False if not. If the check is True, it will NOT run the fix
            str: the message you want to show, like "Succeeded to check this"
            any: data that you want to pass. For now this is used no where. So you can pass whatever you want (None)
        """
        message = "Check:\n"
        progress = 0
        success = True

        self.on_progress(progress, "Start", success)

        if selector_plugin_data:
            progress_delta = 1 / len(selector_plugin_data)
            stage = usd.get_context(context_plugin_data).get_stage()
            root_identifier = stage.GetRootLayer().identifier

            for p in selector_plugin_data:
                prim = stage.GetPrimAtPath(p.GetPath())

                # This will validate the material definition.
                # Prims on overriding layer will appear as valid after fixing the definition.
                # Invalid layer should be the 1st layer we encounter the material in since we go bottom to top
                if self.__fix_ran and schema_data.ignore_not_convertable_shaders:
                    is_valid = True
                else:
                    is_valid = await self._validate_material_shaders(schema_data.shader_subidentifiers, prim)

                subidenfifier = await self._get_material_shader_subidentifier(prim)

                # Check if other layers marked this prim as invalid. If yes, we need to fix it on this layer as well
                for layer_identifier, invalid_paths in self._layers_invalid_paths.copy().items():
                    if layer_identifier != root_identifier and prim.GetPath() in invalid_paths:
                        # Add invalid state from other layer
                        subidenfifier = self._layers_invalid_paths[layer_identifier][prim.GetPath()]
                        is_valid = False

                        # Reset prim on other layer for future iterations
                        del self._layers_invalid_paths[layer_identifier][prim.GetPath()]
                        break

                # Cache the validity of the prim on this layer for the fix function
                if not is_valid:
                    if root_identifier not in self._layers_invalid_paths:
                        self._layers_invalid_paths[root_identifier] = {}
                    self._layers_invalid_paths[root_identifier][prim.GetPath()] = subidenfifier

                result_message = f"{'OK' if is_valid else 'INVALID'}: {str(prim.GetPath())}"
                message += f"- {result_message}\n"
                progress += progress_delta
                success &= is_valid
                self.on_progress(progress, result_message, success)
        else:
            message += "- SKIPPED: No selected prims"

        self.__fix_ran = False
        return success, message, None

    @usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> tuple[bool, str, Any]:
        """
        Function that will be executed to fix the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns:
            bool: True if the check passed, False if not. If the check is True, it will NOT run the fix
            str: the message you want to show, like "Succeeded to check this"
            any: data that you want to pass. For now this is used no where. So you can pass whatever you want (None)
        """
        message = "Fix:\n"
        progress = 0
        success = True

        self.on_progress(progress, "Start", success)

        if selector_plugin_data:
            progress_delta = 1 / len(selector_plugin_data)
            context = usd.get_context(context_plugin_data)
            stage = context.get_stage()
            root_identifier = stage.GetRootLayer().identifier

            with disable_orphan_parameter_cleanup():
                for prim in selector_plugin_data:
                    # Only fix invalid materials. Skip materials that were not tagged as invalid
                    if (
                        root_identifier not in self._layers_invalid_paths
                        or prim.GetPath() not in self._layers_invalid_paths[root_identifier]
                    ):
                        result_message = f"SKIPPED: {prim.GetPath()}"
                        message += f"- {result_message}\n"
                        progress += progress_delta
                        self.on_progress(progress, result_message, success)
                        continue

                    # Make sure we can convert the input shader
                    subidentifier = self._layers_invalid_paths[root_identifier][prim.GetPath()]
                    supported_identifier = subidentifier in [s.value for s in _SupportedShaderInputs]
                    converter = None
                    if not supported_identifier:
                        # Material mapping matcher: we try to see if the current material has the same inputs than a
                        # supported MDL.
                        shader = usd.get_shader_from_material(prim, get_prim=True)
                        if shader and shader.IsValid():
                            try:
                                (
                                    converter,
                                    tmp_subidenfifier,
                                ) = await _MaterialConverterCore.find_matching_supported_material(shader)
                                if converter is not None:
                                    subidentifier = tmp_subidenfifier.value
                            except asyncio.TimeoutError:
                                # Kit was frozen because an identifier was set but not found in the MDL
                                converter = None
                    if not supported_identifier and converter is None:
                        if schema_data.ignore_not_convertable_shaders:
                            was_fixed = True
                            result_message = (
                                f"WARNING: Unsupported input material '{subidentifier}'. "
                                f"Supported input material shaders "
                                f"are currently: {','.join([str(s.value) for s in _SupportedShaderInputs])} on layer "
                                f"{root_identifier}. Skipped"
                            )
                        else:
                            was_fixed = False
                            result_message = (
                                f"ERROR: Unsupported input material '{subidentifier}'. "
                                f"Supported input material shaders are currently: "
                                f"{','.join([str(s.value) for s in _SupportedShaderInputs])} on layer {root_identifier}"
                            )
                    else:

                        def _determine_output_shader(prim_name: str):
                            shader_output = ""
                            for name, re_pattern in schema_data.shader_subidentifiers.items():
                                if re.search(re_pattern, prim_name, re.IGNORECASE):
                                    shader_output = name
                                    break
                            return shader_output

                        was_fixed, conversion_message, _was_skipped = await self._convert_material(
                            schema_data.context_name if schema_data.context_name is not None else context_plugin_data,
                            _determine_output_shader(prim.GetName()),
                            subidentifier,
                            prim,
                        )
                        result_message = f"{'FIXED' if was_fixed else 'ERROR'}: {str(prim.GetPath())}"
                        if conversion_message:
                            result_message += f" - {conversion_message}"

                    message += f"- {result_message}\n"
                    progress += progress_delta
                    success &= was_fixed
                    self.on_progress(progress, result_message, success)

        self.__fix_ran = True
        return success, message, None

    @usd.handle_exception
    async def _get_material_shader_subidentifier(self, prim: Usd.Prim) -> str | None:
        shader_prim = usd.get_shader_from_material(prim, get_prim=True)
        subid_list = await omni.kit.material.library.get_subidentifier_from_material(
            shader_prim, lambda x: x, use_functions=False
        )
        # not MDL?
        shader = UsdShade.Shader(shader_prim)
        if shader and not subid_list and shader.GetShaderId():
            value = shader.GetShaderId()
            if value:
                subid_list = [value]
        return str(subid_list[0]) if subid_list else None

    @usd.handle_exception
    async def _validate_material_shaders(self, shader_subidentifiers: OrderedDict, prim: Usd.Prim) -> bool:
        return await self._get_material_shader_subidentifier(prim) in [
            name for name, _ in shader_subidentifiers.items()
        ]

    @usd.handle_exception
    async def _convert_material(
        self, context_name: str, output_subidentifier: str, input_subidentifier: str, prim: Usd.Prim
    ) -> tuple[bool, str | None, bool]:
        converter = None

        # if there is a OmniGlass, we force the converter
        if input_subidentifier == _SupportedShaderInputs.OMNI_GLASS.value:
            converter = _OmniGlassToAperturePBRConverterBuilder().build(prim, output_subidentifier)
        else:
            # We use name pattern
            # AperturePBR converters
            match output_subidentifier:
                case _SupportedShaderOutputs.APERTURE_PBR_OPACITY.value:
                    # Input Shader
                    match input_subidentifier:
                        case _SupportedShaderInputs.OMNI_PBR.value:
                            converter = _OmniPBRToAperturePBRConverterBuilder().build(prim, output_subidentifier)
                        case _SupportedShaderInputs.OMNI_PBR_OPACITY.value:
                            converter = _OmniPBRToAperturePBRConverterBuilder().build(prim, output_subidentifier)
                        case _SupportedShaderInputs.USD_PREVIEW_SURFACE.value:
                            converter = _USDPreviewSurfaceToAperturePBRConverterBuilder().build(
                                prim, output_subidentifier
                            )
                        case _SupportedShaderInputs.NONE.value:
                            converter = _NoneToAperturePBRConverterBuilder().build(prim, output_subidentifier)
                case _SupportedShaderOutputs.APERTURE_PBR_TRANSLUCENT.value:
                    match input_subidentifier:
                        case _SupportedShaderInputs.OMNI_GLASS.value:
                            converter = _OmniGlassToAperturePBRConverterBuilder().build(prim, output_subidentifier)
                        case _:  # default
                            converter = _NoneToAperturePBRConverterBuilder().build(prim, output_subidentifier)

        if not converter:
            return False, "No supported converter found", False

        return await _MaterialConverterCore.convert(context_name, converter)

    @usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
