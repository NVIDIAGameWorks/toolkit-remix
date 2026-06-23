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

__all__ = ["FilterTypes", "RemixLogicPrimsFilterPlugin"]

from enum import Enum
from typing import ClassVar

from lightspeed.common.constants import OMNI_GRAPH_NODE_TYPES, OMNI_GRAPH_TYPE
from omni import ui
from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.stage_manager.plugin.filter.usd.base import StageManagerUSDFilterPlugin
from pydantic import Field, PrivateAttr


class FilterTypes(Enum):
    NO_FILTERS = "No Filter"
    GRAPHS_ONLY = "Graphs Only"
    GRAPHS_AND_NODES = "Graphs + Nodes"


class RemixLogicPrimsFilterPlugin(StageManagerUSDFilterPlugin):
    _filter_active_fields: ClassVar[tuple[str, ...]] = ("current_filter_type",)

    display_name: str = Field(default="Remix Logic", exclude=True)
    tooltip: str = Field(
        default=(
            "Filter Remix Logic prims.\n\n"
            "Options:\n"
            "- No Filter: Show every prim.\n"
            "- Graphs Only: Show only OmniGraph graph prims.\n"
            "- Graphs + Nodes: Show OmniGraph graph and node prims."
        ),
        exclude=True,
    )

    _filter_combobox: ui.ComboBox | None = PrivateAttr(default=None)
    current_filter_type: FilterTypes = Field(
        default=FilterTypes.NO_FILTERS, description="The type of logic to filter by"
    )

    def _refresh_filter_active(self) -> None:
        self.filter_active = self.current_filter_type != FilterTypes.NO_FILTERS

    def filter_predicate(self, item: StageManagerItem) -> bool:
        match self.current_filter_type:
            case FilterTypes.GRAPHS_ONLY:
                return item.data.GetTypeName() == OMNI_GRAPH_TYPE
            case FilterTypes.GRAPHS_AND_NODES:
                return item.data.GetTypeName() in OMNI_GRAPH_NODE_TYPES
        return True

    def build_ui(self) -> None:
        filter_labels = [each.value for each in FilterTypes]
        with ui.HStack(spacing=ui.Pixel(8), tooltip=self.tooltip):
            ui.Spacer(width=0)
            ui.Label(
                self.display_name,
                width=ui.Pixel(self._LABEL_WIDTH),
                alignment=ui.Alignment.RIGHT,
            )
            self._filter_combobox = ui.ComboBox(
                list(FilterTypes).index(self.current_filter_type),
                *filter_labels,
            )
            self._filter_combobox.model.add_item_changed_fn(self._on_filter_changed)

    def _on_filter_changed(self, model: ui.AbstractItemModel, _: ui.AbstractItem) -> None:
        selected_index = model.get_item_value_model().get_value_as_int()
        self.current_filter_type = list(FilterTypes)[selected_index]
        self._filter_items_changed()
