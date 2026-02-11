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

from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.stage_manager.factory import StageManagerUtils as _StageManagerUtils
from pxr import Usd, UsdSkel
from pydantic import Field

from .virtual_groups import VirtualGroupsDelegate as _VirtualGroupsDelegate
from .virtual_groups import VirtualGroupsItem as _VirtualGroupsItem
from .virtual_groups import VirtualGroupsModel as _VirtualGroupsModel
from .virtual_groups import VirtualGroupsTreePlugin as _VirtualGroupsTreePlugin


class SkeletonTreeItem(_VirtualGroupsItem):
    icon: str | None = None

    def __init__(
        self,
        display_name: str,
        data: Usd.Prim | None,
        tooltip: str = "",
        display_name_ancestor: str | None = None,
        skel_root: Usd.Prim | None = None,
        skel_prim: Usd.Prim | None = None,
        bound_prim: Usd.Prim | None = None,
    ):
        """
        Create a Skeleton Tree Item

        Args:
            display_name: The name to display in the Tree
            data: The prim associated with the skeleton. This should NOT BE SET for virtual groups
            tooltip: The tooltip to display when hovering an item in the Tree
            display_name_ancestor: A string to prepend to the display name with
            skel_root: The root prim of the skeleton
            skel_prim: The skeleton prim
            bound_prim: The mesh prim bound to the skeleton if applicable
        """

        super().__init__(display_name, data, tooltip=tooltip, display_name_ancestor=display_name_ancestor)
        self._skel_root = skel_root
        self._skel_prim = skel_prim
        self._bound_prim = bound_prim

    @property
    def skel_root(self) -> Usd.Prim | None:
        return self._skel_root

    @property
    def skel_prim(self) -> Usd.Prim | None:
        return self._skel_prim

    @property
    def bound_prim(self) -> Usd.Prim | None:
        return self._bound_prim

    @property
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_skel_root": None,
                "_skel_prim": None,
                "_bound_prim": None,
            }
        )
        return default_attr


class SkeletonItem(SkeletonTreeItem):
    icon = "Skeleton"


class SkeletonJointItem(SkeletonTreeItem):
    icon = "SkeletonJoint"

    def __init__(
        self,
        display_name: str,
        data: Usd.Prim | None,
        index: int,
        tooltip: str = "",
        display_name_ancestor: str | None = None,
        skel_root: Usd.Prim | None = None,
        skel_prim: Usd.Prim | None = None,
        bound_prim: Usd.Prim | None = None,
    ):
        super().__init__(
            display_name,
            data,
            tooltip=tooltip,
            display_name_ancestor=display_name_ancestor,
            skel_root=skel_root,
            skel_prim=skel_prim,
            bound_prim=bound_prim,
        )
        self._index = index

    @property
    def index(self):
        return self._index


class SkeletonRootItem(SkeletonTreeItem):
    icon = "SkeletonRoot"


class SkeletonBoundMeshItem(SkeletonTreeItem):
    icon = "Mesh"


class SkeletonGroupsModel(_VirtualGroupsModel):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def _build_items(self, items: Iterable[_StageManagerItem]) -> list[SkeletonTreeItem] | None:
        """
        Recursively build the model items from Stage Manager items

        Args:
            items: an iterable of Stage Manager items

        Returns:
            A list of Stage Manager items or None if the input items are None
        """
        orphan_group: SkeletonTreeItem | None = None

        self._unique_item_names = _StageManagerUtils.get_unique_names(items)

        tree_items: list[SkeletonTreeItem] = []
        for item in items:
            tree_item = self._create_tree_item_from_stage_item(item)
            item.tree_item = tree_item

            parent = item.parent
            if parent is None:
                if isinstance(tree_item, SkeletonRootItem):
                    # Add to the root
                    tree_items.append(tree_item)
                else:
                    # Add under orphan group
                    if not orphan_group:
                        orphan_group = self._build_item(
                            "Orphaned Skeletons", None, tooltip="Orphaned skeletons with no skel root"
                        )

                    tree_item.parent = orphan_group
            else:
                # Add to the parent
                tree_item.parent = parent.tree_item

        # Add orphan group last
        if orphan_group:
            tree_items.append(orphan_group)

        # Sort the parent items alphabetically
        self.sort_items(tree_items, sort_children=False)

        return tree_items

    def _build_item(
        self,
        display_name: str,
        data: Usd.Prim | None,
        tooltip: str = "",
        display_name_ancestor: str = "",
        skel_root: Usd.Prim | None = None,
        skel_prim: Usd.Prim | None = None,
        bound_prim: Usd.Prim | None = None,
        long_name: str = "",
        index: int | None = None,
    ) -> SkeletonTreeItem:
        """
        Factory method to create SkeletonTreeItem instances based on prim type.

        One of the more complex implementations of _build_item as it manages
        multiple constructors for different skeleton-related item types.

        Args:
            display_name: The name to display in the tree
            data: The USD prim (None for virtual groups)
            tooltip: Tooltip text for the item
            display_name_ancestor: Ancestor path prefix for display
            skel_root: The skeleton root prim
            skel_prim: The skeleton prim
            bound_prim: The bound mesh prim if applicable
            long_name: Full joint path used as cache key for recycling
            index: Joint index (required when creating SkeletonJointItem)

        Returns:
            A SkeletonTreeItem subclass instance appropriate for the prim type
        """

        if data is None:
            if index is None or not long_name:
                return SkeletonTreeItem(display_name, data, tooltip=tooltip)

            return SkeletonJointItem(
                display_name,
                data,  # messy to have all joints select same prim
                index,
                tooltip=tooltip,
                skel_root=skel_root,
                skel_prim=skel_prim,
            )

        match data.GetTypeName():
            case "SkelRoot":
                return SkeletonRootItem(
                    display_name,
                    data,
                    tooltip=tooltip,
                    display_name_ancestor=display_name_ancestor,
                )
            case "Skeleton":
                return SkeletonItem(
                    display_name,
                    data,
                    tooltip=tooltip,
                    display_name_ancestor=display_name_ancestor,
                    skel_root=skel_root,
                )

        return SkeletonBoundMeshItem(
            display_name,
            data,
            tooltip=tooltip,
            display_name_ancestor=display_name_ancestor,
            skel_root=skel_root,
            skel_prim=skel_prim,
            bound_prim=data,
        )

    def _create_tree_item_from_stage_item(self, item: _StageManagerItem) -> SkeletonTreeItem:
        """
        Function used to transform Stage Manager items into TreeView items

        Args:
            item: Stage Manager item

        Returns:
            A fully built TreeView item
        """

        def get_skel_root(prim_) -> Usd.Prim | None:
            skel_root_ = prim_.GetParent()
            while skel_root_ and skel_root_.GetTypeName() != "SkelRoot":
                skel_root_ = skel_root_.GetParent()
            return skel_root_

        prim: Usd.Prim = item.data
        item_name, parent_name = self._unique_item_names.get(item, (None, None))
        if item_name is None:
            item_name = prim.GetName()

        if prim.GetTypeName() == "SkelRoot":
            return self._build_item(
                item_name,
                prim,
                tooltip=f"{prim.GetTypeName()}: {prim.GetPath()}",
                display_name_ancestor=parent_name,
            )

        if prim.GetTypeName() == "Skeleton":
            skel_root = get_skel_root(prim)
            tree_item = self._build_item(
                item_name,
                prim,
                tooltip=f"{prim.GetTypeName()}: {prim.GetPath()}",
                display_name_ancestor=parent_name,
                skel_root=skel_root,
            )

            # Build tree items for each joint
            joint_items: dict[int, SkeletonJointItem] = {}
            skeleton = UsdSkel.Skeleton(prim)
            joints_attr = skeleton.GetJointsAttr()
            if joints_attr:
                joint_names = joints_attr.Get()
                topology = UsdSkel.Topology(joint_names)
                for i, joint_name in enumerate(joint_names):
                    short_name = joint_name.rsplit("/", 1)[-1]

                    joint_item = self._build_item(
                        short_name,
                        None,  # messy to have all joints select same prim
                        tooltip=f"Joint: {prim.GetPath()}, {joint_name}",
                        index=i,
                        skel_root=skel_root,
                        skel_prim=prim,
                        long_name=joint_name,
                    )
                    joint_items[i] = joint_item

                    # Add joints to the right parent in the hierarchy
                    if topology.IsRoot(i):
                        joint_item.parent = tree_item
                    else:
                        parent_index = topology.GetParent(i)
                        joint_item.parent = joint_items[parent_index]

            return tree_item
        if prim.HasAPI(UsdSkel.BindingAPI):
            skel_root = get_skel_root(prim)
            skel_prim = None
            skeleton = UsdSkel.BindingAPI(prim).GetSkeleton()
            if skeleton:
                skel_prim = skeleton.GetPrim()
            return self._build_item(
                item_name,
                prim,
                tooltip=f"{prim.GetTypeName()}: {prim.GetPath()}",
                display_name_ancestor=parent_name,
                skel_root=skel_root,
                skel_prim=skel_prim,
                bound_prim=prim,
            )

        raise ValueError(f"Unexpected prim type: {prim.GetTypeName()}, path: {prim.GetPath()}")


class SkeletonGroupsDelegate(_VirtualGroupsDelegate):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class SkeletonGroupsTreePlugin(_VirtualGroupsTreePlugin):
    """
    An abbreviated tree of skeleton related prims.
    """

    model: SkeletonGroupsModel = Field(default=None, exclude=True)
    delegate: SkeletonGroupsDelegate = Field(default=None, exclude=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.model = SkeletonGroupsModel()
        self.delegate = SkeletonGroupsDelegate()
