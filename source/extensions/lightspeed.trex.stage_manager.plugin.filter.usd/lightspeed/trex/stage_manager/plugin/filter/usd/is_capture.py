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

__all__ = ["IsCaptureFilterPlugin", "ReferenceType"]

from enum import Enum
from typing import TYPE_CHECKING

from lightspeed.layer_manager.core import LayerManagerCore
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementCore
from lightspeed.trex.utils.common import prim_utils
from omni import ui
from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.stage_manager.plugin.filter.usd.base import StageManagerUSDFilterPlugin
from pxr import Usd
from pydantic import Field, PrivateAttr

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel


class ReferenceType(Enum):
    ALL = "all"
    CAPTURED = "captured"
    REPLACED = "replaced"
    DELETED = "deleted"


class IsCaptureFilterPlugin(StageManagerUSDFilterPlugin):
    display_name: str = Field(default="Asset State", exclude=True)
    tooltip: str = Field(default="Filter by prim reference type (captured, replaced, or deleted)", exclude=True)

    reference_type: ReferenceType = Field(
        default=ReferenceType.ALL,
        description="Whether to keep captured, replaced, deleted, or all references when filtering",
    )

    _REFERENCE_TYPE_LABELS: dict = PrivateAttr(
        default={
            ReferenceType.ALL: "All",
            ReferenceType.CAPTURED: "Captured",
            ReferenceType.REPLACED: "Replaced",
            ReferenceType.DELETED: "Deleted",
        }
    )
    _COMBO_BOX_WIDTH: int = PrivateAttr(default=130)

    _layer_manager: LayerManagerCore = PrivateAttr()
    _ref_type_combobox: ui.ComboBox | None = PrivateAttr(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._layer_manager = LayerManagerCore(self._context_name)

    def __del__(self):
        if self._layer_manager is not None:
            self._layer_manager.destroy()
            self._layer_manager = None
        if self._ref_type_combobox is not None:
            self._ref_type_combobox = None

    def filter_predicate(self, item: StageManagerItem) -> bool:
        match self.reference_type:
            case ReferenceType.ALL:
                return True
            case ReferenceType.CAPTURED:
                return _AssetReplacementCore.prim_is_from_a_capture_reference(item.data)
            case ReferenceType.REPLACED:
                return not _AssetReplacementCore.prim_is_from_a_capture_reference(item.data)
            case ReferenceType.DELETED:
                return self._is_deleted_prim(item.data)
        return False

    def _is_deleted_prim(self, prim: Usd.Prim) -> bool:
        """Return True when *prim* originated from a capture reference that has been removed.

        Two variants qualify:
        * **Ghost prim** -- a valid, typeless instance child whose prototype
          no longer exists.
        * **Ref-edited prim** -- no deletable capture references remain on the
          prim or its ancestors, but the replacement layer still contains
          reference-list edits (e.g. an explicitly emptied list).
        """
        if not _AssetReplacementCore.prim_is_from_a_capture_reference(prim):
            return False

        if prim_utils.is_ghost_prim(prim):
            return True

        _, refs = prim_utils.find_prim_with_references(prim)
        if refs:
            return False

        return prim_utils.has_replacement_ref_edits(prim, self._layer_manager.get_replacement_layers())

    def build_ui(self):
        with ui.HStack(spacing=ui.Pixel(8), tooltip=self.tooltip):
            ui.Spacer(width=0)
            ui.Label(self.display_name, width=ui.Pixel(self._LABEL_WIDTH), alignment=ui.Alignment.RIGHT)
            self._ref_type_combobox = ui.ComboBox(
                list(self._REFERENCE_TYPE_LABELS.keys()).index(self.reference_type),
                *self._REFERENCE_TYPE_LABELS.values(),
                width=ui.Pixel(self._COMBO_BOX_WIDTH),
            )
            self._ref_type_combobox.model.add_item_changed_fn(self._on_ref_type_changed)

    def _on_ref_type_changed(self, model: "StageManagerTreeModel", item: "StageManagerTreeItem"):
        selected_index = model.get_item_value_model().get_value_as_int()
        self.reference_type = list(self._REFERENCE_TYPE_LABELS.keys())[selected_index]

        self._filter_items_changed()
