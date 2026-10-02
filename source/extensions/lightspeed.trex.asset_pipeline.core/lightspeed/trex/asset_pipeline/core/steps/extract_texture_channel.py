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

__all__ = ["ExtractTextureChannelStep"]

import functools

import numpy as np
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep

from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import RemixAssetItem, TextureAsset
from ..utils import edit_texture_pixels, is_dds_texture


def _requires_extraction(texture: TextureAsset) -> bool:
    """Return whether a non-DDS texture requires a channel or factor operation."""
    return bool(texture.channel or texture.factor) and not is_dds_texture(texture)


def _extract_linear_channel(pixels: np.ndarray, channel: str | None, factor: tuple[float, ...] | None) -> None:
    """Select a channel and multiply by the factor in float and in place.

    The pixels are linear, so every factor multiplies them directly.
    """
    if channel:
        index = "RGBA".index(channel)
        for target in range(3):
            if target != index:
                pixels[:, :, target] = pixels[:, :, index]
        pixels[:, :, 3] = 1.0
    if factor:
        if len(factor) == 1:
            # A mono factor writes RGB without alpha.
            pixels[:, :, 0:3] *= factor[0]
            pixels[:, :, 3] = 1.0
        else:
            pixels[:, :, 0 : len(factor)] *= np.asarray(factor, dtype="float32")


class ExtractTextureChannelStep(PipelineStep):
    """Extract packed texture channels and bake texture factors before texture conversion."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier."""
        return "extract_texture_channel"

    @property
    def description(self) -> str:
        """Return the step description."""
        return "Extract texture channels"

    def should_run(self, context: RemixAssetPipelineContext) -> bool:
        """Return whether any texture requires channel extraction or a factor."""
        return any(_requires_extraction(texture) for texture in context.textures)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why the step has no work."""
        return "no texture channels to extract"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Extract each marked channel, bake each factor, and clear the source markers."""
        for texture in context.textures:
            if not _requires_extraction(texture):
                continue
            stem_suffix = f".{texture.channel.lower()}" if texture.channel else ""
            if texture.factor:
                stem_suffix += ".x" + "_".join(repr(component) for component in texture.factor)
            transform = functools.partial(_extract_linear_channel, channel=texture.channel, factor=texture.factor)
            await edit_texture_pixels(context, texture, transform, stem_suffix=stem_suffix)
            texture.channel = None
            texture.factor = None
