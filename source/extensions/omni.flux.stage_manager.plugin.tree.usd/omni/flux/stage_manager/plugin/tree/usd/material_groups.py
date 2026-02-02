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

from __future__ import annotations

from typing import Iterable

from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.utils.common.materials import get_materials_from_prim_paths as _get_materials_from_prim_paths
from pxr import Usd, UsdGeom, UsdShade
from pydantic import Field

from .virtual_groups import VirtualGroupsDelegate as _VirtualGroupsDelegate
from .virtual_groups import VirtualGroupsItem as _VirtualGroupsItem
from .virtual_groups import VirtualGroupsModel as _VirtualGroupsModel
from .virtual_groups import VirtualGroupsTreePlugin as _VirtualGroupsTreePlugin


class MaterialGroupsItem(_VirtualGroupsItem):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    @property
    def icon(self):
        if self.is_virtual:
            return "Material"
        return ""


class MaterialGroupsModel(_VirtualGroupsModel):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def _build_item(
        self,
        display_name: str,
        data: Usd.Prim | None,
        tooltip: str = "",
        display_name_ancestor: str = "",
        is_virtual: bool = False,
    ) -> MaterialGroupsItem:
        """
        Factory method to create a MaterialGroupsItem instance.

        Args:
            display_name: The name to display in the tree.
            data: The USD prim this item represents, or None for material group headers.
            tooltip: The tooltip text to display on hover.
            display_name_ancestor: Ancestor path prefix for disambiguation.
            is_virtual: Whether this is a virtual grouping node (material header).

        Returns:
            A new MaterialGroupsItem instance.
        """
        return MaterialGroupsItem(
            display_name=display_name,
            data=data,
            tooltip=tooltip,
            is_virtual=is_virtual,
            display_name_ancestor=display_name_ancestor,
        )

    def _build_items(self, items: Iterable[_StageManagerItem]) -> list[MaterialGroupsItem] | None:
        tree_items = {}

        # Create material group items as parents and create mesh list
        mesh_items = []
        for item in items:
            if item.data.IsA(UsdGeom.Mesh):
                mesh_items.append(item)
            if item.data.IsA(UsdShade.Material):
                item_path = item.data.GetPath()
                tree_items[str(item_path)] = self._build_item(
                    str(item_path.name),
                    item.data,
                    tooltip=str(item_path),
                    is_virtual=True,
                )

        # Create child mesh group items from mesh list
        for item in mesh_items:
            # Grab item name and parent name for hierarchy labeling
            item_name = item.data.GetPath().name
            parent_name = item.data.GetParent().GetPath().name

            # Find target materials; There should normally be 1, but handle multiple
            target_materials = _get_materials_from_prim_paths([item.data.GetPath()])
            for material in target_materials:
                parent_material_path = str(material.GetPrim().GetPath())

                # Create the mesh children per parent material
                if parent_material_path in tree_items:
                    mat_tree_item = self._build_item(
                        item_name,
                        item.data,
                        tooltip=str(item.data.GetPath()),
                        display_name_ancestor=parent_name,
                    )
                    mat_tree_item.parent = tree_items[parent_material_path]

        # Sort the items alphabetically (both parents and children)
        sorted_tree_items = list(tree_items.values())
        self.sort_items(sorted_tree_items)

        return sorted_tree_items


class MaterialGroupsDelegate(_VirtualGroupsDelegate):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class MaterialGroupsTreePlugin(_VirtualGroupsTreePlugin):
    """
    A flat list of prims that can be grouped using virtual groups
    """

    model: MaterialGroupsModel = Field(default=None, exclude=True)
    delegate: MaterialGroupsDelegate = Field(default=None, exclude=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.model = MaterialGroupsModel()
        self.delegate = MaterialGroupsDelegate()
