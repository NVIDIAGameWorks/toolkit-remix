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

from enum import Enum
from typing import TYPE_CHECKING

from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementCore
from omni import ui
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.stage_manager.plugin.filter.usd.base import StageManagerUSDFilterPlugin as _StageManagerUSDFilterPlugin
from pydantic import Field, PrivateAttr

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class ReferenceType(Enum):
    ALL = "all"
    CAPTURED = "captured"
    REPLACED = "replaced"


class IsCaptureFilterPlugin(_StageManagerUSDFilterPlugin):
    display_name: str = "Prim Reference Type"
    tooltip: str = "Filter by prim reference type (captured or replaced)"

    reference_type: ReferenceType = Field(
        ReferenceType.ALL, description="Whether to keep captured, replaced, or all references when filtering"
    )

    _REFERENCE_TYPE_LABELS: dict = PrivateAttr(
        {
            ReferenceType.ALL: "All References",
            ReferenceType.CAPTURED: "Captured Only",
            ReferenceType.REPLACED: "Replaced Only",
        }
    )
    _COMBO_BOX_WIDTH: int = PrivateAttr(130)

    _ref_type_combobox: ui.ComboBox | None = PrivateAttr(None)

    def filter_predicate(self, item: _StageManagerItem) -> bool:
        match self.reference_type:
            case ReferenceType.ALL:
                return True
            case ReferenceType.CAPTURED:
                return _AssetReplacementCore.prim_is_from_a_capture_reference(item.data)
            case ReferenceType.REPLACED:
                return not _AssetReplacementCore.prim_is_from_a_capture_reference(item.data)
        return False

    def build_ui(self):
        with ui.HStack(spacing=ui.Pixel(8)):
            ui.Label(self.display_name, width=0)
            self._ref_type_combobox = ui.ComboBox(
                list(self._REFERENCE_TYPE_LABELS.keys()).index(self.reference_type),
                *self._REFERENCE_TYPE_LABELS.values(),
                width=ui.Pixel(self._COMBO_BOX_WIDTH),
            )
            self._ref_type_combobox.model.add_item_changed_fn(self._on_ref_type_changed)

    def _on_ref_type_changed(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem"):
        selected_index = model.get_item_value_model().get_value_as_int()
        self.reference_type = list(self._REFERENCE_TYPE_LABELS.keys())[selected_index]

        self._filter_items_changed()
