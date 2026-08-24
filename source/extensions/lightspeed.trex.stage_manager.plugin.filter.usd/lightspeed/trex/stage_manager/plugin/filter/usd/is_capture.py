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

from collections.abc import Callable
from enum import Enum
from functools import partial
from typing import TYPE_CHECKING, ClassVar

from lightspeed.layer_manager.core import LayerManagerCore
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementCore
from lightspeed.trex.utils.common import prim_utils
from omni import ui
from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.stage_manager.plugin.filter.usd.base import StageManagerUSDFilterPlugin
from pxr import Sdf, Usd
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
    _filter_active_fields: ClassVar[tuple[str, ...]] = ("reference_type",)

    display_name: str = Field(default="Asset State", exclude=True)
    tooltip: str = Field(
        default=(
            "Filter by prim reference type.\n\n"
            "Options:\n"
            "- All: Show every prim.\n"
            "- Captured: Show prims that still reference captured assets.\n"
            "- Replaced: Show prims using replacement assets instead of captured references.\n"
            "- Deleted: Show captured prims whose reference was removed."
        ),
        exclude=True,
    )

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

    _layer_manager: LayerManagerCore = PrivateAttr()
    _ref_type_combobox: ui.ComboBox | None = PrivateAttr(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._layer_manager = LayerManagerCore(self._context_name)

    def set_context_name(self, name: str) -> None:
        """Bind replacement-layer access to a USD context.

        Args:
            name: USD context name.
        """
        if name == self._context_name:
            return
        self._layer_manager.destroy()
        super().set_context_name(name)
        self._layer_manager = LayerManagerCore(name)

    @staticmethod
    def _is_deleted_capture_prim(
        prim: Usd.Prim,
        capture_layer_cache: dict[str, bool] | None,
        replacement_layers: set[Sdf.Layer] | Callable[[], set[Sdf.Layer]],
    ) -> bool:
        """Return whether a capture-origin prim has had its captured reference removed.

        Args:
            prim: Prim to classify.
            capture_layer_cache: Optional caller-owned read-through cache keyed by each layer's exact ``realPath``.
                Cache misses are added in place; ``None`` uses uncached traversal.
            replacement_layers: Replacement layers or a callback that returns them.

        Returns:
            Whether the prim is a deleted capture prim.
        """
        if not _AssetReplacementCore.prim_is_from_a_capture_reference(prim, capture_layer_cache):
            return False

        if prim_utils.is_ghost_prim(prim):
            return True

        _, references = prim_utils.find_prim_with_references(prim)
        if references:
            return False

        if callable(replacement_layers):
            replacement_layers = replacement_layers()
        return prim_utils.has_replacement_ref_edits(prim, replacement_layers)

    def _refresh_filter_active(self) -> None:
        self.filter_active = self.reference_type != ReferenceType.ALL

    def __del__(self):
        if self._layer_manager is not None:
            self._layer_manager.destroy()
            self._layer_manager = None
        if self._ref_type_combobox is not None:
            self._ref_type_combobox = None

    def filter_predicate(
        self,
        item: StageManagerItem,
        capture_layer_cache: dict[str, bool] | None = None,
        replacement_layers: set[Sdf.Layer] | None = None,
    ) -> bool:
        """Return whether an item matches the selected Asset State filter.

        Args:
            item: Stage Manager item to evaluate.
            capture_layer_cache: Optional caller-owned capture-layer cache.
            replacement_layers: Optional refresh-local replacement-layer snapshot.

        Returns:
            Whether the item matches the selected reference type.
        """
        match self.reference_type:
            case ReferenceType.ALL:
                return True
            case ReferenceType.CAPTURED:
                return _AssetReplacementCore.prim_is_from_a_capture_reference(item.data, capture_layer_cache)
            case ReferenceType.REPLACED:
                return not _AssetReplacementCore.prim_is_from_a_capture_reference(item.data, capture_layer_cache)
            case ReferenceType.DELETED:
                replacement_layers_source: set[Sdf.Layer] | Callable[[], set[Sdf.Layer]]
                if replacement_layers is None:
                    replacement_layers_source = self._layer_manager.get_replacement_layers
                else:
                    replacement_layers_source = replacement_layers
                return self._is_deleted_capture_prim(
                    item.data,
                    capture_layer_cache,
                    replacement_layers_source,
                )
        return False

    def build_filter_predicate(self) -> Callable[[StageManagerItem], bool]:
        """Build an Asset State predicate with refresh-local caches and replacement layers.

        Returns:
            Predicate that evaluates a Stage Manager item against the prepared Asset State data.
        """
        replacement_layers = (
            self._layer_manager.get_replacement_layers() if self.reference_type == ReferenceType.DELETED else None
        )
        return partial(
            self.filter_predicate,
            capture_layer_cache={},
            replacement_layers=replacement_layers,
        )

    def build_ui(self):
        with ui.HStack(spacing=ui.Pixel(8), tooltip=self.tooltip):
            ui.Spacer(width=0)
            ui.Label(self.display_name, width=ui.Pixel(self._LABEL_WIDTH), alignment=ui.Alignment.RIGHT)
            self._ref_type_combobox = ui.ComboBox(
                list(self._REFERENCE_TYPE_LABELS.keys()).index(self.reference_type),
                *self._REFERENCE_TYPE_LABELS.values(),
            )
            self._ref_type_combobox.model.add_item_changed_fn(self._on_ref_type_changed)

    def _on_ref_type_changed(self, model: "StageManagerTreeModel", item: "StageManagerTreeItem"):
        selected_index = model.get_item_value_model().get_value_as_int()
        self.reference_type = list(self._REFERENCE_TYPE_LABELS.keys())[selected_index]

        self._filter_items_changed()
