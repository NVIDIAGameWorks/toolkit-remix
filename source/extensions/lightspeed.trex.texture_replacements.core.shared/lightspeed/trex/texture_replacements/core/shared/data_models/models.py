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
from pydantic import Field, model_validator
from pydantic_core.core_schema import ValidationInfo

from .validators import TextureReplacementsValidators

# PATH PARAM MODELS


class TextureMaterialPathParamModel(BaseServiceModel):
    """
    Path parameter model for getting the textures of a given material prim.
    """

    texture_prim_path: str = Field(description="The shader input path where the texture is set")

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model, info: ValidationInfo):
        if not info.context:
            raise ValueError("Context name is required")
        context_name = info.context.get("context_name")
        TextureReplacementsValidators.is_valid_texture_prim((instance_model.texture_prim_path, None), context_name)
        return instance_model


# QUERY MODELS


class GetTexturesQueryModel(BaseServiceModel):
    """
    Query parameters model for modifying the behavior when getting the textures of a given material prim.
    """

    prim_hashes: set[str] | None = Field(default=None, description="A set of prim hashes to filter the results by")
    texture_types: set[TextureTypeNames] | None = Field(
        default=None, description="A set of texture types to filter the results by"
    )
    return_selection: bool = Field(
        default=False, description="Whether to return only prims selected in the viewport or all prims"
    )
    filter_session_prims: bool = Field(
        default=False, description="Whether to filter out the prims that exist on the session layer or not"
    )
    layer_identifier: Path | None = Field(
        default=None, description="The layer identifier to filter the results by. Use in conjunction with `exists`"
    )
    exists: bool = Field(
        default=True, description="Whether to filter out the prims that exist or not on `layer_identifier`"
    )

    context_name: str = ""  # This is only used to validate the layer_identifier

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model):
        TextureReplacementsValidators.layer_is_in_project(instance_model.layer_identifier, instance_model.context_name)
        return instance_model


# RESPONSE MODELS


class TexturesResponseModel(BaseServiceModel):
    """
    Response model received when fetching the textures of a given material prim.
    """

    textures: list[tuple[str, Path]] = Field(
        description="A list of prim paths (shader input paths) and their corresponding texture paths"
    )


class PrimPathsResponseModel(BaseServiceModel):
    """
    Response model received when fetching prim paths in the current stage.
    """

    prim_paths: list[str] = Field(description="A list of prim paths")


class TextureTypesResponseModel(BaseServiceModel):
    """
    Response model received when fetching the available texture types.
    """

    texture_types: list[str] = Field(description="A list of texture types")


# REQUEST MODELS


class ReplaceTexturesRequestModel(BaseServiceModel):
    """
    Request body model for replacing the textures of a given material prim.
    """

    force: bool = Field(
        default=False, description="Whether to replace a non-ingested asset or fail the validation instead"
    )
    textures: list[tuple[str, Path]] = Field(
        description="A list of prim paths (shader input paths) and their corresponding texture paths"
    )

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model):
        for texture_entry in instance_model.textures:
            TextureReplacementsValidators.is_valid_texture_prim(texture_entry, instance_model.context_name)
            TextureReplacementsValidators.is_valid_texture_asset(texture_entry, instance_model.force)
        return instance_model
