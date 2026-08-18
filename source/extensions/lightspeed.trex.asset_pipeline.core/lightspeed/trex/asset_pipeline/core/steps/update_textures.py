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

__all__ = ["UpdateTexturesStep"]

import carb
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from pxr import Sdf

from ..pipeline_context import RemixAssetPipelineContext
from ..pipeline_item import AssetKind, RemixAssetItem, get_texture_source_path


class UpdateTexturesStep(PipelineStep):
    """Update model USD texture asset paths after texture processing."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier.

        Returns:
            Stable pipeline step name.
        """
        return "update_textures"

    @property
    def description(self) -> str:
        """Return a human-readable description.

        Returns:
            User-facing phase description.
        """
        return "Update model textures"

    def should_run(self, context: PipelineContext) -> bool:
        """Return true when any model item has texture bindings to update.

        Args:
            context: Pipeline state to inspect.

        Returns:
            Whether at least one model texture binding needs rewriting.
        """
        return any(item.kind is AssetKind.MODEL and item.texture_bindings for item in context.items)

    def validate(self, context: PipelineContext) -> list[str]:
        """Validate that final output paths are available for model texture rewrites.

        Args:
            context: Pipeline state to validate.

        Returns:
            Ordered validation errors.
        """
        errors = super().validate(context)
        if errors:
            return errors
        if any(item.kind is AssetKind.MODEL for item in context.items):
            errors.extend(context.validate_output_dir(self.name))
        return errors

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this model texture update step has no work.

        Args:
            context: Pipeline state without runnable update work.

        Returns:
            User-readable skip reason.
        """
        if any(item.kind is AssetKind.MODEL for item in context.items):
            return "no model texture bindings"
        return "no model items"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Update each recorded shader asset path to its processed texture path.

        Args:
            context: Remix pipeline state containing model texture bindings.

        Raises:
            RuntimeError: If a recorded shader or texture attribute no longer exists.
        """
        for item in context.items:
            if item.kind is not AssetKind.MODEL or not item.texture_bindings:
                continue

            stage = context.open_stage(item.value)
            changed = False
            with Sdf.ChangeBlock():
                for binding in item.texture_bindings:
                    shader_prim = stage.GetPrimAtPath(binding.shader_path)
                    if not shader_prim:
                        raise RuntimeError(f"Texture binding shader no longer exists: {binding.shader_path}")

                    attr = shader_prim.GetAttribute(binding.input_name)
                    if not attr:
                        raise RuntimeError(
                            f"Texture binding attribute '{binding.input_name}' no longer exists on {binding.shader_path}"
                        )

                    relative_path = context.get_relative_output_asset_path(
                        item.value,
                        binding.texture.path,
                        owner_source_path=item.source_path,
                        asset_source_path=get_texture_source_path(binding.texture),
                    )
                    new_asset_path = Sdf.AssetPath(relative_path)
                    if attr.Get() == new_asset_path:
                        continue

                    attr.Set(new_asset_path)
                    changed = True

            if changed:
                context.save_stage()
                carb.log_info(f"[UpdateTextures] Saved updated stage {item.value}")
