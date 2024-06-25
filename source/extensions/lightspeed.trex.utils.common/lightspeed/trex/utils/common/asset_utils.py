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

__all__ = [
    "get_texture_type_input_name",
    "is_asset_ingested",
    "is_mesh_from_capture",
    "is_texture_from_capture",
]

from pathlib import Path

from lightspeed.common import constants
from omni.flux.asset_importer.core.data_models import (
    TEXTURE_TYPE_CONVERTED_SUFFIX_MAP,
    TEXTURE_TYPE_INPUT_MAP,
    TextureTypes,
)
from omni.flux.utils.common import path_utils
from omni.flux.validator.factory import BASE_HASH_KEY, VALIDATION_PASSED


def get_texture_type_input_name(texture_type: TextureTypes) -> str | None:
    return TEXTURE_TYPE_INPUT_MAP.get(texture_type, None)


def get_ingested_texture_type(texture_file_path: str | Path) -> TextureTypes | None:
    texture_path = Path(str(texture_file_path))
    suffixes = texture_path.suffixes

    if not suffixes:
        return None

    # Expect .a.rtex.dds -> ['.a', '.rtex', '.dds'] -> Only keep 'a'
    return TEXTURE_TYPE_CONVERTED_SUFFIX_MAP.get(suffixes[0][1:], None)


def is_asset_ingested(asset_path: str | Path) -> bool:
    path = str(asset_path)

    # Invalid paths are ignored
    if not path_utils.is_file_path_valid(path, log_error=False):
        return True

    # Ignore assets from captures
    if is_mesh_from_capture(path) or is_texture_from_capture(path):
        return True

    if not bool(
        path_utils.hash_match_metadata(path, key=BASE_HASH_KEY) and path_utils.read_metadata(path, VALIDATION_PASSED)
    ):
        return False

    return True


def is_mesh_from_capture(asset_path: str) -> bool:
    path = Path(asset_path)
    return (
        bool(constants.CAPTURE_FOLDER in path.parts or constants.REMIX_CAPTURE_FOLDER in path.parts)
        and constants.MESHES_FOLDER in path.parts
    )


def is_texture_from_capture(texture_path: str) -> bool:
    path = Path(texture_path)
    return (
        bool(constants.CAPTURE_FOLDER in path.parts or constants.REMIX_CAPTURE_FOLDER in path.parts)
        and constants.TEXTURES_FOLDER in path.parts
    )
