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

from lightspeed.common.constants import HIDDEN_REMIX_CATEGORIES as _HIDDEN_REMIX_CATEGORIES
from lightspeed.common.constants import REMIX_CATEGORIES_DISPLAY_NAMES as _REMIX_CATEGORIES_DISPLAY_NAMES
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.stage_manager.factory import StageManagerUtils as _StageManagerUtils
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsDelegate as _VirtualGroupsDelegate
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsItem as _VirtualGroupsItem
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsModel as _VirtualGroupsModel
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsTreePlugin as _VirtualGroupsTreePlugin
from pxr import Usd
from pydantic import Field


class CategoryGroupsItem(_VirtualGroupsItem):
    """
    Create a Category Group Item

    Args:
        display_name: The name to display in the Tree
        data: The USD Prim this item represents
        tooltip: The tooltip to display when hovering an item in the TreeView
        display_name_ancestor: A string to prepend to the display name with

        category: The name of the category this item represents
    """

    def __init__(
        self,
        display_name: str,
        data: Usd.Prim | None,
        tooltip: str = None,
        display_name_ancestor: str = None,
        category: str = None,
    ):
        super().__init__(
            display_name,
            data,
            tooltip=tooltip,
            display_name_ancestor=display_name_ancestor,
        )

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

    def _build_item(
        self,
        display_name: str,
        data: Usd.Prim,
        tooltip: str = "",
        category: str | None = None,
        display_name_ancestor: str | None = None,
    ):
        return CategoryGroupsItem(
            display_name,
            data,
            tooltip=tooltip,
            category=category,
        )

    def _build_items(self, items: Iterable[_StageManagerItem]) -> list[CategoryGroupsItem] | None:
        # Build the group items only needs to be done once (preserves expanded states)
        parent_lookup = {}
        for attr, display_name in _REMIX_CATEGORIES_DISPLAY_NAMES.items():
            parent_lookup[attr] = self._build_item(display_name, None, tooltip=f"{display_name} Group", category=attr)

        # Get unique item names
        item_names = _StageManagerUtils.get_unique_names(items)

        # Add category items to the groups
        for item in items:
            prim_path = item.data.GetPath()
            for attr in item.data.GetAttributes():
                if attr.GetName() in _REMIX_CATEGORIES_DISPLAY_NAMES and attr.Get():
                    name, parent = item_names.get(item, (None, None))

                    tree_item = self._build_item(
                        name,
                        item.data,
                        tooltip=str(prim_path),
                        display_name_ancestor=parent,
                    )

                    tree_item.parent = parent_lookup[attr.GetName()]

        # Filter out empty groups and sort alphabetically (both parents and children)
        filtered_items = [item for item in parent_lookup.values() if item.children]
        self.sort_items(filtered_items)

        return filtered_items


class CategoryGroupsDelegate(_VirtualGroupsDelegate):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class CategoryGroupsTreePlugin(_VirtualGroupsTreePlugin):
    """
    A flat list of prims that can be grouped using virtual groups
    """

    model: CategoryGroupsModel = Field(default=None, exclude=True)
    delegate: CategoryGroupsDelegate = Field(default=None, exclude=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.model = CategoryGroupsModel()
        self.delegate = CategoryGroupsDelegate()
