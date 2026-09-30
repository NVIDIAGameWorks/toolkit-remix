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

from lightspeed.trex.asset_pipeline.core.metadata import MetadataApplyReceipt
from omni.flux.job_queue.core.persistence import PersistenceCodec
from omni.flux.job_queue.core.persistence_codec import decode_positional_payload
from pxr import Sdf

from .apply_handler import ComfyUIAssetApplyHandler, ComfyUIJobApplyHandler, ComfyUITextureApplyHandler
from .enums import (
    IntroducingLayer,
    MeshReferenceSelection,
    OutputApplyBehavior,
    RemixType,
    WorkflowCategory,
    WorkflowSourceType,
    WorkflowType,
)
from .job import ComfyUIAssetJob, ComfyUIJob
from .keys import type_key
from .models import (
    ComfyUIApplyReceipt,
    ComfyUIApplyTarget,
    ComfyUIAssetApplyTarget,
    ComfyUIFileResult,
    ComfyUIInputBinding,
    ComfyUIWorkflowRequest,
    ReferenceTarget,
    Workflow,
    WorkflowInput,
    WorkflowOutput,
)
from .preset import Preset
from .resolvers import (
    AllStageMeshesResolver,
    AllStageTexturesResolver,
    ConstantResolver,
    LayerIdentifierResolver,
    SelectedMeshResolver,
    SelectedPrimPathResolver,
    SelectedTextureResolver,
)

__all__ = ("COMFYUI_CODECS",)


def _decode_comfyui_apply_receipt(payload: object) -> ComfyUIApplyReceipt:
    """Decode current receipts and released receipts without metadata."""
    if type(payload) is tuple and len(payload) == 3:
        payload = (*payload, MetadataApplyReceipt(prior_meta=()))
    return decode_positional_payload(ComfyUIApplyReceipt, payload, 4)


def _decode_workflow_request(payload: object) -> ComfyUIWorkflowRequest:
    """Decode current requests and released texture-source pairs."""
    if type(payload) is tuple and len(payload) == 6 and type(payload[1]) is tuple:
        bindings = tuple(
            ComfyUIInputBinding(binding[0], RemixType.TEXTURE_FILE_PATH, binding[1])
            if type(binding) is tuple and len(binding) == 2
            else binding
            for binding in payload[1]
        )
        payload = (payload[0], bindings, *payload[2:])
    return decode_positional_payload(ComfyUIWorkflowRequest, payload, 6)


def _decode_workflow_output(payload: object) -> WorkflowOutput:
    """Decode current outputs and released outputs that stored only texture identity, no name, or no group.

    A released output was always a texture that Apply replaced, so those two values are implied.
    """
    if type(payload) is tuple and len(payload) == 3:
        node_id, texture_type, order = payload
        payload = (node_id, RemixType.TEXTURE_FILE_PATH, order, texture_type, OutputApplyBehavior.REPLACE)
    if type(payload) is tuple and 5 <= len(payload) < 7:
        payload = (*payload, *(("",) * (7 - len(payload))))
    return decode_positional_payload(WorkflowOutput, payload, 7)


def _decode_workflow(payload: object) -> Workflow:
    """Decode current workflows and released workflows without an output group order or display metadata.

    A released workflow without display metadata shows its file name, the same as a catalog entry without one.
    """
    if type(payload) is tuple and len(payload) == 10:
        payload = (*payload, [])
    if type(payload) is tuple and len(payload) == 11:
        payload = (*payload, "", "", None)
    return decode_positional_payload(Workflow, payload, 14)


def _decode_sdf_reference(payload: object) -> Sdf.Reference:
    """Decode one explicit persisted Sdf.Reference payload.

    Args:
        payload: Five positional fields from the persistence registry.

    Returns:
        Reconstructed reference with exact path, offset, scale, and custom data.

    Raises:
        TypeError: If the payload does not have the expected shape.
    """
    if not isinstance(payload, (list, tuple)) or len(payload) != 5:
        raise TypeError("Sdf.Reference payload must contain five positional fields")
    asset_path, prim_path, offset, scale, custom_data = payload
    return Sdf.Reference(
        assetPath=asset_path,
        primPath=Sdf.Path(prim_path),
        layerOffset=Sdf.LayerOffset(offset, scale),
        customData=custom_data,
    )


COMFYUI_CODECS = (
    PersistenceCodec(ComfyUIJobApplyHandler.name, ComfyUIJobApplyHandler),
    PersistenceCodec(ComfyUITextureApplyHandler.name, ComfyUITextureApplyHandler),
    PersistenceCodec(ComfyUIAssetApplyHandler.name, ComfyUIAssetApplyHandler),
    PersistenceCodec(type_key(RemixType), RemixType),
    PersistenceCodec(type_key(OutputApplyBehavior), OutputApplyBehavior),
    PersistenceCodec(type_key(MeshReferenceSelection), MeshReferenceSelection),
    PersistenceCodec(type_key(WorkflowCategory), WorkflowCategory),
    PersistenceCodec(type_key(WorkflowSourceType), WorkflowSourceType),
    PersistenceCodec(type_key(WorkflowType), WorkflowType),
    PersistenceCodec(type_key(IntroducingLayer), IntroducingLayer),
    PersistenceCodec(
        type_key(Sdf.Reference),
        Sdf.Reference,
        lambda value: (
            value.assetPath,
            str(value.primPath),
            value.layerOffset.offset,
            value.layerOffset.scale,
            value.customData,
        ),
        _decode_sdf_reference,
    ),
    PersistenceCodec(
        type_key(ComfyUIApplyReceipt),
        ComfyUIApplyReceipt,
        lambda value: (
            value.original_authored_values,
            value.original_compare_values,
            value.applied_compare_values,
            value.metadata_receipt,
        ),
        _decode_comfyui_apply_receipt,
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
        type_key(ReferenceTarget),
        ReferenceTarget,
        lambda value: (value.owner_prim_path, value.source_reference, value.source_layer_identifier),
        lambda payload: decode_positional_payload(ReferenceTarget, payload, 3),
    ),
    PersistenceCodec(
        type_key(ComfyUIAssetApplyTarget),
        ComfyUIAssetApplyTarget,
        lambda value: (
            value.context_name,
            value.project_path,
            value.edit_target_layer,
            value.reference_targets,
            value.texture_targets,
            value.mesh_apply_behavior,
        ),
        lambda payload: decode_positional_payload(ComfyUIAssetApplyTarget, payload, 6),
    ),
    PersistenceCodec(
        type_key(ComfyUIInputBinding),
        ComfyUIInputBinding,
        lambda value: (value.port_id, value.remix_type, value.source),
        lambda payload: decode_positional_payload(ComfyUIInputBinding, payload, 3),
    ),
    PersistenceCodec(
        type_key(ComfyUIFileResult),
        ComfyUIFileResult,
        lambda value: (
            value.filename,
            value.key,
            value.remix_type,
            value.order,
            value.subfolder,
            value.texture_type,
            value.path,
        ),
        lambda payload: decode_positional_payload(ComfyUIFileResult, payload, 7),
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
        lambda payload: decode_positional_payload(
            lambda texture_type, context_name: SelectedTextureResolver(texture_type, context_name=context_name),
            payload,
            2,
        ),
    ),
    PersistenceCodec(
        type_key(AllStageTexturesResolver),
        AllStageTexturesResolver,
        lambda value: (value.texture_type, value.context_name, value.introducing_layer),
        lambda payload: decode_positional_payload(
            lambda texture_type, context_name, introducing_layer: AllStageTexturesResolver(
                texture_type, introducing_layer, context_name=context_name
            ),
            payload,
            3,
        ),
    ),
    PersistenceCodec(
        type_key(SelectedMeshResolver),
        SelectedMeshResolver,
        lambda value: (value.context_name, value.reference_selection),
        lambda payload: decode_positional_payload(
            lambda context_name, reference_selection: SelectedMeshResolver(
                context_name=context_name, reference_selection=reference_selection
            ),
            payload,
            2,
        ),
    ),
    PersistenceCodec(
        type_key(AllStageMeshesResolver),
        AllStageMeshesResolver,
        lambda value: (value.context_name, value.reference_selection),
        lambda payload: decode_positional_payload(
            lambda context_name, reference_selection: AllStageMeshesResolver(
                context_name=context_name, reference_selection=reference_selection
            ),
            payload,
            2,
        ),
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
        type_key(ComfyUIAssetJob),
        ComfyUIAssetJob,
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
        lambda payload: decode_positional_payload(ComfyUIAssetJob, payload, 10),
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
        _decode_workflow_request,
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
            value.output_group_order,
            value.display_name,
            value.description,
            value.workflow_type,
        ),
        _decode_workflow,
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
        lambda value: (
            value.node_id,
            value.remix_type,
            value.order,
            value.texture_type,
            value.apply_behavior,
            value.name,
            value.group,
        ),
        _decode_workflow_output,
    ),
)
