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

import threading

from lightspeed.common import constants
from lightspeed.trex.utils.common.prim_utils import is_empty_mesh_prim as _is_empty_mesh_prim
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
            tooltip=tooltip,
            display_name_ancestor=display_name_ancestor,
            is_virtual=is_virtual,
        )

    def _build_items(
        self,
        items: list[_StageManagerItem],
        cancel_event: threading.Event,
    ) -> list[MeshGroupsItem] | None:
        """Build mesh groups unless the refresh is cancelled."""
        if cancel_event.is_set():
            return None

        tree_items = {}

        # Create mesh group items as parents and create instance list.
        # _is_mesh_prototype and _is_empty_mesh_prim are mutually exclusive so both
        # branches can safely share a single pass over items.
        instance_items = []
        for item in items:
            if cancel_event.is_set():
                return None
            if _is_instance(item.data):
                instance_items.append(item)

            prim_path = item.data.GetPath()
            item_path = str(prim_path)
            if _is_mesh_prototype(item.data):
                # Display name should be the mesh_HASH prim instead of "mesh", otherwise keep the original name
                display_name = prim_path.GetParentPath().name if prim_path.name == "mesh" else prim_path.name
                tree_items[item_path] = self._build_item(
                    display_name,
                    item.data,
                    tooltip=item_path,
                    is_virtual=True,
                )
                tree_items[item_path].path = item_path
            elif _is_empty_mesh_prim(item.data):
                tree_items[item_path] = self._build_item(
                    prim_path.name,
                    item.data,
                    tooltip=item_path,
                    is_virtual=True,
                )
                tree_items[item_path].path = item_path

        # Create instance group items as children of mesh group items
        for item in instance_items:
            if cancel_event.is_set():
                return None
            # Get item name and parent name for hierarchy labeling
            prim_path = item.data.GetPath()
            path_str = str(prim_path)
            item_name = prim_path.name
            parent_name = prim_path.GetParentPath().name
            parent_mesh_path = constants.COMPILED_REGEX_INSTANCE_TO_MESH_SUB.sub(rf"{constants.MESH_PATH}\2", path_str)

            if parent_mesh_path in tree_items:
                mesh_tree_item = self._build_item(
                    item_name,
                    item.data,
                    tooltip=path_str,
                    display_name_ancestor=parent_name,
                    is_virtual=False,
                )
                mesh_tree_item.path = path_str
                mesh_tree_item.parent = tree_items[parent_mesh_path]

        # Sort the items alphabetically (both parents and children)
        if cancel_event.is_set():
            return None
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
