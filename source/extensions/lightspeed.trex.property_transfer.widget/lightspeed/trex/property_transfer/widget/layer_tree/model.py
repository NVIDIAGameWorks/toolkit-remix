"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from collections.abc import Iterable, Mapping, Sequence

from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.layer_manager.core import LayerTypeKeys as _LayerTypeKeys
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from omni.flux.layer_tree.usd.widget import LayerModel as _LayerModel
from pxr import Sdf

from .state import OpinionState


class _PropertyTransferLayerModel(_LayerModel):
    def __init__(self, context_name: str, specs_by_path: Mapping[Sdf.Path, Sequence[Sdf.Spec]]):
        """Create the property-transfer layer tree model.

        Args:
            context_name: USD context name containing the layer stack.
            specs_by_path: Transfer specs grouped by their authored USD path.
        """
        super().__init__(context_name)
        self._layer_manager = _LayerManagerCore(context_name)
        self._valid_target_layer_identifiers: set[str] = set()
        self._layer_opinion_states = self._collect_layer_opinion_states(specs_by_path)

    @property
    def default_attr(self) -> dict[str, None]:
        """Get attributes reset during model destruction.

        Returns:
            Mapping of attribute names to their reset values.
        """
        default_attr = super().default_attr
        default_attr.update(
            {"_layer_manager": None, "_valid_target_layer_identifiers": None, "_layer_opinion_states": None}
        )
        return default_attr

    def destroy(self):
        """Destroy owned layer manager resources before destroying the tree model."""
        if self._layer_manager is not None:
            self._layer_manager.destroy()
        super().destroy()

    @property
    def valid_target_layer_identifiers(self) -> set[str]:
        """Get currently selectable transfer target layer identifiers.

        Returns:
            Set of unlocked replacement-layer identifiers.
        """
        return self._valid_target_layer_identifiers

    def get_item_value_model_count(self, _item) -> int:
        """Get the number of columns shown in the transfer layer tree.

        Args:
            _item: Ignored layer-tree item.

        Returns:
            Number of value columns exposed by the model.
        """
        return 2

    async def _deferred_refresh(self):
        self._refresh_valid_target_layer_identifiers()
        await super()._deferred_refresh()

    def can_transfer_specs_to_layer(
        self, target_layer_identifier: str, spec_groups: Iterable[Sequence[Sdf.Spec]]
    ) -> bool:
        """Return whether any pending spec group can transfer to the target layer.

        Args:
            target_layer_identifier: Candidate transfer target layer identifier.
            spec_groups: Source spec groups still requiring transfer.

        Returns:
            True if the target is valid and at least one source group can transfer.
        """
        self._refresh_valid_target_layer_identifiers()
        if not target_layer_identifier or target_layer_identifier not in self._valid_target_layer_identifiers:
            return False
        return any(
            self._layer_manager.can_transfer_from_layers(
                (spec.layer.identifier for spec in specs if spec is not None),
                self._valid_target_layer_identifiers,
            )
            for specs in spec_groups
        )

    def get_layer_opinion_state(self, layer_identifier: str) -> OpinionState | None:
        """Get the transfer state for a layer identifier.

        Args:
            layer_identifier: Layer identifier to inspect.

        Returns:
            Opinion state when the transfer spec is authored on the layer, otherwise ``None``.
        """
        return self._layer_opinion_states.get(layer_identifier)

    def _create_layer_items(
        self,
        layer: Sdf.Layer,
        is_root: bool,
        parent_allows_child_rename: bool,
        excluded_layers: dict,
        dirty_layers: set,
        edit_target_layer_identifier: str,
        layers_state,
    ):
        layer_item, is_authoring = super()._create_layer_items(
            layer,
            is_root,
            parent_allows_child_rename,
            excluded_layers,
            dirty_layers,
            edit_target_layer_identifier,
            layers_state,
        )
        layer = layer_item.data.get("layer") if layer_item.data else None
        layer_item.enabled = bool(layer and layer.identifier in self._valid_target_layer_identifiers)
        if not layer_item.enabled and layer_item.data is not None:
            layer_item.data["disabled_tooltip"] = self._get_invalid_target_tooltip(layer_item, is_root)
        return layer_item, is_authoring

    def _refresh_valid_target_layer_identifiers(self) -> None:
        self._valid_target_layer_identifiers = {
            layer.identifier for layer in self._layer_manager.get_valid_transfer_target_layers()
        }

    @staticmethod
    def _collect_layer_opinion_states(
        specs_by_path: Mapping[Sdf.Path, Sequence[Sdf.Spec]],
    ) -> dict[str, OpinionState]:
        states = {}
        for specs in specs_by_path.values():
            if not specs:
                continue
            strongest_layer_identifier = specs[0].layer.identifier
            for spec in specs:
                state = (
                    OpinionState.STRONGEST
                    if spec.layer.identifier == strongest_layer_identifier
                    else OpinionState.WEAKER
                )
                if states.get(spec.layer.identifier) is not OpinionState.STRONGEST:
                    states[spec.layer.identifier] = state
        return states

    @staticmethod
    def _get_invalid_target_tooltip(layer_item, is_root: bool) -> str:
        layer = layer_item.data.get("layer") if layer_item.data else None
        layer_type = layer.customLayerData.get(_LayerTypeKeys.layer_type.value) if layer else None
        if not (is_root or layer_type == _LayerType.capture.value) and layer_item.data.get("locked"):
            return "This layer is locked. Transfer targets must be unlocked."
        return "Select the replacement layer or one of its sublayers."
