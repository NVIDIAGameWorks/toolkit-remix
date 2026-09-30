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

import pathlib

from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from PIL import Image

from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import RemixAssetItem
from ..worker import run_in_worker_thread


def _srgb_to_linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(value: float) -> float:
    return value * 12.92 if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055


def _factor_lut(factor: float, srgb: bool) -> list[int]:
    """Build an 8-bit lookup table that multiplies a band by ``factor`` in linear space."""
    lut = []
    for index in range(256):
        value = index / 255
        if srgb:
            value = _linear_to_srgb(_srgb_to_linear(value) * factor)
        else:
            value *= factor
        lut.append(min(255, round(value * 255)))
    return lut


def _apply_factor(image: Image.Image, factor: tuple[float, ...]) -> Image.Image:
    """Multiply the image by per-channel factors.

    One factor multiplies a mono texture in linear space. Three or four factors multiply an sRGB color
    texture. The fourth factor multiplies an existing linear alpha band, or adds one when it is not ``1.0``.
    """
    if len(factor) == 1:
        lut = _factor_lut(factor[0], srgb=False)
        return Image.merge("RGB", [band.point(lut) for band in image.convert("RGB").split()])
    has_alpha = "A" in image.getbands() or "transparency" in image.info
    image = image.convert("RGBA" if has_alpha or (len(factor) == 4 and factor[3] != 1.0) else "RGB")
    bands = list(image.split())
    for index in range(3):
        bands[index] = bands[index].point(_factor_lut(factor[index], srgb=True))
    if len(bands) == 4:
        bands[3] = bands[3].point(_factor_lut(factor[3] if len(factor) == 4 else 1.0, srgb=False))
    return Image.merge(image.mode, bands)


def _extract_channel(
    source: pathlib.Path, destination: pathlib.Path, channel: str | None, factor: tuple[float, ...] | None
) -> None:
    """Write the selected channel as an RGB PNG, or the source image in its own mode, and bake the factor into it."""
    with Image.open(source) as image:
        # Palette and grayscale images have no RGB bands, so convert before selecting the channel.
        result = image.convert("RGBA").getchannel(channel).convert("RGB") if channel else image
        if factor:
            result = _apply_factor(result, factor)
        result.save(destination, "PNG")


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
        return any(texture.channel or texture.factor for texture in context.textures)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why the step has no work."""
        return "no texture channels to extract"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Extract each marked channel, bake each factor, and clear the source markers."""
        for texture in context.textures:
            if not texture.channel and not texture.factor:
                continue
            stem_suffix = f".{texture.channel.lower()}" if texture.channel else ""
            if texture.factor:
                stem_suffix += ".x" + "_".join(repr(component) for component in texture.factor)
            output_path = context.get_work_path(texture.source_path, stem_suffix=stem_suffix, suffix=".png")
            await run_in_worker_thread(_extract_channel, texture.path, output_path, texture.channel, texture.factor)
            texture.path = output_path
            texture.channel = None
            texture.factor = None
