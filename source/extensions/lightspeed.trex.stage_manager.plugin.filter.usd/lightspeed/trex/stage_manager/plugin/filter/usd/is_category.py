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

from lightspeed.common.constants import REMIX_CATEGORIES_DISPLAY_NAMES as _REMIX_CATEGORIES_DISPLAY_NAMES
from omni import ui
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.stage_manager.plugin.filter.usd.base import StageManagerUSDFilterPlugin as _StageManagerUSDFilterPlugin
from pydantic import Field, PrivateAttr

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class IsCategoryFilterPlugin(_StageManagerUSDFilterPlugin):
    display_name: str = Field(default="Remix Category Filter", exclude=True)
    tooltip: str = Field(default="Filter prims by their assigned Render Categories", exclude=True)

    category_type: str = Field(
        default="All Categories", description="Whether to keep all categories or filter by category type."
    )

    _CATEGORY_DISPLAY_LABELS: dict = PrivateAttr(default={"All": "All Categories", **_REMIX_CATEGORIES_DISPLAY_NAMES})
    _COMBO_BOX_WIDTH: int = PrivateAttr(default=130)
    _cat_type_combobox: ui.ComboBox | None = PrivateAttr(default=None)
    _current_attr: str | None = PrivateAttr(default=None)

    def filter_predicate(self, item: _StageManagerItem) -> bool:
        if self.category_type == "All Categories":
            return True
        return any(attr.GetName() == self._current_attr and attr.Get() for attr in item.data.GetAttributes())

    def build_ui(self):
        with ui.HStack(spacing=ui.Pixel(8)):
            ui.Spacer(width=0)
            ui.Label(self.display_name, width=ui.Pixel(self._LABEL_WIDTH), alignment=ui.Alignment.RIGHT)
            self._cat_type_combobox = ui.ComboBox(
                list(self._CATEGORY_DISPLAY_LABELS.values()).index(self.category_type),
                *self._CATEGORY_DISPLAY_LABELS.values(),
                width=ui.Pixel(self._COMBO_BOX_WIDTH),
            )
            self._cat_type_combobox.model.add_item_changed_fn(self._on_cat_type_changed)

    def _on_cat_type_changed(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem"):
        selected_index = model.get_item_value_model().get_value_as_int()
        self.category_type = list(self._CATEGORY_DISPLAY_LABELS.values())[selected_index]
        self._current_attr = list(self._CATEGORY_DISPLAY_LABELS.keys())[selected_index]

        self._filter_items_changed()
