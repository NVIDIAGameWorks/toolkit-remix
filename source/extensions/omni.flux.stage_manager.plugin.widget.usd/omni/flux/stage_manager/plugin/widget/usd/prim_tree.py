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

import carb
import omni.kit.clipboard
from omni import ui, usd
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin as _StageManagerMenuMixin
from omni.flux.utils.common.menus import MenuGroup as _MenuGroup
from omni.flux.utils.common.menus import MenuItem as _MenuItem
from pydantic import Field

from .base import StageManagerUSDWidgetPlugin as _StageManagerUSDWidgetPlugin

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class PrimTreeWidgetPlugin(_StageManagerUSDWidgetPlugin, _StageManagerMenuMixin):
    display_name: str = Field(default="Prims", exclude=True)
    tooltip: str = Field(default="", exclude=True)

    icon_size: int = Field(default=24 - 8, description="The size of the icon in pixels", exclude=True)
    item_spacing: int = Field(default=8, description="The horizontal space between the items in pixels", exclude=True)

    def build_ui(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool):
        with ui.HStack(spacing=ui.Pixel(self.item_spacing), tooltip=item.tooltip or ""):
            if item.icon:
                with ui.VStack(width=0):
                    ui.Spacer(width=0)
                    ui.Image("", name=item.icon, width=ui.Pixel(self.icon_size), height=ui.Pixel(self.icon_size))
                    ui.Spacer(width=0)
            else:
                ui.Spacer(height=0, width=0)
            item.build_widget()

    def build_overview_ui(self, model: "_StageManagerTreeModel"):
        # Make sure to only count prims, not virtual groups
        prims_count = len([i for i in model.iter_items_children() if not (hasattr(i, "is_virtual") and i.is_virtual)])

        ui.Label(f"{prims_count} prim{'s' if prims_count > 1 else ''} available")

    @classmethod
    def _get_menu_items(cls):
        return [
            (
                {
                    "name": _MenuItem.COPY_PRIM_PATH.value,
                    "glyph": "copy.svg",
                    "onclick_fn": cls._on_copy_prim_path,
                },
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            )
        ]

    @classmethod
    def _on_copy_prim_path(cls, payload: dict):
        selected_prim_paths = usd.get_context(payload.get("context_name", "")).get_selection().get_selected_prim_paths()
        clipboard_content = ", ".join(selected_prim_paths)

        omni.kit.clipboard.copy(clipboard_content)
        carb.log_info(f"Copied '{clipboard_content}' to clipboard")
