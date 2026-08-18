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

from dataclasses import dataclass
from pathlib import Path

from omni.flux.asset_importer.core.data_models import TextureTypeNames
from omni.flux.service.shared import BaseServiceModel
from pydantic import Field, model_validator
from pydantic_core.core_schema import ValidationInfo
from pxr import Sdf

from .validators import TextureReplacementsValidators

__all__ = [
    "GetTexturesQueryModel",
    "PrimPathsResponseModel",
    "ReplaceTexturesRequestModel",
    "TextureMaterialPathParamModel",
    "TextureReplacement",
    "TextureTypesResponseModel",
    "TexturesResponseModel",
]


@dataclass(slots=True)
class TextureReplacement:
    """Describe one strongly typed USD texture-property mutation."""

    property_path: Sdf.Path
    value: str | None
    value_type: Sdf.ValueTypeName | None


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
        default=False,
        description="Whether to bypass source checks after confirming the exact current target-layer values",
    )
    textures: list[tuple[str, Path]] = Field(
        description="A list of prim paths (shader input paths) and their corresponding texture paths"
    )
    expected_current_textures: list[tuple[str, str | None]] | None = Field(
        default=None,
        description="Exact current target-layer values required when force is true",
    )

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model):
        """Validate one texture replacement request as an atomic batch.

        Args:
            instance_model: Parsed request whose target paths and values are validated.

        Returns:
            The unchanged request after every target and asset passes validation.

        Raises:
            ValueError: If force confirmation, target uniqueness, target sets, USD inputs, or assets are invalid.
            RuntimeError: If the current stage or shader registry cannot be read.
        """
        if instance_model.force and instance_model.expected_current_textures is None:
            raise ValueError("Forced texture replacement requires expected current values")
        if not instance_model.force and instance_model.expected_current_textures is not None:
            raise ValueError("Expected current values are only valid for forced texture replacement")

        texture_paths = [path for path, _ in instance_model.textures]
        expected_paths = [path for path, _ in instance_model.expected_current_textures or []]
        if len(texture_paths) != len(set(texture_paths)):
            raise ValueError("Texture replacement target paths must be unique")
        if len(expected_paths) != len(set(expected_paths)):
            raise ValueError("Expected texture target paths must be unique")
        if instance_model.expected_current_textures is not None and set(expected_paths) != set(texture_paths):
            raise ValueError("Expected texture target paths must match the replacement batch")

        TextureReplacementsValidators.get_texture_input_types(texture_paths, instance_model.context_name)
        for texture_batch, force in (
            (instance_model.textures, instance_model.force),
            (instance_model.expected_current_textures or [], True),
        ):
            for texture_entry in texture_batch:
                TextureReplacementsValidators.is_valid_texture_asset(texture_entry, force)
        return instance_model
