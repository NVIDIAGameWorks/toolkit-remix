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

from dataclasses import dataclass

from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.nvtt.core import BlockFormat, MipmapFilter

__all__ = (
    "BASE_HASH_KEY",
    "DDS_SOURCE_HASH_METADATA_KEY",
    "ORPHAN_PARAMETER_CLEANUP_SETTING_PATH",
    "PROCESSED_OUTPUT_DIR_NAME",
    "TEXTURE_INFO",
    "VALIDATION_EXTENSIONS_KEY",
    "VALIDATION_PASSED_KEY",
    "TextureInfo",
)

# The legacy ingestion plugins keyed DDS reuse on "src_hash" and stored hash_file(source) under it. Keep the
# same key and the same value so a texture ingested by the retired system is reused instead of re-encoded.
DDS_SOURCE_HASH_METADATA_KEY = "src_hash"

ORPHAN_PARAMETER_CLEANUP_SETTING_PATH = "/exts/omni.usd/mdl/ignoreOrphanParametersCleanup"

#: Directory below a job directory that holds the job's local pipeline outputs.
PROCESSED_OUTPUT_DIR_NAME = "processed"

#: Metadata sidecar key written by the legacy ``FileMetadataWritter`` for every file.
BASE_HASH_KEY: str = "base_hash"
#: Metadata sidecar key for the pipeline validation outcome.
VALIDATION_PASSED_KEY: str = "validation_passed"
#: Metadata sidecar key for the validator extension snapshot.
VALIDATION_EXTENSIONS_KEY: str = "validation_extensions"
#: Metadata sidecar key for individual fixes applied by validator check plugins.
#: The new pipeline has no check-plugin concept; this key is defined for parity but not written.
# The legacy writer also appended a "fixes_applied" key, populated by the retired check plugins. The shipped
# ingested fixtures under lightspeed.trex.app.resources carry no such key, and no reader in this pipeline
# consumes one, so this pipeline writes none rather than inventing entries.


@dataclass(frozen=True)
class TextureInfo:
    """A texture's desired block format, encoding, and mip filter."""

    block_format: BlockFormat
    gamma_encoded: bool
    mip_filter: MipmapFilter = MipmapFilter.BOX


#: Every texture type has an entry. The runtime shaders gamma-decode only the gamma-encoded entries below.
#: They read all other maps as linear data (dxvk-remix remix-1.5.2).
TEXTURE_INFO: dict[TextureTypes, TextureInfo] = {
    TextureTypes.DIFFUSE: TextureInfo(BlockFormat.BC7, True),
    TextureTypes.OTHER: TextureInfo(BlockFormat.BC7, True),
    TextureTypes.EMISSIVE: TextureInfo(BlockFormat.BC7, True),
    TextureTypes.TRANSMITTANCE: TextureInfo(BlockFormat.BC7, True),
    TextureTypes.SINGLE_SCATTERING: TextureInfo(BlockFormat.BC7, False),
    TextureTypes.NORMAL_OGL: TextureInfo(BlockFormat.BC5, False),
    TextureTypes.NORMAL_DX: TextureInfo(BlockFormat.BC5, False),
    TextureTypes.NORMAL_OTH: TextureInfo(BlockFormat.BC5, False),
    TextureTypes.ROUGHNESS: TextureInfo(BlockFormat.BC4, False),
    TextureTypes.METALLIC: TextureInfo(BlockFormat.BC4, False),
    TextureTypes.ANISOTROPY: TextureInfo(BlockFormat.BC4, False),
    TextureTypes.MEASUREMENT_DISTANCE: TextureInfo(BlockFormat.BC4, False),
    TextureTypes.HEIGHT: TextureInfo(BlockFormat.BC4, False, mip_filter=MipmapFilter.MAX),
    TextureTypes.SKYBOX: TextureInfo(BlockFormat.BC6H_UF16, False),
}
