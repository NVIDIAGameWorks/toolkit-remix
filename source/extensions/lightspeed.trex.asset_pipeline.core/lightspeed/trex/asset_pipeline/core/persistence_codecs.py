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

from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.persistence import PersistenceCodec
from omni.flux.job_queue.core.persistence_codec import decode_positional_payload

from .job import TextureProcessingJob
from .models import ProcessedTexture, TextureProcessingItem, TextureProcessingRequest, TextureProcessingResult

__all__ = ("TEXTURE_PROCESSING_CODECS",)


TEXTURE_PROCESSING_CODECS = (
    PersistenceCodec("remix_texture.TextureTypes", TextureTypes),
    PersistenceCodec(
        "remix_texture.TextureProcessingItem",
        TextureProcessingItem,
        lambda value: (value.key, value.path, value.texture_type),
        lambda payload: decode_positional_payload(TextureProcessingItem, payload, 3),
    ),
    PersistenceCodec(
        "remix_texture.ProcessedTexture",
        ProcessedTexture,
        lambda value: (value.key, value.source_path, value.asset_url, value.texture_type),
        lambda payload: decode_positional_payload(ProcessedTexture, payload, 4),
    ),
    PersistenceCodec(
        "remix_texture.TextureProcessingRequest",
        TextureProcessingRequest,
        lambda value: (value.items, value.source_root, value.output_url),
        lambda payload: decode_positional_payload(TextureProcessingRequest, payload, 3),
    ),
    PersistenceCodec(
        "remix_texture.TextureProcessingResult",
        TextureProcessingResult,
        lambda value: (value.items,),
        lambda payload: decode_positional_payload(TextureProcessingResult, payload, 1),
    ),
    PersistenceCodec(
        "remix_texture.TextureProcessingJob",
        TextureProcessingJob,
        lambda value: (value.job_id, value.name, value.skip_reason, value.apply_binding),
        lambda payload: decode_positional_payload(TextureProcessingJob, payload, 4),
    ),
)
