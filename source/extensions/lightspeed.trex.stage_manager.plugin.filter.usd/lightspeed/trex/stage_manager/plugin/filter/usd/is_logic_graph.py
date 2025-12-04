"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["RemixLogicPrimsFilterPlugin"]

from typing import TYPE_CHECKING

from lightspeed.common.constants import OMNI_GRAPH_NODE_TYPE, OMNI_GRAPH_TYPE
from omni import ui
from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.stage_manager.plugin.filter.usd.base import StageManagerUSDFilterPlugin
from pydantic import Field, PrivateAttr

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel

_filter_types = ["No Filter", "Graphs Only", "Graphs + Nodes"]


class RemixLogicPrimsFilterPlugin(StageManagerUSDFilterPlugin):
    display_name: str = Field(default="Remix Logic", exclude=True)
    tooltip: str = Field(default="Filters For Remix Logic", exclude=True)

    _COMBO_BOX_WIDTH: int = PrivateAttr(default=130)
    _filter_combobox: ui.ComboBox | None = PrivateAttr(default=None)
    _current_index: int = PrivateAttr(default=0)

    def filter_predicate(self, item: StageManagerItem) -> bool:
        match self._current_index:
            case 1:
                return item.data.GetTypeName() == OMNI_GRAPH_TYPE
            case 2:
                return item.data.GetTypeName() in {OMNI_GRAPH_TYPE, OMNI_GRAPH_NODE_TYPE}
        return True

    def build_ui(self) -> None:
        with ui.HStack(spacing=ui.Pixel(8)):
            ui.Spacer(width=0)
            ui.Label(
                self.display_name,
                width=ui.Pixel(self._LABEL_WIDTH),
                alignment=ui.Alignment.RIGHT,
            )
            self._filter_combobox = ui.ComboBox(
                self._current_index,
                *_filter_types,
                width=ui.Pixel(self._COMBO_BOX_WIDTH),
            )
            self._filter_combobox.model.add_item_changed_fn(self._on_filter_changed)

    def _on_filter_changed(self, model: "StageManagerTreeModel", _: "StageManagerTreeItem") -> None:
        selected_index = model.get_item_value_model().get_value_as_int()
        self._current_index = selected_index
        self._filter_items_changed()
