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

from collections.abc import Callable
from dataclasses import fields
from typing import Any

from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.persistence import PersistenceCodec
from omni.flux.job_queue.core.persistence_codec import decode_positional_payload

from .jobs import MeshOptimizationJob, PrepareOptimizationJob, TextureProcessingJob
from .jobs.apply_handler import SaveMeshMetadataHandler, SaveTextureMetadataHandler
from .jobs.models import (
    MeshOptimizationRequest,
    MeshOptimizationResult,
    PrepareOptimizationResult,
    ProcessedTexture,
    TextureLedgerEntry,
    TextureProcessingItem,
    TextureProcessingRequest,
    TextureProcessingResult,
)
from .metadata import MetadataApplyReceipt

__all__ = ("MESH_OPTIMIZATION_CODECS", "TEXTURE_PROCESSING_CODECS")


def _dataclass_codec(name: str, value_type: type, decoder: Callable[[Any], Any] | None = None) -> PersistenceCodec:
    """Build a codec for a dataclass whose persisted tuple matches its declared field order.

    Field order is the persisted schema. Never reorder or remove a field of a persisted dataclass. To add
    one, append it with a default, pass a ``decoder`` that accepts the released shorter shape, and add a
    legacy-payload test beside the existing ones in ``tests/unit/test_codecs.py``.

    Args:
        name: Stable identifier stored in the queue database.
        value_type: Exact dataclass type to encode and decode.
        decoder: Optional override for payload shapes released before later fields were added.
            Defaults to requiring the exact current field count.

    Returns:
        A codec that encodes field values positionally and reconstructs the value the same way.
    """
    field_names = tuple(field.name for field in fields(value_type))
    length = len(field_names)
    return PersistenceCodec(
        name,
        value_type,
        lambda value: tuple(getattr(value, field_name) for field_name in field_names),
        decoder or (lambda payload: decode_positional_payload(value_type, payload, length)),
    )


def _decode_processed_texture(payload: Any) -> ProcessedTexture:
    """Decode a ProcessedTexture payload, accepting the released 1.1.x shape without udim_tiles.

    Args:
        payload: Decoded custom payload: a 4-tuple (released 1.1.x) or a 5-tuple (current).

    Returns:
        Constructed ProcessedTexture value, with udim_tiles defaulted to () for the legacy shape.

    Raises:
        TypeError: If the payload is not an exact tuple.
        ValueError: If the tuple length matches neither the released nor the current shape.
    """
    if type(payload) is tuple and len(payload) == 4:
        payload = (*payload, ())
    return decode_positional_payload(ProcessedTexture, payload, 5)


def _decode_texture_processing_result(payload: Any) -> TextureProcessingResult:
    """Decode a TextureProcessingResult payload, accepting the released 1.1.x shape without lineage.

    Args:
        payload: Decoded custom payload: a 1-tuple (released 1.1.x) or a 3-tuple (current).

    Returns:
        Constructed TextureProcessingResult value, with lineage and validation_passed defaulted for
        the legacy shape.

    Raises:
        TypeError: If the payload is not an exact tuple.
        ValueError: If the tuple length matches neither the released nor the current shape.
    """
    if type(payload) is tuple and len(payload) == 1:
        payload = (*payload, (), True)
    return decode_positional_payload(TextureProcessingResult, payload, 3)


TEXTURE_PROCESSING_CODECS = (
    PersistenceCodec("remix_texture.TextureTypes", TextureTypes),
    _dataclass_codec("remix_texture.TextureProcessingItem", TextureProcessingItem),
    _dataclass_codec("remix_texture.ProcessedTexture", ProcessedTexture, decoder=_decode_processed_texture),
    _dataclass_codec("remix_texture.TextureProcessingRequest", TextureProcessingRequest),
    _dataclass_codec(
        "remix_texture.TextureProcessingResult", TextureProcessingResult, decoder=_decode_texture_processing_result
    ),
    _dataclass_codec("remix_texture.TextureProcessingJob", TextureProcessingJob),
)


MESH_OPTIMIZATION_CODECS = (
    PersistenceCodec("NoneType", type(None)),
    _dataclass_codec("remix_mesh.MetadataApplyReceipt", MetadataApplyReceipt),
    _dataclass_codec("remix_mesh.TextureLedgerEntry", TextureLedgerEntry),
    _dataclass_codec("remix_mesh.MeshOptimizationRequest", MeshOptimizationRequest),
    _dataclass_codec("remix_mesh.PrepareOptimizationResult", PrepareOptimizationResult),
    _dataclass_codec("remix_mesh.MeshOptimizationResult", MeshOptimizationResult),
    _dataclass_codec("remix_mesh.MeshOptimizationJob", MeshOptimizationJob),
    _dataclass_codec("remix_mesh.PrepareOptimizationJob", PrepareOptimizationJob),
    PersistenceCodec(SaveTextureMetadataHandler.name, SaveTextureMetadataHandler),
    PersistenceCodec(SaveMeshMetadataHandler.name, SaveMeshMetadataHandler),
)
