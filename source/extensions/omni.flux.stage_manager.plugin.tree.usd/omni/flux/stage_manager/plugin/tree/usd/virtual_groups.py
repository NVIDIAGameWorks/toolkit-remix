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

from .base import StageManagerUSDTreeDelegate as _StageManagerUSDTreeDelegate
from .base import StageManagerUSDTreeItem as _StageManagerUSDTreeItem
from .base import StageManagerUSDTreeModel as _StageManagerUSDTreeModel
from .base import StageManagerUSDTreePlugin as _StageManagerUSDTreePlugin


class VirtualGroupsItem(_StageManagerUSDTreeItem):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class VirtualGroupsModel(_StageManagerUSDTreeModel):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def refresh(self):
        self._items = [
            VirtualGroupsItem(str(prim.GetPath().name), str(prim.GetPath()), prim=prim) for prim in self.context_items
        ]
        super().refresh()


class VirtualGroupsDelegate(_StageManagerUSDTreeDelegate):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class VirtualGroupsTreePlugin(_StageManagerUSDTreePlugin):
    """
    A flat list of prims that can be grouped using virtual groups
    """

    model: VirtualGroupsModel = None
    delegate: VirtualGroupsDelegate = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.model = VirtualGroupsModel()
        self.delegate = VirtualGroupsDelegate()
