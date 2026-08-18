"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = [
    "NATIVE_TYPE_TO_USD_VALUE_TYPE",
    "OUTPUT_TEXTURE_TYPE_MAP",
    "TYPE_MAP",
]

import pathlib

from omni.flux.asset_importer.core.data_models import TextureTypes
from pxr import Sdf


NATIVE_TYPE_TO_USD_VALUE_TYPE: dict[type, Sdf.ValueTypeName] = {
    bool: Sdf.ValueTypeNames.Bool,
    int: Sdf.ValueTypeNames.Int,
    float: Sdf.ValueTypeNames.Float,
    str: Sdf.ValueTypeNames.String,
    pathlib.Path: Sdf.ValueTypeNames.Asset,
}
"""Canonical workflow-native types and their corresponding USD value types."""


OUTPUT_TEXTURE_TYPE_MAP: dict[str, TextureTypes] = {
    "albedo": TextureTypes.DIFFUSE,
    "roughness": TextureTypes.ROUGHNESS,
    "anisotropy": TextureTypes.ANISOTROPY,
    "metallic": TextureTypes.METALLIC,
    "emissive_mask": TextureTypes.EMISSIVE,
    "normal_ogl": TextureTypes.NORMAL_OGL,
    "normal_dx": TextureTypes.NORMAL_DX,
    "normal_oth": TextureTypes.NORMAL_OTH,
    "height": TextureTypes.HEIGHT,
    "transmittance": TextureTypes.TRANSMITTANCE,
    "measurement_distance": TextureTypes.MEASUREMENT_DISTANCE,
    "single_scattering": TextureTypes.SINGLE_SCATTERING,
    "other": TextureTypes.OTHER,
}
"""Canonical ComfyUI output names and their asset-pipeline texture types."""

# ComfyUI type string to Python type.
TYPE_MAP: dict[str, type] = {
    "str": str,
    "STRING": str,
    "bool": bool,
    "BOOLEAN": bool,
    "int": int,
    "INT": int,
    "float": float,
    "FLOAT": float,
    "Path": pathlib.Path,
}
