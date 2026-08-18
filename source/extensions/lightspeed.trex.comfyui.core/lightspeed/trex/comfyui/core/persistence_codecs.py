"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from omni.flux.job_queue.core.persistence import PersistenceCodec
from omni.flux.job_queue.core.persistence_codec import decode_positional_payload

from .apply_handler import ComfyUIJobApplyHandler
from .enums import IntroducingLayer, RemixType, WorkflowCategory, WorkflowSourceType
from .job import ComfyUIJob
from .keys import type_key
from .models import (
    ComfyUIApplyReceipt,
    ComfyUIApplyTarget,
    ComfyUIWorkflowRequest,
    Workflow,
    WorkflowInput,
    WorkflowOutput,
)
from .preset import Preset
from .resolvers import (
    AllStageTexturesResolver,
    ConstantResolver,
    LayerIdentifierResolver,
    SelectedPrimPathResolver,
    SelectedTextureResolver,
)

__all__ = ("COMFYUI_CODECS",)


# Every codec key is derived from its type's name so none is a hand-written string that can drift.
# The Apply handler keeps its own plugin ``name`` because that is the identity its runtime registry uses.
COMFYUI_CODECS = (
    PersistenceCodec(ComfyUIJobApplyHandler.name, ComfyUIJobApplyHandler),
    PersistenceCodec(type_key(RemixType), RemixType),
    PersistenceCodec(type_key(WorkflowCategory), WorkflowCategory),
    PersistenceCodec(type_key(WorkflowSourceType), WorkflowSourceType),
    PersistenceCodec(type_key(IntroducingLayer), IntroducingLayer),
    PersistenceCodec(
        type_key(ComfyUIApplyReceipt),
        ComfyUIApplyReceipt,
        lambda value: (
            value.original_authored_values,
            value.original_compare_values,
            value.applied_compare_values,
        ),
        lambda payload: decode_positional_payload(ComfyUIApplyReceipt, payload, 3),
    ),
    PersistenceCodec(
        type_key(ComfyUIApplyTarget),
        ComfyUIApplyTarget,
        lambda value: (
            value.context_name,
            value.project_path,
            value.edit_target_layer,
            value.material_path,
            value.texture_targets,
        ),
        lambda payload: decode_positional_payload(ComfyUIApplyTarget, payload, 5),
    ),
    PersistenceCodec(
        type_key(ConstantResolver),
        ConstantResolver,
        lambda value: (value.value, value.value_type),
        lambda payload: decode_positional_payload(ConstantResolver, payload, 2),
    ),
    PersistenceCodec(
        type_key(LayerIdentifierResolver),
        LayerIdentifierResolver,
        lambda _value: (),
        lambda payload: decode_positional_payload(LayerIdentifierResolver, payload, 0),
    ),
    PersistenceCodec(
        type_key(SelectedPrimPathResolver),
        SelectedPrimPathResolver,
        lambda _value: (),
        lambda payload: decode_positional_payload(SelectedPrimPathResolver, payload, 0),
    ),
    PersistenceCodec(
        type_key(SelectedTextureResolver),
        SelectedTextureResolver,
        lambda value: (value.texture_type, value.context_name),
        lambda payload: decode_positional_payload(SelectedTextureResolver, payload, 2),
    ),
    PersistenceCodec(
        type_key(AllStageTexturesResolver),
        AllStageTexturesResolver,
        lambda value: (value.texture_type, value.context_name, value.introducing_layer),
        lambda payload: decode_positional_payload(AllStageTexturesResolver, payload, 3),
    ),
    PersistenceCodec(
        type_key(ComfyUIJob),
        ComfyUIJob,
        lambda value: (
            value.job_id,
            value.name,
            value.skip_reason,
            value.apply_binding,
            value.context_name,
            value.prim_paths,
            value.material_path,
            value.scheme,
            value.host,
            value.port,
        ),
        lambda payload: decode_positional_payload(ComfyUIJob, payload, 10),
    ),
    PersistenceCodec(
        type_key(ComfyUIWorkflowRequest),
        ComfyUIWorkflowRequest,
        lambda value: (
            value.prompt,
            value.input_bindings,
            value.client_id,
            value.timeout,
            value.output_url,
            value.workflow,
        ),
        lambda payload: decode_positional_payload(ComfyUIWorkflowRequest, payload, 6),
    ),
    PersistenceCodec(
        type_key(Preset),
        Preset,
        lambda value: (value.name, value.description, value.inputs),
        lambda payload: decode_positional_payload(Preset, payload, 3),
    ),
    PersistenceCodec(
        type_key(Workflow),
        Workflow,
        lambda value: (
            value.api,
            value.name,
            value.source_type,
            value.category,
            value.inputs,
            value.output_specs,
            value.presets,
            value.active_preset,
            value.group_order,
            value.workflow_defaults,
        ),
        lambda payload: decode_positional_payload(Workflow, payload, 10),
    ),
    PersistenceCodec(
        type_key(WorkflowInput),
        WorkflowInput,
        lambda value: (
            value.port_id,
            value.label,
            value.native_type,
            value.default_value,
            value.value,
            value.order,
            value.remix_type,
            value.group,
            value.tooltip,
        ),
        lambda payload: decode_positional_payload(WorkflowInput, payload, 9),
    ),
    PersistenceCodec(
        type_key(WorkflowOutput),
        WorkflowOutput,
        lambda value: (value.node_id, value.texture_type, value.order),
        lambda payload: decode_positional_payload(WorkflowOutput, payload, 3),
    ),
)
