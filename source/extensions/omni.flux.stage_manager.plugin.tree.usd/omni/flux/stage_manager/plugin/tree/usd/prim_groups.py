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

from typing import Iterable

from pxr import Usd

from .base import StageManagerUSDTreeDelegate as _StageManagerUSDTreeDelegate
from .base import StageManagerUSDTreeItem as _StageManagerUSDTreeItem
from .base import StageManagerUSDTreeModel as _StageManagerUSDTreeModel
from .base import StageManagerUSDTreePlugin as _StageManagerUSDTreePlugin


class PrimGroupsItem(_StageManagerUSDTreeItem):

    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class PrimGroupsModel(_StageManagerUSDTreeModel):

    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def refresh(self):
        self._items = self._build_items_recursive(self.context_items)
        super().refresh()

    def _build_items_recursive(self, prims: Iterable[Usd.Prim]) -> list[PrimGroupsItem]:
        items = []
        for prim in prims:
            children = self._build_items_recursive(
                self.filter_items((prim.GetFilteredChildren(Usd.PrimAllPrimsPredicate)))
            )
            items.append(PrimGroupsItem(str(prim.GetPath().name), str(prim.GetPath()), children=children, prim=prim))
        return items


class PrimGroupsDelegate(_StageManagerUSDTreeDelegate):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class PrimGroupsTreePlugin(_StageManagerUSDTreePlugin):
    """
    A hierarchical tree of prims reflecting the actual USD structure
    """

    model: PrimGroupsModel = None
    delegate: PrimGroupsDelegate = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.model = PrimGroupsModel()
        self.delegate = PrimGroupsDelegate()
