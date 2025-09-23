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

import carb
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl


class SupportedShaderInputs(Enum):
    OMNI_PBR = "OmniPBR"
    OMNI_PBR_OPACITY = "OmniPBR_Opacity"
    OMNI_GLASS = "OmniGlass"
    USD_PREVIEW_SURFACE = "UsdPreviewSurface"
    NONE = None


class SupportedShaderOutputs(Enum):
    APERTURE_PBR_OPACITY = "AperturePBR_Opacity"
    APERTURE_PBR_TRANSLUCENT = "AperturePBR_Translucent"


class MaterialConverterUtils:
    MATERIAL_LIBRARY_SETTING_PATH = "/renderer/mdl/searchPaths/templates"

    @staticmethod
    def get_material_library_shader_urls() -> list[_OmniUrl]:
        shader_urls = []
        lib_paths = carb.tokens.get_tokens_interface().resolve(
            carb.settings.get_settings().get(MaterialConverterUtils.MATERIAL_LIBRARY_SETTING_PATH)
        )
        if not lib_paths:
            return shader_urls
        if "${" in lib_paths:
            carb.log_warn(
                f"Not all tokens were resolved in "
                f"'{MaterialConverterUtils.MATERIAL_LIBRARY_SETTING_PATH}' setting. "
                f"Result: {lib_paths}"
            )

        for lib_path in lib_paths.split(";"):
            shader_urls.extend([file for file in _OmniUrl(lib_path).iterdir() if file.suffix == ".mdl"])
        return shader_urls
