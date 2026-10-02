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
import pathlib
from collections.abc import Callable

import carb
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.utils.octahedral_converter import OctahedralConverter

from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import RemixAssetItem
from ..texture_naming import get_octahedral_stem
from omni.flux.utils.common.path_utils import (
    get_udim_sequence as _get_udim_sequence,
    is_udim_texture as _is_udim_texture,
)
from ..worker import run_in_worker_thread


def _get_normal_converter(texture_type: TextureTypes) -> Callable[[str, str], None] | None:
    """Return the converter for one source normal-map semantic.

    Args:
        texture_type: Texture semantic to resolve.

    Returns:
        DirectX or OpenGL converter, or ``None`` for non-convertible semantics.
    """
    if texture_type in (TextureTypes.NORMAL_DX, TextureTypes.NORMAL_OGL):
        return functools.partial(
            OctahedralConverter.convert_file_to_octahedral, opengl=texture_type is TextureTypes.NORMAL_OGL
        )
    return None


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
        """Return true when any texture record is a DirectX or OpenGL normal.

        Octahedral normals (``NORMAL_OTH``) and other texture types need no conversion, so they do not run the step.
        """
        return any(_get_normal_converter(texture.texture_type) is not None for texture in context.textures)

    def validate(self, context: PipelineContext) -> list[str]:
        """Validate that the runner provided a work directory for converted files."""
        errors = super().validate(context)
        if errors:
            return errors
        return context.validate_work_dir(self.name)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no work for the already-compatible context."""
        return "no DirectX or OpenGL normal textures"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Convert the DirectX and OpenGL normal texture records in place.

        Other texture records, which include octahedral normals, stay unchanged.
        A UDIM path expands to concrete tile files. Each tile converts individually into the
        same work directory (keyed on the ``<UDIM>`` token form), so the sequence stays whole
        across steps. The concrete tiles are stored in ``texture.udim_tiles`` and ``texture.path``
        points to the first tile. ``ApplyProcessedTexturesStep`` derives the ``<UDIM>`` token only when
        it writes the shader attribute.

        This mutates ``TextureAsset.path``, ``TextureAsset.texture_type``, and
        ``TextureAsset.udim_tiles``. The owning ``RemixAssetItem`` stays unchanged.

        Raises:
            RuntimeError: If a UDIM pattern resolves to zero concrete tile files.
        """
        for texture in context.textures:
            converter = _get_normal_converter(texture.texture_type)
            if converter is None:
                continue
            texture_path_str = str(texture.path)
            if _is_udim_texture(texture_path_str):
                tiles = _get_udim_sequence(texture_path_str)
                if not tiles:
                    raise RuntimeError(f"UDIM texture resolves to no tiles: {texture.path}. UDIM files don't exist.")
                udim_source = texture.original_path or texture.path
                tile_work_paths: list[pathlib.Path] = []
                for tile_path_str in tiles:
                    tile_path = pathlib.Path(tile_path_str)
                    tile_new_path = context.get_work_path(udim_source, stem=get_octahedral_stem(tile_path.stem))
                    carb.log_info(f"[ConvertNormal] Converting UDIM tile {tile_path_str} -> {tile_new_path}")
                    await run_in_worker_thread(converter, tile_path_str, str(tile_new_path))
                    tile_work_paths.append(tile_new_path)
                texture.path = tile_work_paths[0]
                texture.udim_tiles = tuple(tile_work_paths)
            else:
                new_path = context.get_work_path(texture.path, stem=get_octahedral_stem(texture.path.stem))
                carb.log_info(f"[ConvertNormal] Converting {texture.path} -> {new_path}")
                await run_in_worker_thread(converter, texture_path_str, str(new_path))
                texture.path = new_path
            texture.texture_type = TextureTypes.NORMAL_OTH
