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
from pydantic import Field, model_validator
from pydantic_core.core_schema import ValidationInfo

from .enums import AssetType
from .validators import AssetReplacementsValidators

# PATH PARAM MODELS


class SetSelectionPathParamModel(BaseServiceModel):
    """
    Path parameter model for setting the selection in the viewport.
    """

    prim_paths: list[str] = Field(description="A list of prim paths to select in the viewport")

    @model_validator(mode="after")
    @classmethod
    def ensure_prim_paths_are_valid(cls, instance_model, info: ValidationInfo):
        if not info.context:
            raise ValueError("Context name is required")
        context_name = info.context.get("context_name")
        for prim_path in instance_model.prim_paths:
            AssetReplacementsValidators.is_valid_prim(prim_path, context_name)
        return instance_model


class PrimInstancesPathParamModel(BaseServiceModel):
    """
    Path parameter model for getting the instances of a given prim.
    """

    prim_path: str = Field(description="The prim path to get instances for")

    @model_validator(mode="after")
    @classmethod
    def ensure_prim_path_is_valid(cls, instance_model, info: ValidationInfo):
        if not info.context:
            raise ValueError("Context name is required")
        context_name = info.context.get("context_name")
        AssetReplacementsValidators.is_valid_prim(instance_model.prim_path, context_name)
        AssetReplacementsValidators.is_valid_mesh(instance_model.prim_path)
        return instance_model


class PrimTexturesPathParamModel(BaseServiceModel):
    """
    Path parameter model for getting the textures of a given material prim.
    """

    prim_path: str = Field(description="The prim path to get textures for")

    @model_validator(mode="after")
    @classmethod
    def ensure_prim_path_is_valid(cls, instance_model, info: ValidationInfo):
        if not info.context:
            raise ValueError("Context name is required")
        context_name = info.context.get("context_name")
        AssetReplacementsValidators.is_valid_prim(instance_model.prim_path, context_name)
        AssetReplacementsValidators.is_valid_material(instance_model.prim_path, context_name)
        return instance_model


class PrimReferencePathParamModel(BaseServiceModel):
    """
    Path parameter model for getting the references of a given model prim.
    """

    prim_path: str = Field(description="The prim path to get references for")

    @model_validator(mode="after")
    @classmethod
    def ensure_prim_path_is_valid(cls, instance_model, info: ValidationInfo):
        if not info.context:
            raise ValueError("Context name is required")
        context_name = info.context.get("context_name")
        AssetReplacementsValidators.is_valid_prim(instance_model.prim_path, context_name)
        return instance_model


# QUERY MODELS


class GetPrimsQueryModel(BaseServiceModel):
    """
    Query parameters model for modifying the behavior when getting the prims in the current stage.
    """

    prim_hashes: set[str] | None = Field(default=None, description="A set of prim hashes to filter the results by")
    prim_types: set[PrimTypes] | None = Field(default=None, description="A set of prim types to filter the results by")
    return_selection: bool = Field(
        default=False, description="Whether to return only prims selected in the viewport or all prims"
    )
    filter_session_prims: bool = Field(default=False, description="Whether to filter out session prims or keep them")
    exists: bool = Field(default=True, description="Whether to look for prims that exists or not on `layer_identifier`")
    layer_identifier: Path | None = Field(
        default=None, description="The layer to filter the results by. Use in conjunction with `exists`"
    )

    context_name: str = ""  # This is only used to validate the layer_identifier

    @model_validator(mode="after")
    @classmethod
    def ensure_layer_is_in_project(cls, instance_model):
        AssetReplacementsValidators.layer_is_in_project(instance_model.layer_identifier, instance_model.context_name)
        return instance_model


class GetTexturesQueryModel(BaseServiceModel):
    """
    Query parameters model for modifying the behavior when getting the textures of a given material prim.
    """

    texture_types: set[TextureTypeNames] | None = Field(
        default=None, description="A set of texture types to filter the results by"
    )


class GetAvailableAssetsQueryModel(BaseServiceModel):
    """
    Query parameters model for modifying the behavior when getting the available assets.
    """

    asset_type: AssetType | None = Field(default=None, description="A type of asset to filter the results by")


# RESPONSE MODELS


class DirectoryResponseModel(BaseServiceModel):
    """
    Response model received when fetching the default output directories for ingestion tasks.
    """

    directory_path: str = Field(description="Path pointing to a directory")


class FilePathsResponseModel(BaseServiceModel):
    """
    Response model received when fetching available files for ingestion tasks.
    """

    file_paths: list[str] = Field(description="List of paths pointing to files")


class PrimPathsResponseModel(BaseServiceModel):
    """
    Response model received when fetching prim paths in the current stage.
    """

    prim_paths: list[str] = Field(description="A list of prim paths")


class TexturesResponseModel(BaseServiceModel):
    """
    Response model received when fetching the textures of a given material prim.
    """

    # Format: [(prim_path, texture_path)]
    textures: list[tuple[str, Path]] = Field(
        ..., description="A list of prim paths (shader input paths) and their corresponding texture paths"
    )


class ReferenceResponseModel(BaseServiceModel):
    """
    Response model received when fetching the reference paths of a given model prim.
    """

    # Format: [(prim_path, (ref_path, layer_identifier))]
    reference_paths: list[tuple[str, tuple[Path, Path]]] = Field(
        ...,
        description=(
            "A list of prim paths and their corresponding reference relative paths and layer identifiers. "
            "Combine the reference path's relative path with the layer identifier to get the absolute reference path."
        ),
    )


# REQUEST MODELS


class AppendReferenceRequestModel(BaseServiceModel):
    """
    Request body model for appending a reference to a given model prim.
    """

    asset_file_path: Path = Field(description="The path to the asset to use as a reference")
    force: bool = Field(
        default=False, description="Whether to force use the reference or validate the ingestion status"
    )

    @model_validator(mode="after")
    @classmethod
    def ensure_reference_asset_is_valid(cls, instance_model):
        AssetReplacementsValidators.is_valid_file_path(instance_model.asset_file_path)

        if not instance_model.force:
            AssetReplacementsValidators.is_asset_ingested(instance_model.asset_file_path)

        return instance_model


class ReplaceReferenceRequestModel(AppendReferenceRequestModel):
    """
    Request body model for replacing a reference of a given model prim.

    If the existing reference is not provided, the first reference found will be replaced
    """

    # Extra validation is done in the endpoint since it requires both the path parameter & the body
    existing_asset_file_path: Path | None = Field(
        default=None, description="The relative path of the asset reference to replace"
    )
    existing_asset_layer_id: Path | None = Field(
        default=None, description="The layer identifier where the existing reference is located"
    )
