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

from enum import Enum as _Enum

from .base.converter_builder_base import ConverterBuilderBase
from .impl.gltf_to_aperture_pbr import GltfToAperturePBRConverterBuilder

from .impl.none_to_aperture_pbr import NoneToAperturePBRConverterBuilder as _NoneToAperturePBRConverterBuilder
from .impl.omni_glass_to_aperture_pbr import (
    OmniGlassToAperturePBRConverterBuilder as _OmniGlassToAperturePBRConverterBuilder,
)
from .impl.omni_pbr_to_aperture_pbr import OmniPBRToAperturePBRConverterBuilder as _OmniPBRToAperturePBRConverterBuilder
from .impl.usd_preview_surface_to_aperture_pbr import (
    USDPreviewSurfaceToAperturePBRConverterBuilder as _USDPreviewSurfaceToAperturePBRConverterBuilder,
)
from .utils import SupportedShaderInputs as _SupportedShaderInputs


__all__ = ["Converters", "get_converter_builder"]


class Converters(_Enum):
    GLTF_TO_APERTURE_PBRCONVERTER_BUILDER = (GltfToAperturePBRConverterBuilder, _SupportedShaderInputs.GLTF)
    NONE_TO_APERTURE_PBRCONVERTER_BUILDER = (_NoneToAperturePBRConverterBuilder, _SupportedShaderInputs.NONE)
    OMNI_GLASS_TO_APERTURE_PBRCONVERTER_BUILDER = (
        _OmniGlassToAperturePBRConverterBuilder,
        _SupportedShaderInputs.OMNI_GLASS,
    )
    OMNI_PBR_TO_APERTURE_PBRCONVERTER_BUILDER = (_OmniPBRToAperturePBRConverterBuilder, _SupportedShaderInputs.OMNI_PBR)
    OMNI_PBR_OPACITY_TO_APERTURE_PBRCONVERTER_BUILDER = (
        _OmniPBRToAperturePBRConverterBuilder,
        _SupportedShaderInputs.OMNI_PBR_OPACITY,
    )
    USD_PREVIEW_SURFACE_TO_APERTURE_PBRCONVERTER_BUILDER = (
        _USDPreviewSurfaceToAperturePBRConverterBuilder,
        _SupportedShaderInputs.USD_PREVIEW_SURFACE,
    )


_CONVERTER_BUILDERS = {
    shader_input.value: builder for builder, shader_input in (converter.value for converter in Converters)
}


def get_converter_builder(input_subidentifier: str | None) -> ConverterBuilderBase | None:
    """Create the registered builder for an input shader identifier."""
    builder = _CONVERTER_BUILDERS.get(input_subidentifier)
    return builder() if builder else None
