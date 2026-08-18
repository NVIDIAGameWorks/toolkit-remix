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

__all__ = ["AllStageTexturesResolver"]

import dataclasses
from collections.abc import Iterator
from typing import Any, ClassVar

from lightspeed.trex.utils.common.asset_utils import is_texture_from_capture
from pxr import Usd, UsdGeom, UsdShade

from ...enums import IntroducingLayer
from ..base import ResolverParameter, StageExpandingResolver
from .base import TextureResolverBase


@dataclasses.dataclass
class AllStageTexturesResolver(TextureResolverBase, StageExpandingResolver):
    """Resolve one texture per material, expanded across every material in the stage.

    Resolving a single material behaves exactly like :class:`SelectedTextureResolver`.
    Selecting this getter instead expands a submission to one job per stage material
    (de-duplicated by material) rather than only the current selection. ``introducing_layer``
    filters that expansion to textures introduced by the capture layer, the mod layer, or any layer.
    """

    label: ClassVar[str] = "All Textures"
    introducing_layer: IntroducingLayer = IntroducingLayer.CAPTURE

    @property
    def parameters(self) -> tuple[ResolverParameter[Any], ...]:
        """Return the texture type binding plus the introducing layer binding.

        Returns:
            The inherited texture type binding followed by the introducing layer binding.
        """
        return (
            *super().parameters,
            ResolverParameter(
                "introducing_layer",
                IntroducingLayer,
                lambda: self.introducing_layer,
                self._set_introducing_layer,
                tuple(IntroducingLayer),
                "Introducing Layer",
                tooltip=(
                    "Which layer must introduce a texture for it to be processed: the capture layer, "
                    "the mod layer, or any layer."
                ),
            ),
        )

    def _set_introducing_layer(self, value: IntroducingLayer) -> None:
        """Store the introducing layer filter selected by the user.

        Args:
            value: Introducing layer the getter should include.
        """
        self.introducing_layer = value

    def accepts_introducing_layer(self, texture_path: str) -> bool:
        """Return whether a resolved texture matches the configured introducing layer.

        Args:
            texture_path: Resolved texture file path to classify by its introducing layer.

        Returns:
            Whether the texture should be processed under the current introducing layer filter.
        """
        if self.introducing_layer is IntroducingLayer.ANY:
            return True
        return is_texture_from_capture(texture_path) is (self.introducing_layer is IntroducingLayer.CAPTURE)

    def iter_stage_prim_paths(self, stage: Usd.Stage) -> Iterator[str]:
        """Iterate every mesh, subset, and material prim path in the stage.

        Args:
            stage: Live stage traversed to seed one candidate per stage material.

        Yields:
            Mesh, subset, and material prim paths used to build all-stage material candidates.
        """
        predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
        for prim in Usd.PrimRange.Stage(stage, predicate):
            if prim.IsA(UsdGeom.Mesh) or prim.IsA(UsdGeom.Subset) or prim.IsA(UsdShade.Material):
                yield str(prim.GetPath())

    def accepts_resolved_value(self, value: object) -> bool:
        """Return whether a resolved texture matches the configured introducing layer.

        Args:
            value: Texture path resolved for one stage material.

        Returns:
            Whether the material should produce one all-stage job.
        """
        return self.accepts_introducing_layer(str(value))
