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

from omni import ui
from pydantic import Field

from .base import StageManagerUSDTreeDelegate as _StageManagerUSDTreeDelegate
from .base import StageManagerUSDTreeItem as _StageManagerUSDTreeItem
from .base import StageManagerUSDTreeModel as _StageManagerUSDTreeModel
from .base import StageManagerUSDTreePlugin as _StageManagerUSDTreePlugin


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

    def build_widget(self):
        with ui.HStack(spacing=ui.Pixel(2), height=0):
            if not self.children:
                with ui.VStack(width=ui.Pixel(16)):
                    ui.Spacer()
                    ui.Image(
                        "",
                        name="Rename" if self._nickname else "RenameOutline",
                        width=ui.Pixel(16),
                        height=ui.Pixel(16),
                    )
                    ui.Spacer()
            if self._display_name_ancestor:
                ui.Label(self._display_name_ancestor, name="FadedLabel", width=0)
                ui.Label("/", name="FadedLabel", width=0)
            field = ui.StringField(
                read_only=True,
                style=(
                    self.FIELD_READ_ONLY_STYLE_NO_NICKNAME
                    if not self._nickname
                    else self.FIELD_READ_ONLY_STYLE_NICKNAME
                ),
            )
            ui.Spacer()
            if not self.children:
                field.set_mouse_double_clicked_fn(lambda x, y, b, m: self._nickname_action(field, x, y, b, m))
                self._setup_edit_mode(field)
            if not self.show_nickname:
                field.model.set_value(self._display_name)
                self._set_label_width(int(len(self._display_name)))
                self.tooltip = self._nickname if self._nickname else self._display_name
            else:
                field.model.set_value(self.display_name)
                self._set_label_width(int(len(self.display_name)))
                self.tooltip = self._display_name


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
