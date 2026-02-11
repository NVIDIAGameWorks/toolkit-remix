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

from omni.flux.custom_tags.core import CustomTagsCore as _CustomTagsCore
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.stage_manager.factory import StageManagerUtils as _StageManagerUtils
from pxr import Usd
from pydantic import Field

from .virtual_groups import VirtualGroupsDelegate as _VirtualGroupsDelegate
from .virtual_groups import VirtualGroupsItem as _VirtualGroupsItem
from .virtual_groups import VirtualGroupsModel as _VirtualGroupsModel
from .virtual_groups import VirtualGroupsTreePlugin as _VirtualGroupsTreePlugin


class CustomTagGroupsItem(_VirtualGroupsItem):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    @property
    def icon(self) -> str | None:
        return "Tag" if (self.data is None) else None


class CustomTagGroupsModel(_VirtualGroupsModel):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def _build_item(
        self, display_name: str, data: Usd.Prim | None, tooltip: str = "", display_name_ancestor: str = ""
    ) -> CustomTagGroupsItem:
        return CustomTagGroupsItem(
            display_name,
            data,
            tooltip=tooltip,
            display_name_ancestor=display_name_ancestor,
        )

    def _build_items(self, items: Iterable[_StageManagerItem]) -> list[CustomTagGroupsItem] | None:
        tree_items = []
        tag_items = {}

        core = _CustomTagsCore(context_name=self._context_name)

        # Build the group items
        for tag_path in core.get_all_tags():
            group_item = self._build_item(
                core.get_tag_name(tag_path),
                None,
                tooltip=f"Items tagged with the '{core.get_tag_name(tag_path)}' custom tag",
            )

            tree_items.append(group_item)
            for prim_path in core.get_tag_prims(tag_path):
                if prim_path not in tag_items:
                    tag_items[prim_path] = []

                tag_items[prim_path].append(group_item)

        # If no tags were found, we can quick return
        if not tree_items:
            return tree_items

        # Get unique item names
        item_names = _StageManagerUtils.get_unique_names(items)

        # Fill the groups with the context items
        for item in items:
            prim_path = item.data.GetPath()
            if prim_path not in tag_items:
                continue

            item_name, parent_name = item_names.get(item, (None, None))
            if item_name is None:
                item_name = item.data.GetPath().name

            for group_item in tag_items[prim_path]:
                cust_tree_item = self._build_item(
                    item_name, item.data, tooltip=str(prim_path), display_name_ancestor=parent_name
                )
                cust_tree_item.parent = group_item

        # Sort the items alphabetically (both parents and children)
        self.sort_items(tree_items)

        return tree_items


class CustomTagGroupsDelegate(_VirtualGroupsDelegate):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class CustomTagGroupsTreePlugin(_VirtualGroupsTreePlugin):
    """
    A flat list of prims that can be grouped using virtual groups
    """

    model: CustomTagGroupsModel = Field(default=None, exclude=True)
    delegate: CustomTagGroupsDelegate = Field(default=None, exclude=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.model = CustomTagGroupsModel()
        self.delegate = CustomTagGroupsDelegate()
