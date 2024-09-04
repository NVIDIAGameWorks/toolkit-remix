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

from omni import ui
from pydantic import Field

from .base import StageManagerUSDWidgetPlugin as _StageManagerUSDWidgetPlugin

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class PrimTreeWidgetPlugin(_StageManagerUSDWidgetPlugin):
    display_name: str = "Prims"
    tooltip: str = ""

    icon_size: int = Field(24 - 8, description="The size of the icon in pixels", exclude=True)
    item_spacing: int = Field(8, description="The horizontal space between them items in pixels", exclude=True)

    def build_ui(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool):
        with ui.HStack(spacing=ui.Pixel(self.item_spacing), tooltip=item.tooltip):
            if item.icon:
                ui.Image("", name=item.icon, width=ui.Pixel(self.icon_size), height=ui.Pixel(self.icon_size))
            else:
                ui.Spacer(height=0, width=0)
            ui.Label(item.display_name)

    def build_result_ui(self, model: "_StageManagerTreeModel"):
        # Make sure to only count prims, not virtual groups
        prims_count = len([i for i in model.iter_items_children() if not i.data.get("virtual")])

        ui.Label(f"{prims_count} item{'s' if prims_count > 1 else '' } available")
