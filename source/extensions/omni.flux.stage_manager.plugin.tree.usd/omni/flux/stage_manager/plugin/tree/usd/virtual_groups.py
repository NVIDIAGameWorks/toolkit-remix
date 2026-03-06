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
from omni.flux.utils.widget.usd.prims.string_field import UsdPrimNameField as _UsdPrimNameField
from pydantic import Field

from .base import StageManagerUSDTreeDelegate as _StageManagerUSDTreeDelegate
from .base import StageManagerUSDTreeItem as _StageManagerUSDTreeItem
from .base import StageManagerUSDTreeModel as _StageManagerUSDTreeModel
from .base import StageManagerUSDTreePlugin as _StageManagerUSDTreePlugin

if TYPE_CHECKING:
    from pxr import Usd


class VirtualGroupsItem(_StageManagerUSDTreeItem):
    """
    Create a Virtual Group Item.

    Virtual items are synthetic grouping nodes that exist for UI organization purposes
    and don't directly correspond to a real USD prim. For example, a Material node that
    groups meshes by their bound material. Non-virtual items represent actual USD prims.

    Note: The same USD prim may appear multiple times under different virtual parents
    (e.g., a mesh with multiple materials). In such cases, always create new instances
    via `_build_item()` rather than reusing existing tree items to ensure each
    occurrence gets its own unique tree item instance.

    Args:
        display_name: The name to display in the Tree
        data: The USD Prim this item represents (None for pure virtual grouping nodes)
        tooltip: The tooltip to display when hovering an item in the TreeView
        display_name_ancestor: A string to prepend to the display name with
        is_virtual: Whether this is a virtual grouping node. If None, inferred from
            whether data is None.
    """

    def __init__(
        self,
        *args,
        is_virtual: bool | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        # NOTE: is_virtual is a tri-state where if data is not provided object is always virtual
        # but it can also be forced
        self._is_virtual = (self.data is None) if (is_virtual is None) else is_virtual

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

    def display_text_fn(self, prim: Usd.Prim) -> str:
        """Get display text for the prim. Returns display_name if virtual, otherwise prim.GetName()."""
        if self.is_virtual:
            return self.display_name
        return prim.GetName()

    def build_widget(self):
        with ui.HStack(spacing=ui.Pixel(2), height=0):
            # Determine if editing should be enabled (only for leaf nodes)
            if not self.data and self.is_virtual:
                with ui.VStack(height=ui.Pixel(24)):
                    ui.Spacer(height=4)
                    ui.Label(self.display_name, width=0, tooltip=self._tooltip)
                    ui.Spacer()
                ui.Spacer()
                return

            self._nickname_field = _UsdPrimNameField(
                prim=self._data,
                display_text_fn=self.display_text_fn,
                editable_check_fn=self.is_prim_editable,
                field_id=self.show_nickname_key,
                show_display_name_ancestor=bool(self._display_name_ancestor),
            )

            ui.Spacer()

    def is_prim_editable(self, prim: Usd.Prim) -> bool:
        if self.is_virtual:
            return False
        return bool(prim and prim.IsValid())


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

    model: VirtualGroupsModel = Field(default=None, exclude=True)
    delegate: VirtualGroupsDelegate = Field(default=None, exclude=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.model = VirtualGroupsModel()
        self.delegate = VirtualGroupsDelegate()
