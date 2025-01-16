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

__all__ = ["JointTreeModel"]

import omni.ui as ui
from lightspeed.trex.asset_replacements.core.shared import SkeletonReplacementBinding
from omni.flux.utils.widget.tree_widget import TreeModelBase
from pxr import UsdSkel

from .item_model import JointItem


class JointTreeModel(TreeModelBase[JointItem]):
    """Model representing a tree of remapped joints."""

    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    @property
    def column_count(self) -> int:
        """
        Get the number of columns to build
        """
        return 3

    def get_item_children(self, parentItem: JointItem = None) -> list[JointItem]:  # noqa: N803
        """
        Returns the vector of items that are nested to the given parent item.


        ### Arguments:

            `id :`
                The item to request children from. If it's null, the children of root will be returned.
        """
        if parentItem is None:
            return self._items
        return parentItem.children

    def get_item_value_model(self, item: JointItem = None, column_id: int = 0) -> ui.AbstractValueModel | None:
        """
        Get the value model associated with this item.


        ### Arguments:

            `item :`
                The item to request the value model from. If it's null, the root value model will be returned.

            `index :`
                The column number to get the value model.
        """
        if column_id == 0:
            return item.name_model()
        if column_id == 1:
            return None
        if column_id == 2:
            return item.remap_model().get_item_value_model()
        raise ValueError("invalid column_id")

    def get_item_value_model_count(self, item: JointItem = None) -> int:
        """
        Returns the number of columns this model item contains.
        """
        return self.column_count

    def get_joint_map(self) -> list[int]:
        return [
            item.remap_model().get_current_index()
            for item in sorted(self.iter_items_children(), key=lambda item: item.index)
        ]

    def refresh(self, skel_replacement: SkeletonReplacementBinding | None, read_from_usd: bool = True):
        self._items.clear()
        if skel_replacement is not None:
            mesh_joints = skel_replacement.get_mesh_joints()
            capture_joints = skel_replacement.get_captured_joints()
            if read_from_usd:
                remapped_joint_map = skel_replacement.get_joint_map()
            else:
                remapped_joint_map = skel_replacement.generate_joint_map(mesh_joints, capture_joints, fallback=True)

            joint_items = []
            topology = UsdSkel.Topology(mesh_joints)
            for i, joint_name in enumerate(mesh_joints):
                remapped_index = None
                if remapped_joint_map:
                    remapped_index = remapped_joint_map[i]
                joint_item = JointItem(joint_name, i, capture_joints, remapped_index=remapped_index)
                joint_items.append(joint_item)
                if topology.IsRoot(i):
                    self._items.append(joint_item)
                else:
                    parent_index = topology.GetParent(i)
                    joint_items[parent_index].add_child(joint_item)

        self._item_changed(None)
