"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ("PrimListModel",)

import omni.ui as ui

from .prim_item import PrimItem


class PrimListModel(ui.AbstractItemModel):
    """Model for the prim list TreeView."""

    def __init__(self):
        super().__init__()
        self._items: list[PrimItem] = []

    def set_items(self, prim_data: list[tuple[str, str]]):
        """Set the prim items from (path, type) tuples."""
        self._items = [PrimItem(path, prim_type, i) for i, (path, prim_type) in enumerate(prim_data)]
        self._item_changed(None)

    def get_item_children(self, item):
        if item is None:
            return self._items
        return []

    def get_item_value_model_count(self, item):
        return 1

    def get_item_value_model(self, item, column_id):
        return None

    @property
    def item_count(self) -> int:
        return len(self._items)

    def destroy(self):
        self._items = []
