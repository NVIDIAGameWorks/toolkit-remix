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
from pydantic import root_validator, validator

from .enums import LayerType
from .validators import LayerManagerValidators

# ITEM MODELS


class LayerModel(BaseServiceModel):
    layer_id: Path
    layer_type: Optional[LayerType] = None
    children: List["LayerModel"] = []


# PATH PARAM MODELS


class OpenProjectPathParamModel(BaseServiceModel):
    layer_id: Path

    @validator("layer_id", allow_reuse=True)
    def project_path_valid(cls, v):  # noqa
        return LayerManagerValidators.is_project_layer(v)


class GetLayerPathParamModel(BaseServiceModel):
    layer_id: Path

    @root_validator
    def root_validators(cls, values):  # noqa
        LayerManagerValidators.layer_is_in_project(values.get("layer_id"), values.get("context_name"))
        return values


class MoveLayerPathParamModel(BaseServiceModel):
    layer_id: Path

    @root_validator
    def root_validators(cls, values):  # noqa
        LayerManagerValidators.layer_is_in_project(values.get("layer_id"), values.get("context_name"))
        LayerManagerValidators.can_move_sublayer(values.get("layer_id"), values.get("context_name"))
        return values


class DeleteLayerPathParamModel(BaseServiceModel):
    layer_id: Path

    @root_validator
    def root_validators(cls, values):  # noqa
        LayerManagerValidators.layer_is_in_project(values.get("layer_id"), values.get("context_name"))
        LayerManagerValidators.can_delete_layer(values.get("layer_id"), values.get("context_name"))
        return values


class MuteLayerPathParamModel(BaseServiceModel):
    layer_id: Path

    @root_validator
    def root_validators(cls, values):  # noqa
        LayerManagerValidators.layer_is_in_project(values.get("layer_id"), values.get("context_name"))
        LayerManagerValidators.can_mute_layer(values.get("layer_id"), values.get("context_name"))
        return values


class LockLayerPathParamModel(BaseServiceModel):
    layer_id: Path

    @root_validator
    def root_validators(cls, values):  # noqa
        LayerManagerValidators.layer_is_in_project(values.get("layer_id"), values.get("context_name"))
        LayerManagerValidators.can_lock_layer(values.get("layer_id"), values.get("context_name"))
        return values


class SetEditTargetPathParamModel(BaseServiceModel):
    layer_id: Path

    @root_validator
    def root_validators(cls, values):  # noqa
        LayerManagerValidators.layer_is_in_project(values.get("layer_id"), values.get("context_name"))
        LayerManagerValidators.can_set_edit_target_layer(values.get("layer_id"), values.get("context_name"))
        return values


class SaveLayerPathParamModel(BaseServiceModel):
    layer_id: Path

    @root_validator
    def root_validators(cls, values):  # noqa
        LayerManagerValidators.layer_is_in_project(values.get("layer_id"), values.get("context_name"))
        return values


# QUERY MODELS


class GetLayersQueryModel(BaseServiceModel):
    layer_types: Optional[Set[Optional[LayerType]]] = None
    layer_count: int = -1


# RESPONSE MODELS


class LayerResponseModel(BaseServiceModel):
    layer_id: Path


class LayerStackResponseModel(BaseServiceModel):
    layers: List[LayerModel]


class LayerTypeResponseModel(BaseServiceModel):
    layer_types: List[str]


# REQUEST MODELS


class CreateLayerRequestModel(BaseServiceModel):
    layer_path: Path
    layer_type: Optional[LayerType] = None  # If used, will set custom metadata for layer type
    set_edit_target: bool = False
    sublayer_position: int = -1  # Insert at the end by default
    parent_layer_id: Optional[Path] = None  # If none, the root layer will be used
    create_or_insert: bool = True
    replace_existing: bool = False  # Remove existing layers of type layer_type if set

    @root_validator
    def root_validators(cls, values):  # noqa
        LayerManagerValidators.can_create_layer(values.get("layer_path"), values.get("create_or_insert", True))
        LayerManagerValidators.layer_is_in_project(values.get("parent_layer_id"), values.get("context_name"))
        LayerManagerValidators.can_insert_sublayer(values.get("parent_layer_id"), values.get("context_name"))
        return values

    @validator("sublayer_position", allow_reuse=True)
    def is_valid_index(cls, v):  # noqa
        return LayerManagerValidators.is_valid_index(v)


class MoveLayerRequestModel(BaseServiceModel):
    current_parent_layer_id: Path
    new_parent_layer_id: Optional[Path] = None
    layer_index: int = -1  # Insert at the end by default

    @root_validator
    def root_validators(cls, values):  # noqa
        LayerManagerValidators.layer_is_in_project(values.get("current_parent_layer_id"), values.get("context_name"))
        LayerManagerValidators.layer_is_in_project(values.get("new_parent_layer_id"), values.get("context_name"))
        LayerManagerValidators.can_insert_sublayer(values.get("new_parent_layer_id"), values.get("context_name"))
        return values


class DeleteLayerRequestModel(BaseServiceModel):
    parent_layer_id: Path

    @root_validator
    def root_validators(cls, values):  # noqa
        LayerManagerValidators.layer_is_in_project(values.get("parent_layer_id"), values.get("context_name"))
        return values


class MuteLayerRequestModel(BaseServiceModel):
    value: bool


class LockLayerRequestModel(BaseServiceModel):
    value: bool
