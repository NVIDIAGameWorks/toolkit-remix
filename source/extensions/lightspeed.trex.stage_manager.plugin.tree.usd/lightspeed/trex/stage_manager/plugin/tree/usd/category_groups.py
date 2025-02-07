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
        category: str = None,
        display_name_ancestor: str = None,
    ):
        """
        Create a Category Group Item

        Args:
            display_name: The name to display in the Tree
            data: The USD Prim this item represents
            tooltip: The tooltip to display when hovering an item in the TreeView
        """

        super().__init__(display_name, data, tooltip=tooltip, display_name_ancestor=display_name_ancestor)

        self._categories = []
        if category is not None:
            self._categories.append(category)
        if data:
            for attr in data.GetAttributes():
                if "remix_category" in attr.GetName() and attr.Get():
                    self._categories.append(attr.GetName())

    @property
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_categories": [],
            }
        )
        return default_attr

    def is_category_hidden(self):
        return any(
            _REMIX_CATEGORIES_DISPLAY_NAMES.get(category, "") in _HIDDEN_REMIX_CATEGORIES
            for category in self._categories
        )

    @property
    def icon(self):
        if self.data:
            return None
        if self.is_category_hidden():
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
            found = False

            for attr in item.data.GetAttributes():
                if found:
                    break
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
                    found = True

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
