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

from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from pydantic import Field

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

    def _build_item(self, item: _StageManagerItem) -> PrimGroupsItem:
        prim_path = item.data.GetPath()
        return PrimGroupsItem(str(prim_path.name), item.data, tooltip=str(prim_path))


class PrimGroupsDelegate(_StageManagerUSDTreeDelegate):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class PrimGroupsTreePlugin(_StageManagerUSDTreePlugin):
    """
    A hierarchical tree of prims reflecting the actual USD structure.

    The plugin model expects a single context item representing the root of the USD stage. The children prims will be
    fetched during item creation.
    """

    model: PrimGroupsModel = Field(default=None, exclude=True)
    delegate: PrimGroupsDelegate = Field(default=None, exclude=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.model = PrimGroupsModel(context_name=self._context_name)
        self.delegate = PrimGroupsDelegate()
