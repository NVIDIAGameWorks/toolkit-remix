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

from __future__ import annotations

__all__ = ["StandardizeLinearTexturesStep"]

import pathlib

import numpy as np
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.nvtt.core import BlockFormat, convert_to_openexr, is_dds, is_linear_image
from omni.flux.utils.common.path_utils import get_udim_sequence, is_udim_texture, write_metadata

from ..constants import DDS_SOURCE_HASH_METADATA_KEY, TEXTURE_INFO
from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import RemixAssetItem, TextureAsset
from ..utils import hash_source_file, is_dds_texture
from ..worker import run_in_worker_thread

# The largest value BC6H_UF16 stores. Skybox textures keep HDR values up to this limit.
_BC6H_UF16_MAX = 65504.0
_NORMAL_TYPES = (TextureTypes.NORMAL_OGL, TextureTypes.NORMAL_DX, TextureTypes.NORMAL_OTH)
# Each pass edits about this many pixels at a time, so a temporary array holds 12 MiB, not the full image.
_CHUNK_PIXELS = 1 << 20
# sRGB values at or below this limit use the linear segment of the sRGB decode.
_SRGB_LINEAR_THRESHOLD = 0.04045


def _requires_standardization(texture: TextureAsset) -> bool:
    """Return whether the texture needs float preparation or UDIM resolution."""
    return is_udim_texture(str(texture.path)) or not is_dds_texture(texture)


def _srgb_to_linear(color: np.ndarray) -> np.ndarray:
    """Return the sRGB decode of NVTT, which the DDS encoder applies to an sRGB source.

    Args:
        color: sRGB color values.

    Returns:
        A new array with the linear color values.
    """
    return np.where(color <= _SRGB_LINEAR_THRESHOLD, color / 12.92, ((color + 0.055) / 1.055) ** 2.4)


def _standardize_pixels(pixels: np.ndarray, texture_type: TextureTypes, srgb: bool) -> None:
    """Change float RGBA pixels in place to linear values in the range that the DDS format of the texture stores.

    NaN becomes 0 and infinity becomes the maximum. sRGB color channels become linear, and alpha stays linear.
    A normal map with a negative component stores signed [-1, 1] vectors, so it moves to the unsigned [0, 1]
    encoding before the limit applies.

    Args:
        pixels: Float32 RGBA pixels with shape ``(height, width, 4)``.
        texture_type: Semantic that selects the DDS format.
        srgb: Whether the color channels hold sRGB values.
    """
    maximum = _BC6H_UF16_MAX if texture_type is TextureTypes.SKYBOX else 1.0
    rows_per_chunk = max(1, _CHUNK_PIXELS // pixels.shape[1])
    chunks = [pixels[start : start + rows_per_chunk] for start in range(0, pixels.shape[0], rows_per_chunk)]
    signed = False
    for rows in chunks:
        np.nan_to_num(rows, copy=False, nan=0.0, posinf=maximum, neginf=0.0)
        # ponytail: one negative component marks the whole file as signed, and each UDIM tile decides alone.
        # A declared encoding per texture is the upgrade path.
        signed = signed or (texture_type in _NORMAL_TYPES and bool((rows[:, :, 0:3] < 0.0).any()))
    for rows in chunks:
        color = rows[:, :, 0:3]
        if srgb:
            np.copyto(color, _srgb_to_linear(color))
        if signed:
            color *= 0.5
            color += 0.5
        # ponytail: out-of-range values clamp, so a height map in scene units loses its scale. Normalize if needed.
        np.clip(rows, 0.0, maximum, out=rows)


def _write_standardized_openexr(
    context: RemixAssetPipelineContext, source: pathlib.Path, texture_type: TextureTypes
) -> pathlib.Path:
    """Write a source texture as a linear float OpenEXR work file in the range of its DDS format.

    An SDR source is sRGB when its DDS format is gamma encoded or BC6H_UF16, which is the rule of the DDS encoder.
    The work file records the reuse key of the source bytes, so DDS reuse stays keyed on the source.

    Args:
        context: Remix pipeline state that owns the workspace.
        source: Texture file to read.
        texture_type: Semantic that selects the color space and the value range.

    Returns:
        The OpenEXR work path.
    """
    linear = is_linear_image(source)
    texture_info = TEXTURE_INFO[texture_type]
    srgb = not linear and (texture_info.gamma_encoded or texture_info.block_format == BlockFormat.BC6H_UF16)
    # The color space and the range follow the texture type, so a source that two types share gets one file each.
    # The file name stays the source name, which names the DDS output.
    work_path = context.get_work_path(source, suffix=".exr")
    work_path = work_path.parent / texture_type.name / work_path.name
    work_path.parent.mkdir(exist_ok=True)
    convert_to_openexr(source, work_path, lambda pixels: _standardize_pixels(pixels, texture_type, srgb))
    write_metadata(str(work_path), DDS_SOURCE_HASH_METADATA_KEY, hash_source_file(source, linear))
    return work_path


def _standardize_udim(context: RemixAssetPipelineContext, texture: TextureAsset) -> None:
    """Resolve the UDIM ledger and prepare non-DDS tiles as float OpenEXR files."""
    tiles = texture.udim_tiles or tuple(pathlib.Path(tile) for tile in get_udim_sequence(str(texture.path)))
    if not tiles:
        raise RuntimeError(f"UDIM texture resolves to no tiles: {texture.path}. UDIM files don't exist.")
    if not is_dds(tiles[0]):
        tiles = tuple(_write_standardized_openexr(context, tile, texture.texture_type) for tile in tiles)
    texture.udim_tiles = tiles
    texture.path = tiles[0]


class StandardizeLinearTexturesStep(PipelineStep):
    """Replace texture sources with linear float OpenEXR files in the range of their DDS format.

    Later steps read the float values without 8-bit rounding, and the DDS encoder reads one format for every
    texture. The step edits one texture at a time in place, so memory holds about one float copy of one image.
    DDS pixels stay unchanged. UDIM paths use the first concrete tile. Mixed DDS and non-DDS tiles are unsupported.
    """

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier."""
        return "standardize_linear_textures"

    @property
    def description(self) -> str:
        """Return a human-readable description."""
        return "Prepare textures"

    def validate(self, context: PipelineContext) -> list[str]:
        """Validate that the runner provided a work directory for the OpenEXR files."""
        errors = super().validate(context)
        if errors:
            return errors
        return context.validate_work_dir(self.name)

    def should_run(self, context: RemixAssetPipelineContext) -> bool:
        """Return whether any texture needs float preparation or UDIM resolution."""
        return any(_requires_standardization(texture) for texture in context.textures)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no work."""
        return "only DDS textures"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Resolve UDIM textures and prepare non-DDS textures as linear float OpenEXR files."""
        for texture in context.textures:
            if not _requires_standardization(texture):
                continue
            if texture.udim_tiles or is_udim_texture(str(texture.path)):
                await run_in_worker_thread(_standardize_udim, context, texture)
                continue
            texture.path = await run_in_worker_thread(
                _write_standardized_openexr, context, texture.path, texture.texture_type
            )
