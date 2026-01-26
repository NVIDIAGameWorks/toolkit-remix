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
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.stage_manager.plugin.filter.usd.base import StageManagerUSDFilterPlugin as _StageManagerUSDFilterPlugin
from pxr import Usd, UsdGeom
from pydantic import Field, PrivateAttr

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class VisiblePrimsFilterPlugin(_StageManagerUSDFilterPlugin):
    display_name: str = Field(default="Visibility Filter", exclude=True)
    tooltip: str = Field(default="Filter prims by their visibility status.", exclude=True)

    visible_prims_type: str = Field(default="All Prims", description="Filter prims by their visibility status.")

    _VISIBLE_PRIMS_DISPLAY_LABELS: dict = PrivateAttr(
        default={"All": "All Prims", "Visible": "Visible Prims", "Hidden": "Hidden Prims"}
    )
    _COMBO_BOX_WIDTH: int = PrivateAttr(default=130)
    _visible_prims_combobox: ui.ComboBox | None = PrivateAttr(default=None)
    _current_attr: str | None = PrivateAttr(default=None)

    def filter_predicate(self, item: _StageManagerItem) -> bool:
        if self.visible_prims_type == "All Prims":
            return True

        imageable = UsdGeom.Imageable(item.data)
        if not imageable:
            return False

        is_visible = imageable.ComputeVisibility(Usd.TimeCode.Default()) != UsdGeom.Tokens.invisible
        if self.visible_prims_type == "Visible Prims":
            return bool(is_visible)
        if self.visible_prims_type == "Hidden Prims":
            return bool(not is_visible)
        return True

    def build_ui(self):
        with ui.HStack(spacing=ui.Pixel(8)):
            ui.Spacer(width=0)
            ui.Label(self.display_name, width=ui.Pixel(self._LABEL_WIDTH), alignment=ui.Alignment.RIGHT)
            self._visible_prims_combobox = ui.ComboBox(
                list(self._VISIBLE_PRIMS_DISPLAY_LABELS.values()).index(self.visible_prims_type),
                *self._VISIBLE_PRIMS_DISPLAY_LABELS.values(),
                width=ui.Pixel(self._COMBO_BOX_WIDTH),
            )
            self._visible_prims_combobox.model.add_item_changed_fn(self._on_visible_prims_type_changed)

    def _on_visible_prims_type_changed(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem"):
        selected_index = model.get_item_value_model().get_value_as_int()
        self.visible_prims_type = list(self._VISIBLE_PRIMS_DISPLAY_LABELS.values())[selected_index]
        self._current_attr = list(self._VISIBLE_PRIMS_DISPLAY_LABELS.keys())[selected_index]

        self._filter_items_changed()
