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
from typing import List, Optional, Set

from omni.flux.service.shared import BaseServiceModel
from pydantic import Field, field_validator, model_validator
from pydantic_core.core_schema import ValidationInfo

from .enums import LayerType
from .validators import LayerManagerValidators

# ITEM MODELS


class LayerModel(BaseServiceModel):
    """
    Generic model describing a layer.
    """

    layer_id: Path = Field(description="The layer identifier (layer path for non-anonymous layers)")
    layer_type: Optional[LayerType] = Field(default=None, description="The type of layer")
    children: List["LayerModel"] = Field(default=[], description="The immediate sublayers of the layer")


# PATH PARAM MODELS


class OpenProjectPathParamModel(BaseServiceModel):
    """
    Path parameter model for opening a project.
    """

    layer_id: Path = Field(description="The layer identifier (layer path for non-anonymous layers)")

    @field_validator("layer_id", mode="before")
    @classmethod
    def project_path_valid(cls, v):
        return LayerManagerValidators.is_project_layer(v)


class GetLayerPathParamModel(BaseServiceModel):
    """
    Path parameter model for getting a layer.
    """

    layer_id: Path = Field(description="The layer identifier (layer path for non-anonymous layers)")

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model, info: ValidationInfo):
        if not info.context:
            raise ValueError("Context name is required")
        context_name = info.context.get("context_name")
        LayerManagerValidators.layer_is_in_project(instance_model.layer_id, context_name)
        return instance_model


class MoveLayerPathParamModel(BaseServiceModel):
    """
    Path parameter model for moving a layer.
    """

    layer_id: Path = Field(description="The layer identifier (layer path for non-anonymous layers)")

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model, info: ValidationInfo):
        if not info.context:
            raise ValueError("Context name is required")
        context_name = info.context.get("context_name")
        LayerManagerValidators.layer_is_in_project(instance_model.layer_id, context_name)
        LayerManagerValidators.can_move_sublayer(instance_model.layer_id, context_name)
        return instance_model


class DeleteLayerPathParamModel(BaseServiceModel):
    """
    Path parameter model for deleting a layer.
    """

    layer_id: Path = Field(description="The layer identifier (layer path for non-anonymous layers)")

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model, info: ValidationInfo):
        if not info.context:
            raise ValueError("Context name is required")
        context_name = info.context.get("context_name")
        LayerManagerValidators.layer_is_in_project(instance_model.layer_id, context_name)
        LayerManagerValidators.can_delete_layer(instance_model.layer_id, context_name)
        return instance_model


class MuteLayerPathParamModel(BaseServiceModel):
    """
    Path parameter model for muting a layer.
    """

    layer_id: Path = Field(description="The layer identifier (layer path for non-anonymous layers)")

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model, info: ValidationInfo):
        if not info.context:
            raise ValueError("Context name is required")
        context_name = info.context.get("context_name")
        LayerManagerValidators.layer_is_in_project(instance_model.layer_id, context_name)
        LayerManagerValidators.can_mute_layer(instance_model.layer_id, context_name)
        return instance_model


class LockLayerPathParamModel(BaseServiceModel):
    """
    Path parameter model for locking a layer.
    """

    layer_id: Path = Field(description="The layer identifier (layer path for non-anonymous layers)")

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model, info: ValidationInfo):
        if not info.context:
            raise ValueError("Context name is required")
        context_name = info.context.get("context_name")
        LayerManagerValidators.layer_is_in_project(instance_model.layer_id, context_name)
        LayerManagerValidators.can_lock_layer(instance_model.layer_id, context_name)
        return instance_model


class SetEditTargetPathParamModel(BaseServiceModel):
    """
    Path parameter model for setting the edit target layer.
    """

    layer_id: Path = Field(description="The layer identifier (layer path for non-anonymous layers)")

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model, info: ValidationInfo):
        if not info.context:
            raise ValueError("Context name is required")
        context_name = info.context.get("context_name")
        LayerManagerValidators.layer_is_in_project(instance_model.layer_id, context_name)
        LayerManagerValidators.can_set_edit_target_layer(instance_model.layer_id, context_name)
        return instance_model


class SaveLayerPathParamModel(BaseServiceModel):
    """
    Path parameter model for saving a layer.
    """

    layer_id: Path = Field(description="The layer identifier (layer path for non-anonymous layers)")

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model, info: ValidationInfo):
        if not info.context:
            raise ValueError("Context name is required")
        context_name = info.context.get("context_name")
        LayerManagerValidators.layer_is_in_project(instance_model.layer_id, context_name)
        return instance_model


# QUERY MODELS


class GetLayersQueryModel(BaseServiceModel):
    """
    Query model that modifies the behavior when getting layers.
    """

    layer_types: Optional[Set[Optional[LayerType]]] = Field(default=None, description="The type of layer to get")
    layer_count: int = Field(
        default=-1, description="The number of layers to get per `layer_type`. Use -1 to get all the layers."
    )


# RESPONSE MODELS


class LayerResponseModel(BaseServiceModel):
    """
    Response model received when getting a layer.
    """

    layer_id: Path = Field(description="The layer identifier (layer path for non-anonymous layers)")


class LayerStackResponseModel(BaseServiceModel):
    """
    Response model received when getting the layer stack.
    """

    layers: List[LayerModel] = Field(description="The list of layers in the layer stack")


class LayerTypeResponseModel(BaseServiceModel):
    """
    Response model received when getting the layer types.
    """

    layer_types: List[str] = Field(description="The types of layers available")


# REQUEST MODELS


class CreateLayerRequestModel(BaseServiceModel):
    """
    Request model for creating a layer.
    """

    layer_path: Path = Field(description="The path to the layer to create")
    layer_type: Optional[LayerType] = Field(
        default=None, description="If used, will set custom metadata for the layer type"
    )
    set_edit_target: bool = Field(default=False, description="Whether to set the layer as the edit target")
    sublayer_position: int = Field(
        default=-1, description="The position to insert the new layer at. Use -1 to insert at the end."
    )
    parent_layer_id: Optional[Path] = Field(
        default=None,
        description=(
            "Layer identifier (layer path for non-anonymous layers) for the layer to insert the sublayer into. "
            "If none, the root layer will be used"
        ),
    )
    create_or_insert: bool = Field(default=True, description="Whether to create a new layer or insert a sublayer")
    replace_existing: bool = Field(default=False, description="Remove existing layers of type layer_type if set")

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model):
        context_name = instance_model.context_name if hasattr(instance_model, "context_name") else None
        LayerManagerValidators.can_create_layer(instance_model.layer_path, instance_model.create_or_insert)
        LayerManagerValidators.layer_is_in_project(instance_model.parent_layer_id, context_name)
        LayerManagerValidators.can_insert_sublayer(instance_model.parent_layer_id, context_name)
        return instance_model

    @field_validator("sublayer_position", mode="before")
    @classmethod
    def is_valid_index(cls, v):
        return LayerManagerValidators.is_valid_index(v)


class MoveLayerRequestModel(BaseServiceModel):
    """
    Request model for moving a layer.
    """

    current_parent_layer_id: Path = Field(
        description="Layer identifier (layer path for non-anonymous layers) for the layer to move"
    )
    new_parent_layer_id: Optional[Path] = Field(
        default=None,
        description=(
            "Layer identifier (layer path for non-anonymous layers) for the new parent layer. "
            "If none, the layer will be moved to the root layer"
        ),
    )
    layer_index: int = Field(
        default=-1, description="The position to insert the layer at. Use -1 to insert at the end."
    )

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model):
        context_name = instance_model.context_name if hasattr(instance_model, "context_name") else None
        LayerManagerValidators.layer_is_in_project(instance_model.current_parent_layer_id, context_name)
        LayerManagerValidators.layer_is_in_project(instance_model.new_parent_layer_id, context_name)
        LayerManagerValidators.can_insert_sublayer(instance_model.new_parent_layer_id, context_name)
        return instance_model


class DeleteLayerRequestModel(BaseServiceModel):
    """
    Request model for deleting a layer.
    """

    parent_layer_id: Path = Field(
        description=(
            "Layer identifier (layer path for non-anonymous layers) for the parent layer of the layer to delete. "
            "If none, the root layer will be used"
        ),
    )

    @model_validator(mode="after")
    @classmethod
    def root_validators(cls, instance_model):
        context_name = instance_model.context_name if hasattr(instance_model, "context_name") else None
        LayerManagerValidators.layer_is_in_project(instance_model.parent_layer_id, context_name)
        return instance_model


class MuteLayerRequestModel(BaseServiceModel):
    """
    Request model for muting or unmuting a layer.
    """

    value: bool = Field(description="Whether to mute the layer")


class LockLayerRequestModel(BaseServiceModel):
    """
    Request model for locking or unlocking a layer.
    """

    value: bool = Field(description="Whether to lock the layer")
