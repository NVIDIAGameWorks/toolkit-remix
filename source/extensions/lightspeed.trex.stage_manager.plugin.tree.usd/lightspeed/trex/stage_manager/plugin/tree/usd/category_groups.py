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

from typing import TYPE_CHECKING, Iterable

from lightspeed.common.constants import HIDDEN_REMIX_CATEGORIES as _HIDDEN_REMIX_CATEGORIES
from lightspeed.common.constants import REMIX_CATEGORIES_DISPLAY_NAMES as _REMIX_CATEGORIES_DISPLAY_NAMES
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.stage_manager.factory import StageManagerUtils as _StageManagerUtils
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsDelegate as _VirtualGroupsDelegate
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsItem as _VirtualGroupsItem
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsModel as _VirtualGroupsModel
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsTreePlugin as _VirtualGroupsTreePlugin

if TYPE_CHECKING:
    from pxr import Usd


class CategoryGroupsItem(_VirtualGroupsItem):
    def __init__(
        self,
        display_name: str,
        data: Usd.Prim | None,
        tooltip: str = None,
        display_name_ancestor: str = None,
        category: str = None,
    ):
        """
        Create a Category Group Item

        Args:
            display_name: The name to display in the Tree
            data: The USD Prim this item represents
            tooltip: The tooltip to display when hovering an item in the TreeView
            display_name_ancestor: A string to prepend to the display name with
            category: The name of the category this item represents
        """

        super().__init__(display_name, data, tooltip=tooltip, display_name_ancestor=display_name_ancestor)

        self._category = category

    @property
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_category": None,
            }
        )
        return default_attr

    @property
    def icon(self):
        if not self.is_virtual:
            return None
        if _REMIX_CATEGORIES_DISPLAY_NAMES.get(self._category) in _HIDDEN_REMIX_CATEGORIES:
            return "CategoriesHidden"
        return "CategoriesShown"


class CategoryGroupsModel(_VirtualGroupsModel):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def _build_items(self, items: Iterable[_StageManagerItem]) -> list[CategoryGroupsItem] | None:
        tree_items = {}

        # Build the group items
        for attr, display_name in _REMIX_CATEGORIES_DISPLAY_NAMES.items():
            tree_items[attr] = CategoryGroupsItem(display_name, None, tooltip=f"{display_name} Group", category=attr)

        # Get unique item names
        item_names = _StageManagerUtils.get_unique_names(items)

        # Add category items to the groups
        for item in items:
            prim_path = item.data.GetPath()
            for attr in item.data.GetAttributes():
                if attr.GetName() in _REMIX_CATEGORIES_DISPLAY_NAMES and attr.Get():
                    name, parent = item_names.get(item, (None, None))
                    tree_items[attr.GetName()].add_child(
                        CategoryGroupsItem(
                            name,
                            item.data,
                            tooltip=str(prim_path),
                            display_name_ancestor=parent,
                        )
                    )

        # Filter out empty groups
        return [item for item in tree_items.values() if item.children]


class CategoryGroupsDelegate(_VirtualGroupsDelegate):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class CategoryGroupsTreePlugin(_VirtualGroupsTreePlugin):
    """
    A flat list of prims that can be grouped using virtual groups
    """

    model: CategoryGroupsModel = None
    delegate: CategoryGroupsDelegate = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.model = CategoryGroupsModel()
        self.delegate = CategoryGroupsDelegate()
