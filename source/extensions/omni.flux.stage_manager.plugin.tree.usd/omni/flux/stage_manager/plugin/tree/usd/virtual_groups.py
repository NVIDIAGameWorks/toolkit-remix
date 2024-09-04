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

from typing import TYPE_CHECKING

from .base import StageManagerUSDTreeDelegate as _StageManagerUSDTreeDelegate
from .base import StageManagerUSDTreeItem as _StageManagerUSDTreeItem
from .base import StageManagerUSDTreeModel as _StageManagerUSDTreeModel
from .base import StageManagerUSDTreePlugin as _StageManagerUSDTreePlugin

if TYPE_CHECKING:
    from pxr import Usd


class VirtualGroupsItem(_StageManagerUSDTreeItem):
    def __init__(
        self,
        display_name: str,
        tooltip: str,
        children: list["VirtualGroupsItem"] | None = None,
        prim: "Usd.Prim" = None,
        is_virtual: bool | None = None,
    ):
        """
        Create a Virtual Group Item

        Args:
            display_name: The name to display in the Tree
            tooltip: The tooltip to display when hovering an item in the Tree
            children: The children items.
            prim: The prim associated with the item. This should NOT BE SET for virtual groups
            is_virtual: Can be set explicitly, otherwise it will be inferred from the prim argument
        """

        super().__init__(display_name, tooltip, children, prim)

        self._data["virtual"] = (prim is None) if (is_virtual is None) else is_virtual

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
