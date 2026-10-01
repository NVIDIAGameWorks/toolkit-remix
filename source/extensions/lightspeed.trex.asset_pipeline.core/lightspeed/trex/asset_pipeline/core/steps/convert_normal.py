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

__all__ = ["ConvertNormalStep"]

import functools

import carb
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.utils.octahedral_converter import OctahedralConverter

from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import RemixAssetItem, TextureAsset
from ..texture_naming import get_octahedral_stem
from ..utils import edit_texture_pixels, is_dds_texture


def _needs_conversion(texture: TextureAsset) -> bool:
    """Return whether a prepared normal texture needs octahedral conversion."""
    return texture.texture_type in (TextureTypes.NORMAL_DX, TextureTypes.NORMAL_OGL) and not is_dds_texture(texture)


class ConvertNormalStep(PipelineStep):
    """Convert DirectX/OpenGL normal textures to octahedral normal textures."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier."""
        return "convert_normal"

    @property
    def description(self) -> str:
        """Return a human-readable description."""
        return "Prepare normal textures"

    def should_run(self, context: RemixAssetPipelineContext) -> bool:
        """Return true when a non-DDS texture needs DirectX or OpenGL normal conversion."""
        return any(_needs_conversion(texture) for texture in context.textures)

    def validate(self, context: PipelineContext) -> list[str]:
        """Validate that the runner provided a work directory for converted files."""
        errors = super().validate(context)
        if errors:
            return errors
        return context.validate_work_dir(self.name)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no work for the already-compatible context."""
        return "no non-DDS DirectX or OpenGL normal textures"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Convert the pixels of each DirectX and OpenGL normal texture to octahedral normals.

        The octahedral copies record no source hash, so the DDS step keys reuse on the octahedral values. A DirectX
        and an OpenGL conversion of one source share the DDS name but not the values, so a changed normal
        convention encodes again. DDS textures and other texture types stay unchanged.

        Raises:
            RuntimeError: If a texture file cannot be read or written.
        """
        for texture in context.textures:
            if not _needs_conversion(texture):
                continue
            carb.log_info(f"[ConvertNormal] Converting {texture.path}")
            convert = functools.partial(
                OctahedralConverter.convert_float_to_octahedral_in_place,
                opengl=texture.texture_type is TextureTypes.NORMAL_OGL,
            )
            await edit_texture_pixels(context, texture, convert, stem=get_octahedral_stem)
            texture.texture_type = TextureTypes.NORMAL_OTH
