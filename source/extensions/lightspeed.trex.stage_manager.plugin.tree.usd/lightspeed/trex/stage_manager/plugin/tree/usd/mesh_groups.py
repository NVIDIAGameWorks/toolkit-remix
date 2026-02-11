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

from collections.abc import Iterable

from lightspeed.common import constants
from lightspeed.trex.utils.common.prim_utils import is_instance as _is_instance
from lightspeed.trex.utils.common.prim_utils import is_mesh_prototype as _is_mesh_prototype
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsDelegate as _VirtualGroupsDelegate
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsItem as _VirtualGroupsItem
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsModel as _VirtualGroupsModel
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsTreePlugin as _VirtualGroupsTreePlugin
from pxr import Usd
from pydantic import Field


class MeshGroupsItem(_VirtualGroupsItem):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    @property
    def icon(self):
        if self.is_virtual:
            return "Mesh"
        return ""


class MeshGroupsModel(_VirtualGroupsModel):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def _build_item(
        self,
        display_name: str,
        data: Usd.Prim,
        tooltip: str = "",
        display_name_ancestor: str = "",
        is_virtual: bool = False,
    ) -> MeshGroupsItem:
        return MeshGroupsItem(
            display_name=display_name,
            data=data,
            tooltip=str(data.GetPath()),
            display_name_ancestor=display_name_ancestor,
            is_virtual=is_virtual,
        )

    def _build_items(self, items: Iterable[_StageManagerItem]) -> list[MeshGroupsItem] | None:
        tree_items = {}

        # Create mesh group items as parents and create instance list
        instance_items = []
        for item in items:
            if _is_instance(item.data):
                instance_items.append(item)

            if _is_mesh_prototype(item.data):
                # Display name should be the mesh_HASH prim instead of "mesh", otherwise keep the original name
                item_path = item.data.GetPath()
                display_name = item_path.GetParentPath().name if item_path.name == "mesh" else item_path.name

                tree_items[str(item.data.GetPath())] = self._build_item(
                    display_name,
                    item.data,
                    tooltip=str(item.data.GetPath()),
                    is_virtual=True,
                )

        # Create instance group items as children of mesh group items
        for item in instance_items:
            # Get item name and parent name for hierarchy labeling
            item_name = item.data.GetPath().name
            parent_name = item.data.GetParent().GetPath().name

            # Use the parent mesh path found with regex
            parent_mesh_path = str(
                constants.COMPILED_REGEX_INSTANCE_TO_MESH_SUB.sub(rf"{constants.MESH_PATH}\2", str(item.data.GetPath()))
            )

            if parent_mesh_path in tree_items:
                mesh_tree_item = self._build_item(
                    item_name,
                    item.data,
                    tooltip=str(item.data.GetPath()),
                    display_name_ancestor=parent_name,
                    is_virtual=False,
                )
                mesh_tree_item.parent = tree_items[parent_mesh_path]

        # Sort the items alphabetically (both parents and children)
        sorted_tree_items = list(tree_items.values())
        self.sort_items(sorted_tree_items)

        return sorted_tree_items


class MeshGroupsDelegate(_VirtualGroupsDelegate):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class MeshGroupsTreePlugin(_VirtualGroupsTreePlugin):
    """
    A flat list of prims that can be grouped using virtual groups
    """

    model: MeshGroupsModel = Field(default=None, exclude=True)
    delegate: MeshGroupsDelegate = Field(default=None, exclude=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.model = MeshGroupsModel()
        self.delegate = MeshGroupsDelegate()
