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

from omni.flux.custom_tags.core import CustomTagsCore as _CustomTagsCore
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
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
    """Build sparse custom-tag groups from refresh-prepared memberships."""

    requires_context_ancestors = False

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

    def _build_items(
        self,
        items: list[_StageManagerItem],
        cancel_event: threading.Event,
    ) -> list[CustomTagGroupsItem] | None:
        """Build custom-tag groups unless the refresh is cancelled."""
        if cancel_event.is_set():
            return None

        tree_items = []
        tag_items = {}
        core = _CustomTagsCore(context_name=self._context_name)
        try:
            for tag_path in core.get_all_tags():
                if cancel_event.is_set():
                    return None
                tag_name = core.get_tag_name(tag_path)
                group_item = self._build_item(
                    tag_name,
                    None,
                    tooltip=f"Items tagged with the '{tag_name}' custom tag",
                )
                group_item.path = str(tag_path)
                tree_items.append(group_item)
                tag_items[str(tag_path)] = group_item

            if not tree_items:
                return tree_items

            for item in items:
                if cancel_event.is_set():
                    return None
                prim_path = item.data.GetPath()

                item_name, parent_name = item.prepared_display_name
                for tag_path in item.prepared_group_memberships:
                    if cancel_event.is_set():
                        return None
                    group_item = tag_items.get(tag_path)
                    if group_item is None:
                        continue
                    path_str = str(prim_path)
                    cust_tree_item = self._build_item(
                        item_name, item.data, tooltip=path_str, display_name_ancestor=parent_name
                    )
                    cust_tree_item.path = path_str
                    cust_tree_item.parent = group_item

            if cancel_event.is_set():
                return None
            self.sort_items(tree_items)
            return tree_items
        finally:
            core.destroy()


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
