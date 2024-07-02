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

from .enums import TextureTypes

SUPPORTED_ASSET_EXTENSIONS = [
    ".usda",
    ".usd",
    ".usdc",
    ".fbx",
    ".obj",
    ".gltf",
    ".lxo",
]
"""
Taken from `omni.kit.tool.asset_importer`
"""


SUPPORTED_TEXTURE_EXTENSIONS = [
    ".dds",
    ".bmp",
    ".gif",
    ".hdr",
    ".jpg",
    ".jpeg",
    ".pgm",
    ".pic",
    ".png",
    ".ppm",
    ".psd",
    ".tga",
]
"""
Taken from `nvidia-texture-tools-exporter`'s README
"""


TEXTURE_TYPE_INPUT_MAP = {
    TextureTypes.DIFFUSE: "inputs:diffuse_texture",
    TextureTypes.ROUGHNESS: "inputs:reflectionroughness_texture",
    TextureTypes.ANISOTROPY: "inputs:anisotropy_texture",
    TextureTypes.METALLIC: "inputs:metallic_texture",
    TextureTypes.EMISSIVE: "inputs:emissive_mask_texture",
    TextureTypes.NORMAL_OGL: "inputs:normalmap_texture",
    TextureTypes.NORMAL_DX: "inputs:normalmap_texture",
    TextureTypes.NORMAL_OTH: "inputs:normalmap_texture",
    TextureTypes.HEIGHT: "inputs:height_texture",
    TextureTypes.TRANSMITTANCE: "inputs:subsurface_transmittance_texture",
    TextureTypes.MEASUREMENT_DISTANCE: "inputs:subsurface_thickness_texture",
    TextureTypes.SINGLE_SCATTERING: "inputs:subsurface_single_scattering_texture",
    TextureTypes.OTHER: "inputs:diffuse_texture",
}
"""
Map between texture types and shader input attribute names. Based on the AperturePBR MDL input names.
"""


TEXTURE_TYPE_REGEX_MAP = {
    TextureTypes.DIFFUSE: r"(?:diff(?:use)?|albedo|color)",
    TextureTypes.ROUGHNESS: r"(?:rough(?:ness)?)",
    TextureTypes.ANISOTROPY: None,
    TextureTypes.METALLIC: r"(?:metal(?:lic|ness)?)",
    TextureTypes.EMISSIVE: r"(?:emissive|emission)",
    # Will match any of the following:
    #   - `normals` (`nrm`, `norm`, etc.) only when `gl`, `ogl`, `dx`, or `octahedral` (`oth`, `octa`, etc.)
    #      are not found in the string
    #       - This is to find textures such as `T_Name_Normals.png` -> OGL will be used to match as default type
    #   - `gl` when `ogl` is not found in the string
    #       - Must look for `gl` only when `ogl` is not found, or we only match `gl` and get the wrong prefixes
    #   - `ogl`
    TextureTypes.NORMAL_OGL: r"(?:(?!.*(?:o?gl|dx|oc?ta?h?e?d?r?a?l?))\b.*(no?rma?l?s?).*\b|(?:^(?!.*ogl).*(gl))|ogl)",
    TextureTypes.NORMAL_DX: r"(?:dx)",
    TextureTypes.NORMAL_OTH: r"(?:oc?ta?h?e?d?r?a?l?)",
    TextureTypes.HEIGHT: r"(?:height|bump|depth)",
    TextureTypes.TRANSMITTANCE: None,
    TextureTypes.MEASUREMENT_DISTANCE: None,
    TextureTypes.SINGLE_SCATTERING: None,
    TextureTypes.OTHER: "(?:other)",
}
"""
Map between texture types and regex patterns used to identify the texture type in a file name.
"""


TEXTURE_TYPE_CONVERTED_SUFFIX_MAP = {
    "a": TextureTypes.DIFFUSE,
    "r": TextureTypes.ROUGHNESS,
    "m": TextureTypes.METALLIC,
    "e": TextureTypes.EMISSIVE,
    "n": TextureTypes.NORMAL_OGL,  # All normal types share the same suffix.
    "h": TextureTypes.HEIGHT,
    "tr": TextureTypes.TRANSMITTANCE,
}
"""
**WARNING**: All normal types share the same suffix but `NORMAL_GL` will be returned as the value here.
In reality the texture type could be one of any of the following: `NORMAL_GL`, `NORMAL_DX`, `NORMAL_OTH`

Map between converted texture suffixes and their texture types.
"""

PREFIX_TEXTURE_NO_PREFIX = "Unknown_prefix"
