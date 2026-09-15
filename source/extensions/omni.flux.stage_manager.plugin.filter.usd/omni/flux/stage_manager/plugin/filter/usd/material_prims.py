"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["MaterialBindingsFilterPlugin", "MaterialPrimsFilterPlugin"]

from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.utils.common.materials import get_materials_from_prim_paths
from pxr import UsdGeom, UsdShade
from pydantic import Field

from .base import StageManagerUSDFilterPlugin
from .base import ToggleableUSDFilterPlugin as _ToggleableUSDFilterPlugin


class MaterialPrimsFilterPlugin(_ToggleableUSDFilterPlugin):
    display_name: str = Field(default="Material Prims", exclude=True)
    tooltip: str = Field(default="Filter for material prims", exclude=True)

    include_meshes: bool = Field(
        True, description="Whether the filter should also include child meshes with the materials or not."
    )

    def _evaluate_item(self, item: StageManagerItem) -> bool:
        """Evaluate whether an item contains a material or configured mesh.

        Args:
            item: Stage Manager item containing the prim to evaluate.

        Returns:
            Whether the item contains a material or configured mesh.
        """
        prim = item.data
        return prim.IsA(UsdShade.Material) or (self.include_meshes and prim.IsA(UsdGeom.Mesh))


class MaterialBindingsFilterPlugin(StageManagerUSDFilterPlugin):
    """Retain material grouping candidates and prepare mesh bindings."""

    display_name: str = Field(default="Material Bindings Filter", exclude=True)
    tooltip: str = Field(default="", exclude=True)
    display: bool = Field(default=False, exclude=True)

    def filter_predicate(self, item: StageManagerItem) -> bool:
        """Retain materials and meshes with prepared material bindings.

        Args:
            item: Stage Manager item containing the prim to evaluate.

        Returns:
            Whether the item is a material or a mesh with resolved bindings.
        """
        prim = item.data
        if prim.IsA(UsdShade.Material):
            return True
        if not prim.IsA(UsdGeom.Mesh):
            return False

        memberships = tuple(
            str(material.GetPrim().GetPath())
            for material in get_materials_from_prim_paths([prim.GetPath()], context_name=self._context_name)
        )
        if not memberships:
            return False
        item.prepare_group_memberships(memberships)
        return True

    def build_ui(self) -> None:
        """Build no UI for the internal material binding filter."""
        pass
