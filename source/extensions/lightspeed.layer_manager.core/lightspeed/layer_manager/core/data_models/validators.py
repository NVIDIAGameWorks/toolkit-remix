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

from pathlib import Path

import omni.usd
from lightspeed.common import constants
from omni.flux.layer_tree.usd.core import LayerCustomData
from omni.flux.utils.common.omni_url import OmniUrl
from pxr import Sdf, Tf

from .enums import LayerType, LayerTypeKeys


class LayerManagerValidators:
    @staticmethod
    def is_project_layer(layer_id: Path | None):
        """
        Validate that a layer file exists on disk and is typed as a workfile layer.

        Raises ValueError if the file does not exist or its ``lightspeed_layer_type``
        customLayerData key is not ``LayerType.workfile``.

        Returns:
            The unchanged ``layer_id`` on success (Pydantic field_validator contract).
        """
        layer = Sdf.Layer.FindOrOpen(str(layer_id))

        # Make sure the layer is in the currently opened project
        if not layer:
            raise ValueError(f"The layer does not exist: {layer_id}")

        if not layer.customLayerData.get(LayerTypeKeys.layer_type.value) == LayerType.workfile.value:
            raise ValueError(f"The layer is not a Project layer: {layer_id}")

        return layer_id

    @staticmethod
    def layer_is_in_project(layer_id: Path | None, context_name: str):
        """
        Validate that a layer is part of the currently loaded USD stage's sublayer tree.

        Accepts None for ``layer_id`` and passes validation without error (some
        Pydantic models make the layer optional; type enforcement is done at the
        model level).

        Raises ValueError if the layer cannot be opened or is not found in the
        stage's recursive sublayer hierarchy.

        Returns:
            The unchanged ``layer_id`` on success (Pydantic field_validator contract).
        """
        # In some cases the layer_id is optional. Is it does not exist we should pass validation
        # In other cases the pydantic typing will make sure the value is not None
        if layer_id is None:
            return layer_id

        try:
            layer = Sdf.Layer.FindOrOpen(str(layer_id))
        except Tf.ErrorException as e:
            raise ValueError(f"Unable to open the layer: {layer_id}") from e
        if not layer:
            raise ValueError(f"The layer does not exist: {layer_id}")

        # Make sure the layer is in the currently opened project
        root_layer = omni.usd.get_context(context_name).get_stage().GetRootLayer()
        layer_identifiers = [layer.identifier for layer in LayerManagerValidators.iter_sublayer_tree(root_layer)]
        if layer.identifier not in layer_identifiers:
            raise ValueError(f"The layer is not present in the loaded project's layer stack: {layer_id}")

        return layer_id

    @staticmethod
    def iter_sublayer_tree(layer: Sdf.Layer, _seen: set | None = None):
        """
        Yield ``layer`` and every valid sublayer reachable from it in DFS order.

        Sublayers that cannot be opened (broken paths) are silently skipped.
        Cycles in the layer graph are detected via ``_seen`` and skipped.
        This is a shared primitive used to avoid duplicating recursive layer-walk
        logic across multiple methods.
        """
        if _seen is None:
            _seen = set()
        if layer.identifier in _seen:
            return
        _seen.add(layer.identifier)
        yield layer
        for sublayer_path in layer.subLayerPaths:
            sublayer = Sdf.Layer.FindOrOpenRelativeToLayer(layer, sublayer_path)
            if sublayer:
                yield from LayerManagerValidators.iter_sublayer_tree(sublayer, _seen)

    @staticmethod
    def is_valid_index(index: int):
        """
        Validate that a sublayer position index is within bounds.

        Accepts -1 (append/end) or any non-negative integer.

        Raises ValueError if the index is less than -1.

        Returns:
            The unchanged ``index`` on success (Pydantic field_validator contract).
        """
        if index < -1:
            raise ValueError("The index should be a positive integer or -1")

        return index

    @staticmethod
    def can_create_layer(layer_path: Path, create_or_insert: bool):
        """
        Validate that a layer can be created or inserted at the given path.

        When creating (``create_or_insert=True``): path must have a USD extension
        and must not already exist on disk.
        When inserting (``create_or_insert=False``): the file must already exist
        and be openable as an Sdf.Layer.

        Raises ValueError describing the specific failure.

        Returns:
            The unchanged ``layer_path`` on success (Pydantic field_validator contract).
        """
        # Make sure the layer points to a USD file
        if OmniUrl(layer_path).suffix.lower() not in constants.USD_EXTENSIONS:
            raise ValueError(f"The layer path must point to a USD file: {layer_path}")

        # Make sure no files already exist at the location if creating the layer
        if create_or_insert:
            if OmniUrl(layer_path).exists:
                raise ValueError(f"A file already exists at the layer path: {layer_path}")
        # Make sure the layer is valid is inserting the layer
        elif not Sdf.Layer.FindOrOpen(str(layer_path)):
            raise ValueError(f"The layer does not exist: {layer_path}")

        return layer_path

    @classmethod
    def can_insert_sublayer(cls, layer_id: Path, context_name: str):
        """
        Validate that a sublayer can be inserted under the given layer.

        Accepts falsy ``layer_id`` and passes validation without error (some
        Pydantic models make the parent layer optional; type enforcement is
        done at the model level).

        Raises ValueError if the layer is of an excluded type (workfile or
        capture), has the ``EXCLUDE_ADD_CHILD`` metadata flag set, or is
        currently locked.

        Returns:
            The unchanged ``layer_id`` on success (Pydantic field_validator contract).
        """
        # In some cases the layer_id is optional. Is it does not exist we should pass validation
        # In other cases the pydantic typing will make sure the value is not None
        if not layer_id:
            return layer_id

        # Make sure the layer is allowed to have sublayers inserted
        if cls.__is_layer_excluded(
            layer_id, [LayerType.workfile, LayerType.capture], context_name=context_name
        ) or cls.__is_metadata_excluded(layer_id, LayerCustomData.EXCLUDE_ADD_CHILD):
            raise ValueError(f"Inserting a sublayer in the given layer is not allowed: {layer_id}")

        # Make sure the layer is not locked
        if omni.usd.is_layer_locked(omni.usd.get_context(context_name), Sdf.Layer.FindOrOpen(str(layer_id)).identifier):
            raise ValueError(f"The layer is locked: {layer_id}")

        return layer_id

    @classmethod
    def can_move_sublayer(cls, layer_id: Path, context_name: str):
        """
        Validate that a sublayer can be repositioned within its parent's sublayer list.

        Raises ValueError if the layer is of an excluded type (workfile, capture, or
        replacement), has the ``EXCLUDE_MOVE`` metadata flag set, or is currently locked.

        Returns:
            The unchanged ``layer_id`` on success (Pydantic field_validator contract).
        """
        # Make sure the layer is allowed to be moved
        if cls.__is_layer_excluded(
            layer_id, [LayerType.workfile, LayerType.capture, LayerType.replacement], context_name=context_name
        ) or cls.__is_metadata_excluded(layer_id, LayerCustomData.EXCLUDE_MOVE):
            raise ValueError(f"Moving the sublayer is not allowed: {layer_id}")

        # Make sure the layer is not locked
        if omni.usd.is_layer_locked(omni.usd.get_context(context_name), Sdf.Layer.FindOrOpen(str(layer_id)).identifier):
            raise ValueError(f"The layer is locked: {layer_id}")

        return layer_id

    @classmethod
    def can_delete_layer(cls, layer_id: Path, context_name: str):
        """
        Validate that a sublayer can be removed from the stage.

        Raises ValueError if the layer is of an excluded type (workfile, capture, or
        replacement) or has the ``EXCLUDE_REMOVE`` metadata flag set.

        Returns:
            The unchanged ``layer_id`` on success (Pydantic field_validator contract).
        """
        # Make sure the layer is allowed to be deleted
        if cls.__is_layer_excluded(
            layer_id,
            [LayerType.workfile, LayerType.capture, LayerType.replacement],
            context_name=context_name,
        ) or cls.__is_metadata_excluded(layer_id, LayerCustomData.EXCLUDE_REMOVE):
            raise ValueError(f"Deleting the sublayer is not allowed: {layer_id}")

        return layer_id

    @classmethod
    def can_mute_layer(cls, layer_id: Path, context_name: str):
        """
        Validate that a sublayer can be muted or unmuted.

        Raises ValueError if the layer is of an excluded type (workfile or capture)
        or has the ``EXCLUDE_MUTE`` metadata flag set.

        Returns:
            The unchanged ``layer_id`` on success (Pydantic field_validator contract).
        """
        # Make sure the layer is allowed to be muted
        if cls.__is_layer_excluded(
            layer_id, [LayerType.workfile, LayerType.capture], context_name=context_name
        ) or cls.__is_metadata_excluded(layer_id, LayerCustomData.EXCLUDE_MUTE):
            raise ValueError(f"Muting/Unmuting the sublayer is not allowed: {layer_id}")

        return layer_id

    @classmethod
    def can_lock_layer(cls, layer_id: Path, context_name: str):
        """
        Validate that a sublayer can be locked or unlocked.

        Raises ValueError if the layer is of an excluded type (workfile, capture, or
        replacement) or has the ``EXCLUDE_LOCK`` metadata flag set.

        Returns:
            The unchanged ``layer_id`` on success (Pydantic field_validator contract).
        """
        # Make sure the layer is allowed to be locked
        if cls.__is_layer_excluded(
            layer_id,
            [LayerType.workfile, LayerType.capture, LayerType.replacement],
            context_name=context_name,
        ) or cls.__is_metadata_excluded(layer_id, LayerCustomData.EXCLUDE_LOCK):
            raise ValueError(f"Locking/Unlocking the sublayer is not allowed: {layer_id}")

        return layer_id

    @classmethod
    def can_set_edit_target_layer(cls, layer_id: Path, context_name: str):
        """
        Validate that a sublayer can be set as the active USD edit target.

        Raises ValueError if the layer is of an excluded type (workfile or capture)
        or has the ``EXCLUDE_EDIT_TARGET`` metadata flag set.

        Returns:
            The unchanged ``layer_id`` on success (Pydantic field_validator contract).
        """
        # Make sure the layer is allowed to be set as edit target
        if cls.__is_layer_excluded(
            layer_id, [LayerType.workfile, LayerType.capture], context_name=context_name
        ) or cls.__is_metadata_excluded(layer_id, LayerCustomData.EXCLUDE_EDIT_TARGET):
            raise ValueError(f"Setting the sublayer as edit target is not allowed: {layer_id}")

        return layer_id

    @staticmethod
    def get_layers_of_type(
        layer_type: LayerType | None, max_results: int = -1, context_name: str = "", find_muted_layers: bool = True
    ) -> list[Sdf.Layer]:
        """
        Helper method used to find layers of a given type up to a certain number of results.

        Args:
            layer_type: The type of layer to look for. None layer type is valid.
            max_results: The maximum number of results to find before quick-returning
            context_name: The context name to use
            find_muted_layers: Whether to look for muted layers or not

        Returns:
            A list of all the layers matching the given layer_type
        """
        layers = []

        stage = omni.usd.get_context(context_name).get_stage()
        if stage is None:
            return layers

        for layer_identifier in omni.usd.get_all_sublayers(
            stage, include_session_layers=False, include_only_omni_layers=False, include_anonymous_layers=True
        ):
            if max_results >= 0 and max_results == len(layers):
                return layers

            if not find_muted_layers and stage.IsLayerMuted(layer_identifier):
                continue

            layer = Sdf.Layer.FindOrOpen(layer_identifier)
            if not layer:
                continue

            if layer.customLayerData.get(LayerTypeKeys.layer_type.value) == (
                layer_type.value if layer_type is not None else None
            ):
                layers.append(layer)

        return layers

    @classmethod
    def __is_layer_excluded(cls, layer_id: Path, excluded_types: list[LayerType], context_name: str):
        exclude_identifiers = []

        for excluded_type in excluded_types:
            excluded_layers = LayerManagerValidators.get_layers_of_type(
                excluded_type, max_results=1, context_name=context_name
            )
            if not excluded_layers:
                continue
            exclude_identifiers.append(OmniUrl(excluded_layers[0].identifier).path)

        return OmniUrl(layer_id).path in exclude_identifiers

    @classmethod
    def __is_metadata_excluded(cls, layer_id: Path, metadata_key: LayerCustomData):
        layer = Sdf.Layer.FindOrOpen(str(layer_id))

        custom_data = layer.customLayerData.get(LayerCustomData.ROOT.value, {})
        if not custom_data:
            return False

        return custom_data.get(metadata_key.value, False)
