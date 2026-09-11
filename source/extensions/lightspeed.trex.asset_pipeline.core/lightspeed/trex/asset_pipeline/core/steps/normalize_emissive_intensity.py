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

__all__ = ["NormalizeEmissiveIntensityStep"]


import carb
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from pxr import Sdf, UsdShade

from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import AssetKind, RemixAssetItem
from ..utils import get_authoring_spec

_EMISSIVE_INTENSITY_ATTR = "inputs:emissive_intensity"
_LEGACY_EMISSIVE_INTENSITY = 10000.0
_NORMALIZED_EMISSIVE_INTENSITY = 1.0


class NormalizeEmissiveIntensityStep(PipelineStep):
    """Normalize legacy emissive intensity on converted model shaders."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier."""
        return "normalize_emissive_intensity"

    @property
    def description(self) -> str:
        """Return a human-readable description."""
        return "Normalize legacy emissive intensity"

    def should_run(self, context: PipelineContext) -> bool:
        """Return true when any model item exists to scan for legacy shader values."""
        return any(item.kind is AssetKind.MODEL for item in context.items)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no shader values to normalize."""
        return "no model items"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Rewrite legacy emissive intensity values authored on converted model shaders.

        Raises:
            RuntimeError: If a legacy value is authored outside the model's own directory.
        """
        for item in context.items:
            if item.kind is not AssetKind.MODEL:
                continue

            stage = await context.open_stage(item.value)
            model_parent = item.value.resolve(strict=False).parent
            changed_layers: dict[str, Sdf.Layer] = {}

            with Sdf.ChangeBlock():
                for prim in stage.Traverse():
                    if not prim.IsA(UsdShade.Shader):
                        continue

                    attr = prim.GetAttribute(_EMISSIVE_INTENSITY_ATTR)
                    if not attr or not attr.HasAuthoredValue() or attr.Get() != _LEGACY_EMISSIVE_INTENSITY:
                        continue

                    authoring_spec = get_authoring_spec(attr, model_parent)
                    authoring_spec.default = _NORMALIZED_EMISSIVE_INTENSITY
                    changed_layers[authoring_spec.layer.identifier] = authoring_spec.layer

            for layer in changed_layers.values():
                layer.Save()

            if changed_layers:
                carb.log_info(f"[NormalizeEmissiveIntensity] Normalized emissive intensity in {item.value}")
