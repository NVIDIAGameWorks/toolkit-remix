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

from collections.abc import Callable

import carb
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.utils.octahedral_converter import OctahedralConverter

from ..pipeline_context import RemixAssetPipelineContext
from ..pipeline_item import RemixAssetItem, iter_texture_assets
from ..worker import run_in_worker_thread


def _get_normal_converter(texture_type: TextureTypes) -> Callable[[str, str], None] | None:
    """Return the converter for one source normal-map semantic.

    Args:
        texture_type: Texture semantic to resolve.

    Returns:
        DirectX or OpenGL converter, or ``None`` for non-convertible semantics.
    """
    if texture_type is TextureTypes.NORMAL_DX:
        return OctahedralConverter.convert_dx_file_to_octahedral
    if texture_type is TextureTypes.NORMAL_OGL:
        return OctahedralConverter.convert_ogl_file_to_octahedral
    return None


class ConvertNormalStep(PipelineStep):
    """Convert DirectX/OpenGL normal textures to octahedral normal textures."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier.

        Returns:
            Stable pipeline step name.
        """
        return "convert_normal"

    @property
    def description(self) -> str:
        """Return a human-readable description.

        Returns:
            User-facing phase description.
        """
        return "Prepare normal textures"

    def should_run(self, context: PipelineContext) -> bool:
        """Return true when any texture record is a DirectX/OpenGL normal.

        Args:
            context: Pipeline state to inspect.

        Returns:
            Whether any normal texture needs octahedral conversion.
        """
        return any(_get_normal_converter(texture.texture_type) is not None for texture in iter_texture_assets(context))

    def validate(self, context: PipelineContext) -> list[str]:
        """Validate that the runner provided a work directory for converted files.

        Args:
            context: Pipeline state to validate.

        Returns:
            Ordered validation errors.
        """
        errors = super().validate(context)
        if errors:
            return errors
        return context.validate_work_dir(self.name)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no work for the already-compatible context.

        Args:
            context: Pipeline state without convertible normal textures.

        Returns:
            User-readable skip reason.
        """
        return "no DirectX/OpenGL normal textures"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Convert matching texture records in place.

        This mutates ``TextureAsset.path`` and ``TextureAsset.texture_type`` only.
        The owning ``RemixAssetItem`` object and item type stay unchanged.

        Args:
            context: Pipeline state containing texture records and the temporary work directory.
        """
        for texture in iter_texture_assets(context):
            converter = _get_normal_converter(texture.texture_type)
            if converter is None:
                continue

            old_path = texture.path
            source_semantic = texture.texture_type.name.lower()
            new_path = context.get_work_path(
                old_path,
                stem_suffix=f".{source_semantic}.octahedral",
                suffix=".png",
            )

            carb.log_info(f"[ConvertNormal] Converting {old_path} -> {new_path}")
            await run_in_worker_thread(converter, str(old_path), str(new_path))

            texture.path = new_path
            texture.texture_type = TextureTypes.NORMAL_OTH
