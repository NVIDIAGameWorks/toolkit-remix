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

__all__ = ["TREE_COLUMNS", "RecentProjectModel"]

from datetime import datetime

from omni.flux.utils.widget.tree_widget import TreeModelBase

from .items import RecentProjectItem

TREE_COLUMNS = {0: "Thumbnail", 1: "Name", 2: "Game", 3: "Version", 4: "Last Modified", 5: ""}


class RecentProjectModel(TreeModelBase):

    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def refresh(self, items: list[tuple[str, str, dict]]):
        """
        Refresh the model with the given items

        Args:
            items: list of tuples of (name, thumbnail, details)
        """
        recent_items = [RecentProjectItem(name, thumbnail, details) for name, thumbnail, details in items]
        self._items = sorted(
            recent_items,
            key=lambda i: (
                i.last_modified is not None,
                datetime.strptime(i.last_modified, "%m/%d/%Y, %H:%M:%S") if i.last_modified else datetime.today(),
            ),
            reverse=True,
        )

        self._item_changed(None)

    def get_item_children(self, item: RecentProjectItem):
        if item is None:
            return self._items
        return []

    def get_item_value_model_count(self, item: RecentProjectItem) -> int:
        return len(TREE_COLUMNS.keys())
