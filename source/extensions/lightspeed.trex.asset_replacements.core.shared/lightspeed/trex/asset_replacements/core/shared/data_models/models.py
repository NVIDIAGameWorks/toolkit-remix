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

from lightspeed.trex.utils.common.prim_utils import PrimTypes
from omni.flux.asset_importer.core.data_models import TextureTypeNames
from omni.flux.service.shared import BaseServiceModel
from pydantic import root_validator

from .validators import AssetReplacementsValidators

# PATH PARAM MODELS


class SetSelectionPathParamModel(BaseServiceModel):
    asset_paths: list[str]

    @root_validator
    def root_validators(cls, values):  # noqa

        for asset_path in values.get("asset_paths"):
            AssetReplacementsValidators.is_valid_prim(asset_path, values.get("context_name"))
        return values


class PrimInstancesPathParamModel(BaseServiceModel):
    asset_path: str

    @root_validator
    def root_validators(cls, values):  # noqa
        AssetReplacementsValidators.is_valid_prim(values.get("asset_path"), values.get("context_name"))
        AssetReplacementsValidators.is_valid_mesh(values.get("asset_path"))

        return values


class PrimTexturesPathParamModel(BaseServiceModel):
    asset_path: str

    @root_validator
    def root_validators(cls, values):  # noqa
        AssetReplacementsValidators.is_valid_prim(values.get("asset_path"), values.get("context_name"))
        AssetReplacementsValidators.is_valid_material(values.get("asset_path"), values.get("context_name"))

        return values


class PrimReferencePathParamModel(BaseServiceModel):
    asset_path: str

    @root_validator
    def root_validators(cls, values):  # noqa
        AssetReplacementsValidators.is_valid_prim(values.get("asset_path"), values.get("context_name"))
        return values


# QUERY MODELS


class GetPrimsQueryModel(BaseServiceModel):
    asset_hashes: set[str] | None = None
    asset_types: set[PrimTypes] | None = None
    return_selection: bool = False
    filter_session_prims: bool = False
    layer_identifier: Path | None = None
    exists: bool = True

    context_name: str = ""  # This is only used to validate the layer_identifier

    @root_validator
    def root_validators(cls, values):  # noqa
        AssetReplacementsValidators.layer_is_in_project(values.get("layer_identifier"), values.get("context_name"))
        return values


class GetTexturesQueryModel(BaseServiceModel):
    texture_types: set[TextureTypeNames] | None = None


# RESPONSE MODELS


class PrimsResponseModel(BaseServiceModel):
    asset_paths: list[str]


class TexturesResponseModel(BaseServiceModel):
    # Format: [(asset_path, texture_path)]
    textures: list[tuple[str, Path]]


class ReferenceResponseModel(BaseServiceModel):
    # Format: [(asset_path, (ref_path, layer_identifier))]
    reference_paths: list[tuple[str, tuple[Path, Path]]]


class AssetPathResponseModel(BaseServiceModel):
    asset_path: str


# REQUEST MODELS


class AppendReferenceRequestModel(BaseServiceModel):
    asset_file_path: Path
    force: bool = False  # Ignore ingestion validation

    @root_validator
    def root_validators(cls, values):  # noqa
        AssetReplacementsValidators.is_valid_file_path(values.get("asset_file_path"))

        if not values.get("force"):
            AssetReplacementsValidators.is_asset_ingested(values.get("asset_file_path"))

        return values


class ReplaceReferenceRequestModel(AppendReferenceRequestModel):
    # If the existing reference is not provided, the first reference found will be replaced
    existing_asset_file_path: Path | None = None
    existing_asset_layer_id: Path | None = None

    # Extra validation is done in the endpoint since it requires both the path parameter & the body
