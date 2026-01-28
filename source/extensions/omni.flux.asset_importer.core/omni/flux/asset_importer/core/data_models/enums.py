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

from enum import Enum
from typing import Any, Callable

from pydantic_core import core_schema


class UsdExtensions(Enum):
    USD = "usd"
    USDA = "usda"
    USDC = "usdc"


class TextureTypes(Enum):
    DIFFUSE = "Albedo"
    ROUGHNESS = "Roughness"
    ANISOTROPY = "Anisotropy"
    METALLIC = "Metallic"
    EMISSIVE = "Emissive Mask"
    NORMAL_OGL = "Normal - OpenGL"
    NORMAL_DX = "Normal - DirectX"
    NORMAL_OTH = "Normal - Octahedral"
    HEIGHT = "Height"
    TRANSMITTANCE = "Transmittance"
    MEASUREMENT_DISTANCE = "Measurement Distance"
    SINGLE_SCATTERING = "Single Scattering"
    OTHER = "Other"

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: Callable[[Any], core_schema.CoreSchema]
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.no_info_plain_validator_function(cls._validate_by_name),
            serialization=core_schema.to_string_ser_schema(),
        )

    @classmethod
    def _validate_by_name(cls, v: Any) -> str:
        enum_names = cls.__members__.keys()
        if v not in enum_names:
            raise ValueError(f"Invalid value selected ({v}). Valid values are: {', '.join(enum_names)}")
        return v


class TextureTypeNames(Enum):
    DIFFUSE = TextureTypes.DIFFUSE.name
    ROUGHNESS = TextureTypes.ROUGHNESS.name
    ANISOTROPY = TextureTypes.ANISOTROPY.name
    METALLIC = TextureTypes.METALLIC.name
    EMISSIVE = TextureTypes.EMISSIVE.name
    NORMAL_OGL = TextureTypes.NORMAL_OGL.name
    NORMAL_DX = TextureTypes.NORMAL_DX.name
    NORMAL_OTH = TextureTypes.NORMAL_OTH.name
    HEIGHT = TextureTypes.HEIGHT.name
    TRANSMITTANCE = TextureTypes.TRANSMITTANCE.name
    MEASUREMENT_DISTANCE = TextureTypes.MEASUREMENT_DISTANCE.name
    SINGLE_SCATTERING = TextureTypes.SINGLE_SCATTERING.name
    OTHER = TextureTypes.OTHER.name
