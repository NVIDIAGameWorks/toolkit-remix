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

__all__ = ["RepairLayerCore"]

from collections.abc import Callable

import omni.client
import omni.kit.usd.layers as _layers
import omni.usd
from lightspeed.layer_manager.core.data_models import LayerType, LayerTypeKeys
from omni.flux.layer_tree.usd.core import LayerCustomData
from omni.flux.utils.common import path_utils
from omni.flux.utils.common.omni_url import OmniUrl
from pxr import Sdf

from .enum import PackagingRepairProgress
from .models import RepairState


class RepairLayerCore:
    """
    Layer lookup, copy, save, reload, and local layer helpers for packaging repairs.
    """

    def __init__(self, context_name: str = ""):
        """Initialize the layer helper.

        Args:
            context_name: USD context name used to inspect dirty layer state and root layer identity.
        """
        self._context_name = context_name

    def raise_if_layers_dirty(self):
        """Raise when any live USD layer has unsaved edits.

        Raises:
            RuntimeError: If the current layer stack has pending edits.
        """
        context = omni.usd.get_context(self._context_name)
        layers_state = _layers.get_layers(context).get_layers_state() if context else _layers.get_layers_state()
        if layers_state.get_dirty_layer_identifiers():
            raise RuntimeError("Save pending layer edits before applying packaging repairs.")

    def get_root_layer_identifier(self) -> str | None:
        """Get the current stage root layer identifier.

        Returns:
            The root layer identifier, or ``None`` when no stage is open.
        """
        context = omni.usd.get_context(self._context_name)
        stage = context.get_stage() if context else None
        if not stage:
            return None
        root_layer = stage.GetRootLayer()
        if root_layer and isinstance(root_layer.identifier, str):
            return root_layer.identifier
        layer_stack = stage.GetLayerStack()
        return layer_stack[0].identifier if layer_stack else None

    @staticmethod
    def compute_absolute_path_from_identifier(layer_identifier: str, asset_path: str) -> str:
        """Resolve an asset path against a layer identifier.

        Args:
            layer_identifier: Identifier for the layer that authored the asset path.
            asset_path: Authored asset path to resolve.

        Returns:
            The normalized absolute asset path, or an empty string when ``asset_path`` is empty.
        """
        if not asset_path:
            return ""

        layer = Sdf.Layer.Find(layer_identifier)
        if layer:
            return path_utils.get_absolute_path_from_relative(asset_path, layer)
        if path_utils.is_absolute_path(asset_path):
            return omni.client.normalize_url(asset_path).replace("\\", "/")

        return omni.client.normalize_url(
            omni.client.combine_urls(OmniUrl(layer_identifier).parent_url, asset_path)
        ).replace("\\", "/")

    @staticmethod
    def _open_layer_copy(layer_identifier: str) -> Sdf.Layer | None:
        source_layer = Sdf.Layer.FindOrOpen(layer_identifier)
        if not source_layer:
            return None

        # Worker repairs mutate anonymous layers only. Live stage layers are checked clean before export and reloaded
        # after save, avoiding worker-thread Sdf authoring against the composed stage.
        layer_copy = Sdf.Layer.CreateAnonymous()
        layer_copy.TransferContent(source_layer)
        return layer_copy

    @classmethod
    def get_read_layer(cls, state: RepairState, layer_identifier: str | None) -> Sdf.Layer | None:
        """Open a layer for read access and cache it in the repair state.

        Args:
            state: The active repair state.
            layer_identifier: Identifier for the layer to open.

        Returns:
            The opened layer, or ``None`` when it cannot be opened.
        """
        if not layer_identifier:
            return None

        layer_key = OmniUrl(layer_identifier).path.lower()
        read_layers = state.read_layers
        if layer_key in read_layers:
            return read_layers[layer_key]

        layer = (
            cls._open_layer_copy(layer_identifier)
            if state.use_editable_layer_copies
            else Sdf.Layer.FindOrOpen(layer_identifier)
        )
        if layer:
            read_layers[layer_key] = layer
        return layer

    @classmethod
    def get_editable_layer(cls, state: RepairState, layer_identifier: str | None) -> Sdf.Layer:
        """Open an editable layer for repair authoring.

        Args:
            state: The active repair state.
            layer_identifier: Identifier for the layer to edit.

        Returns:
            The editable layer or anonymous editable copy.

        Raises:
            RuntimeError: If no editable layer can be resolved.
        """
        if not layer_identifier:
            raise RuntimeError("Unable to resolve an editable layer for the unresolved asset repair")
        editable_layers = state.editable_layers
        if editable_layers is None:
            layer = Sdf.Layer.FindOrOpen(layer_identifier)
            if not layer:
                raise RuntimeError(f"Unable to open layer '{layer_identifier}'")
            return layer

        layer_key = OmniUrl(layer_identifier).path.lower()
        editable_layer_entry = editable_layers.get(layer_key)
        if editable_layer_entry:
            return editable_layer_entry[1]

        editable_layer = cls._open_layer_copy(layer_identifier)
        if not editable_layer:
            raise RuntimeError(f"Unable to open editable copy for layer '{layer_identifier}'")
        editable_layers[layer_key] = (layer_identifier, editable_layer)
        return editable_layer

    @classmethod
    def save_editable_layers(
        cls,
        state: RepairState,
        progress_callback: Callable[[int, int, PackagingRepairProgress], None] | None = None,
    ) -> bool:
        """Save dirty editable layers from the repair state.

        Args:
            state: The active repair state.
            progress_callback: Optional callback receiving current item count, total item count, and progress state.

        Returns:
            Whether the save step completed.

        Raises:
            RuntimeError: If a live target layer is dirty or export fails.
        """
        editable_layers = state.editable_layers
        if not editable_layers:
            return True

        dirty_layer_keys = state.dirty_editable_layer_keys
        layers_to_save = [
            editable_layer_entry
            for layer_key, editable_layer_entry in editable_layers.items()
            if layer_key in dirty_layer_keys
        ]
        if not layers_to_save:
            return True

        total_layers = max(len(layers_to_save), 1)
        if progress_callback:
            progress_callback(0, total_layers, PackagingRepairProgress.SAVING)

        # Finish all dirty exports once saving starts so cancellation cannot leave a partial repair set on disk.
        for index, (layer_identifier, editable_layer) in enumerate(layers_to_save, start=1):
            live_layer = Sdf.Layer.Find(layer_identifier)
            if live_layer and live_layer.dirty is True:
                raise RuntimeError("Save pending layer edits before applying packaging repairs.")
            if not editable_layer.Export(layer_identifier):
                raise RuntimeError(f"Unable to save repaired layer '{layer_identifier}'")
            if progress_callback:
                progress_callback(index, total_layers, PackagingRepairProgress.SAVING)

        return True

    @classmethod
    def reload_saved_layers(cls, state: RepairState):
        """Reload saved live layers after worker-thread repair export.

        Args:
            state: The completed repair state.
        """
        editable_layers = state.editable_layers
        if not editable_layers:
            return

        for layer_key, (layer_identifier, _) in editable_layers.items():
            if layer_key not in state.dirty_editable_layer_keys:
                continue
            layer = Sdf.Layer.Find(layer_identifier)
            if layer:
                layer.Reload()

    def get_local_layers(self, state: RepairState) -> dict[str, tuple[str, Sdf.Layer]]:
        """Get local layer-stack layers reachable from the repair root layer.

        Args:
            state: The active repair state.

        Returns:
            Mapping of normalized layer keys to layer identifiers and layers.
        """
        if state.local_layers is not None:
            return state.local_layers

        local_layers: dict[str, tuple[str, Sdf.Layer]] = {}
        pending_layer_identifiers = [state.root_layer_identifier] if state.root_layer_identifier else []

        while pending_layer_identifiers:
            if state.is_cancelled_requested():
                return local_layers
            layer_identifier = pending_layer_identifiers.pop()
            if not layer_identifier:
                continue
            layer_key = OmniUrl(layer_identifier).path.lower()
            if layer_key in local_layers:
                continue
            layer = self.get_read_layer(state, layer_identifier)
            if not layer:
                continue
            local_layers[layer_key] = (layer_identifier, layer)
            try:
                sublayer_paths = list(layer.subLayerPaths)
            except TypeError:
                sublayer_paths = []
            for sublayer_path in reversed(sublayer_paths):
                pending_layer_identifiers.append(
                    self.compute_absolute_path_from_identifier(layer_identifier, sublayer_path)
                )

        state.local_layers = local_layers
        return local_layers

    @staticmethod
    def is_repair_layer_blocked(layer: Sdf.Layer) -> bool:
        """Check whether a layer is protected from repair authoring.

        Args:
            layer: The layer to inspect.

        Returns:
            Whether repairs should skip the layer.
        """
        custom_layer_data = layer.customLayerData if isinstance(layer.customLayerData, dict) else {}
        layer_type = custom_layer_data.get(LayerTypeKeys.layer_type.value)
        if layer_type in {LayerType.workfile.value, LayerType.capture.value, LayerType.capture_baker.value}:
            return True

        custom_data = custom_layer_data.get(LayerCustomData.ROOT.value, {})
        return custom_data.get(LayerCustomData.EXCLUDE_EDIT_TARGET.value, False)
