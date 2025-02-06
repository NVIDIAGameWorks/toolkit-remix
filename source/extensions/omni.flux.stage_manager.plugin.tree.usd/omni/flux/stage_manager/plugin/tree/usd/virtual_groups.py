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

from typing import TYPE_CHECKING

from omni import ui

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
        data: Usd.Prim | None,
        tooltip: str = "",
        display_name_ancestor: str | None = None,
        is_virtual: bool | None = None,
    ):
        """
        Create a Virtual Group Item

        Args:
            display_name: The name to display in the Tree
            data: The USD Prim this item represents
            tooltip: The tooltip to display when hovering an item in the TreeView
            display_name_ancestor: A string to prepend to the display name with
            is_virtual: Can be set explicitly, otherwise it will be inferred from the data argument
        """

        super().__init__(display_name, data, tooltip=tooltip, display_name_ancestor=display_name_ancestor)

        self._is_virtual = (data is None) if (is_virtual is None) else is_virtual

    @property
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_is_virtual": None,
            }
        )
        return default_attr

    @property
    def is_virtual(self) -> bool:
        return self._is_virtual

    def build_widget(self):
        with ui.HStack(spacing=ui.Pixel(2)):
            if self._display_name_ancestor:
                ui.Label(self._display_name_ancestor, name="FadedLabel", width=0)
                ui.Label("/", name="FadedLabel", width=0)
            ui.Label(self.display_name, name="VirtualItemLabel" if self.is_virtual else "")


class VirtualGroupsModel(_StageManagerUSDTreeModel):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


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

        self.model = VirtualGroupsModel(context_name=self._context_name)
        self.delegate = VirtualGroupsDelegate()
