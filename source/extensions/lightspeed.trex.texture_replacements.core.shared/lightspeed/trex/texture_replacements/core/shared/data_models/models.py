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

from pathlib import Path

from omni.flux.asset_importer.core.data_models import TextureTypeNames
from omni.flux.service.shared import BaseServiceModel
from pydantic import root_validator

from .validators import TextureReplacementsValidators

# PATH PARAM MODELS


class TextureMaterialPathParamModel(BaseServiceModel):
    texture_asset_path: str

    @root_validator()
    def root_validators(cls, values):  # noqa
        TextureReplacementsValidators.is_valid_texture_prim(
            (values.get("texture_asset_path"), None), values.get("context_name")
        )
        return values


class TextureFilePathParamModel(BaseServiceModel):
    texture_file_path: str

    @root_validator()
    def root_validators(cls, values):  # noqa
        TextureReplacementsValidators.is_valid_texture_asset((None, values.get("texture_file_path")), False)
        return values


# QUERY MODELS


class GetTexturesQueryModel(BaseServiceModel):
    asset_hashes: set[str] | None = None
    texture_types: set[TextureTypeNames] | None = None
    return_selection: bool = False
    filter_session_prims: bool = False
    layer_identifier: Path | None = None
    exists: bool = True

    context_name: str = ""  # This is only used to validate the layer_identifier

    @root_validator
    def root_validators(cls, values):  # noqa
        TextureReplacementsValidators.layer_is_in_project(values.get("layer_identifier"), values.get("context_name"))
        return values


# RESPONSE MODELS


class TexturesResponseModel(BaseServiceModel):
    textures: list[tuple[str, Path]]


class PrimsResponseModel(BaseServiceModel):
    asset_paths: list[str]


class TextureTypesResponseModel(BaseServiceModel):
    texture_types: list[str]


# REQUEST MODELS


class ReplaceTexturesRequestModel(BaseServiceModel):
    force: bool = False  # Whether to replace a non-ingested asset or fail the validation instead
    textures: list[tuple[str, Path]]

    @root_validator
    def root_validators(cls, values):  # noqa
        for texture_entry in values.get("textures"):
            TextureReplacementsValidators.is_valid_texture_prim(texture_entry, values.get("context_name"))
            TextureReplacementsValidators.is_valid_texture_asset(texture_entry, values.get("force"))
        return values
