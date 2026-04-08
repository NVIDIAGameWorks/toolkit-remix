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

import re
from asyncio import ensure_future
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path

import carb
import omni.client
import omni.kit.app
import omni.kit.commands
import omni.kit.undo
import omni.usd
from lightspeed.common.constants import REGEX_HASH, REGEX_INSTANCE_PATH
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl
from omni.kit.usd.layers import LayerUtils
from pxr import Sdf

from .constants import LSS_LAYER_GAME_NAME
from .data_models import (
    GetLayerPathParamModel,
    GetLayersQueryModel,
    LayerManagerValidators,
    LayerModel,
    LayerResponseModel,
    LayerStackResponseModel,
    LayerType,
    LayerTypeKeys,
    OpenProjectPathParamModel,
)
from .layers import autoupscale, capture, capture_baker, i_layer, replacement, workfile


class LayerManagerCore:
    def __init__(self, context_name: str = ""):
        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self.context_name = context_name
        self.__context = omni.usd.get_context(context_name or "")
        # ILayer instances are lazy: built on first call to get_layer_instance()
        self.__layer_factories = {
            LayerType.capture: lambda: capture.CaptureLayer(self),
            LayerType.capture_baker: lambda: capture_baker.CaptureBakerLayer(self),
            LayerType.replacement: lambda: replacement.ReplacementLayer(self),
            LayerType.autoupscale: lambda: autoupscale.AutoUpscaleLayer(self),
            LayerType.workfile: lambda: workfile.WorkfileLayer(self),
        }
        self.__layer_cache: dict[LayerType, i_layer.ILayer] = {}

    # INTERNAL HELPERS

    def _require_layer_of_type(self, layer_type: LayerType, msg: str | None = None) -> "Sdf.Layer":
        """
        Return the top-most layer for *layer_type*, or raise ``ValueError`` if none exists.

        This is a convenience wrapper around ``get_layer_of_type()`` for call-sites that
        cannot proceed without the layer being present.

        Args:
            layer_type: The Remix layer type to look up.
            msg: Optional override for the exception message.
                 Defaults to ``'Can't find layer type "<value>" in the stage'``.

        Returns:
            The ``Sdf.Layer`` found for the given type.

        Raises:
            ValueError: If no layer of the given type is present in the current stage.
        """
        layer = self.get_layer_of_type(layer_type)
        if layer is None:
            raise ValueError(msg or f'Can\'t find layer type "{layer_type.value}" in the stage')
        return layer

    # DATA MODEL FUNCTIONS

    def get_loaded_project_with_data_models(self) -> LayerResponseModel:
        project_layer = self._require_layer_of_type(LayerType.workfile, "No project is currently loaded.")
        return LayerResponseModel(layer_id=project_layer.identifier)

    def open_project_with_data_models(self, params: OpenProjectPathParamModel):
        self.__context.open_stage(str(params.layer_id))

    def close_project_with_data_models(self, force: bool = False):
        # Return early if no stage is loaded
        if not self.__context.get_stage():
            return

        # Raise exception if there are unsaved changes and force is False
        if self.__context.has_pending_edit() and not force:
            raise ValueError(
                "The stage has pending changes. Please save the pending changes or "
                "set the force flag to True to discard the pending changes and close the project."
            )

        self.__context.close_stage()

    def get_layer_stack_with_data_models(self, query: GetLayersQueryModel) -> LayerStackResponseModel:
        if query.layer_types is not None:
            layers_dict = {}
            for layer_type in query.layer_types:
                layers_dict[layer_type] = self.get_layers_of_type(layer_type, max_results=query.layer_count)
            layer_models = [
                LayerModel(layer_id=layer.identifier, layer_type=layer_type, children=[])
                for layer_type, layers in layers_dict.items()
                for layer in layers
            ]
            return LayerStackResponseModel(layers=layer_models)

        def get_layer_info(layer: Sdf.Layer) -> LayerModel | None:
            if not layer:
                return None
            layer_type = layer.customLayerData.get(LayerTypeKeys.layer_type.value)
            children = [
                get_layer_info(sublayer)
                for sublayer_path in layer.subLayerPaths
                if (sublayer := Sdf.Layer.FindOrOpenRelativeToLayer(layer, sublayer_path))
            ]
            return LayerModel(layer_id=layer.identifier, layer_type=layer_type, children=children)

        return LayerStackResponseModel(layers=[get_layer_info(self.__context.get_stage().GetRootLayer())])

    @staticmethod
    def get_sublayers_with_data_models(
        params: GetLayerPathParamModel, query: GetLayersQueryModel
    ) -> LayerStackResponseModel:
        layer = Sdf.Layer.FindOrOpen(str(params.layer_id))
        if not layer:
            raise ValueError("The layer cannot be opened.")

        children = []
        for sublayer_path in layer.subLayerPaths:
            sublayer = Sdf.Layer.FindOrOpenRelativeToLayer(layer, sublayer_path)
            if not sublayer:
                continue
            sublayer_type = sublayer.customLayerData.get(LayerTypeKeys.layer_type.value)
            if sublayer_type:
                sublayer_type = LayerType(sublayer_type)
            if query.layer_types and sublayer_type not in query.layer_types:
                continue
            children.append(LayerModel(layer_id=sublayer.identifier, layer_type=sublayer_type, children=[]))

        return LayerStackResponseModel(layers=children)

    # TRADITIONAL FUNCTIONS

    def get_edit_target(self) -> Sdf.Layer:
        """
        Get the current edit target in the stage

        Returns:
            The current edit target layer
        """
        return self.__context.get_stage().GetEditTarget().GetLayer()

    def set_edit_target(self, layer_identifier: str | Path | OmniUrl):
        """
        Set the current edit target in the stage based on its identifier

        Args:
            layer_identifier: The layer identifier of the layer to set as edit target
        """
        omni.kit.commands.execute(
            "SetEditTarget", layer_identifier=str(layer_identifier), usd_context=self.context_name
        )

    def move_layer(
        self,
        layer_identifier: str | Path | OmniUrl,
        current_parent_layer_identifier: str | Path | OmniUrl,
        new_parent_layer_identifier: str | Path | OmniUrl = None,
        layer_index: int = 0,
    ):
        """
        Move a layer based on its subidentifier.

        Args:
            layer_identifier: The layer identifier of the layer to move
            current_parent_layer_identifier: The selected layer's current parent layer identifier
            new_parent_layer_identifier: The selected layer's new parent layer identifier
                                         If None, the current parent layer identifier will be used.
            layer_index: The index at which to move the layer. Can be -1 to insert at the end or a valid index.
        """
        current_parent_layer = LayerManagerCore._get_layer_or_raise(current_parent_layer_identifier)

        new_parent_layer = current_parent_layer
        if new_parent_layer_identifier:
            new_parent_layer = Sdf.Layer.FindOrOpen(str(new_parent_layer_identifier))
        current_index = LayerUtils.get_sublayer_position_in_parent(
            current_parent_layer.identifier, str(layer_identifier)
        )

        omni.kit.commands.execute(
            "MoveSublayer",
            from_parent_layer_identifier=current_parent_layer.identifier,
            from_sublayer_position=current_index,
            to_parent_layer_identifier=new_parent_layer.identifier,
            to_sublayer_position=layer_index,
            remove_source=True,
            usd_context=self.context_name,
        )

    def remove_layer(self, layer_identifier: str | Path | OmniUrl, parent_layer_identifier: str | Path | OmniUrl):
        """
        Remove a layer from the stage based on its identifier

        Args:
            layer_identifier: The layer identifier of the layer to remove
            parent_layer_identifier: The selected layer's parent layer identifier
        """
        omni.kit.commands.execute(
            "RemoveSublayer",
            layer_identifier=str(parent_layer_identifier),
            sublayer_position=LayerUtils.get_sublayer_position_in_parent(
                str(parent_layer_identifier), str(layer_identifier)
            ),
            usd_context=self.context_name,
        )

    def mute_layer(self, layer_identifier: str | Path | OmniUrl, value: bool):
        """
        Mute a layer in the current stage based on its identifier

        Args:
            layer_identifier: The layer identifier of the layer to mute
            value: Whether the layer should be muted or unmuted
        """
        omni.kit.commands.execute(
            "SetLayerMuteness",
            layer_identifier=str(layer_identifier),
            muted=value,
            usd_context=self.context_name,
        )

    def lock_layer(self, layer_identifier: str | Path | OmniUrl, value: bool):
        """
        Lock a layer in the current stage based on its identifier

        Args:
            layer_identifier: The layer identifier of the layer to lock
            value: Whether the layer should be locked or unlocked
        """
        omni.kit.commands.execute(
            "LockLayer", layer_identifier=str(layer_identifier), locked=value, usd_context=self.context_name
        )

    @staticmethod
    def _get_layer_or_raise(layer_identifier: str | Path | OmniUrl) -> Sdf.Layer:
        """
        Open and return the layer at ``layer_identifier``, or raise ValueError if it cannot be opened.

        Args:
            layer_identifier: File path or identifier of the layer to open.

        Returns:
            The opened Sdf.Layer.

        Raises:
            ValueError: If the layer cannot be found or opened.
        """
        layer = Sdf.Layer.FindOrOpen(str(layer_identifier))
        if not layer:
            raise ValueError(f'Can\'t find the layer with identifier "{layer_identifier}".')
        return layer

    @staticmethod
    def save_layer(layer_identifier: str | Path | OmniUrl, force: bool = False):
        """
        Save a layer in the current stage based on its identifier

        Args:
            layer_identifier: The layer identifier of the layer to save
            force: Whether to save the layer even if no changes were detected
        """
        LayerManagerCore._get_layer_or_raise(layer_identifier).Save(force=force)

    def _set_custom_layer_type_data_with_identifier(
        self,
        layer_identifier: str | Path | OmniUrl,
        layer_type: LayerType,
        layer: Sdf.Layer | None = None,
    ) -> dict | None:
        """
        Set a layer's custom data based on the Layer Type's pre-defined custom data.

        Args:
            layer_identifier: The layer identifier of the layer to update
            layer_type: The Layer Type of the selected layer
            layer: Already-open Sdf.Layer object. If provided, skips FindOrOpen.

        Returns:
             The custom layer data
        """
        if layer is None:
            layer = LayerManagerCore._get_layer_or_raise(layer_identifier)

        custom_layer_data = layer.customLayerData
        custom_layer_data.update({LayerTypeKeys.layer_type.value: layer_type.value})

        layer_inst = self.get_layer_instance(layer_type)
        custom_data_layer_inst = layer_inst.get_custom_layer_data()
        if custom_data_layer_inst:
            custom_layer_data.update(custom_data_layer_inst)

        layer.customLayerData = custom_layer_data
        layer.Save()

        return layer.customLayerData

    def get_layer_instance(self, layer_type: LayerType) -> i_layer.ILayer | None:
        """
        Return the ILayer subclass instance for the given Remix layer type.
        Instances are created lazily on first access.

        Args:
            layer_type: The Remix layer type whose instance to retrieve.

        Returns:
            The ILayer subclass instance, or None if the type is not registered.
        """
        if layer_type not in self.__layer_cache:
            factory = self.__layer_factories.get(layer_type)
            if factory is None:
                return None
            self.__layer_cache[layer_type] = factory()
        return self.__layer_cache[layer_type]

    def create_layer(
        self,
        path: str | Path | OmniUrl,
        layer_type: LayerType = None,
        set_edit_target: bool = False,
        sublayer_position: int = 0,
        parent_layer_identifier: str | Path | OmniUrl = None,
        replace_existing: bool = True,
        create_or_insert: bool = True,
        transfer_root_content: bool = False,
        do_undo: bool = True,
    ) -> Sdf.Layer | None:
        """
        Create or Insert a sublayer in the current stage

        Args:
            path: The Path or URL to the layer file to create/insert
            layer_type: The optional Layer Type
            set_edit_target: Set the Edit Target to the created layer after insertion
            sublayer_position: The index at which to create/insert the layer
            parent_layer_identifier: The selected layer's parent layer identifier
            replace_existing: Whether to replace any existing layer of the given layer_type or not.
                              Will only replace a layer if layer_type is also set
            create_or_insert: If True, create the layer, if False, insert an existing layer
            transfer_root_content: Transfer the content of the root layer to the created layer
            do_undo: Whether to use an undo group or not

        Returns:
            The newly created or inserted Sdf.Layer, or None if the layer could not be opened.
        """
        with omni.kit.undo.group() if do_undo else nullcontext():
            # Make sure the parent layer identifier is valid
            stage = self.__context.get_stage()
            if not parent_layer_identifier:
                parent_layer_identifier = stage.GetRootLayer().identifier

            # Before to create the layer, we check if there is no broken layer with the same name
            # The remove layer command doesn't handle layer that are declared but that don't exist on disk
            broken_stack = self.broken_layers_stack()
            for parent_broken_layer, broken_layer_path in broken_stack:
                # If we find a layer with the same name from the same parent and broken, we remove it.
                if str(path).endswith(Path(broken_layer_path).name):
                    self.remove_broken_layer(parent_broken_layer.identifier, broken_layer_path)

            # Remove any existing layer of type layer_type if replacing
            if replace_existing and layer_type:
                # If any parent layer is of type `layer_type`, raise a value error.
                # Otherwise, we remove the parent layer where the sublayer should be created before calling the command.
                if self._layer_type_in_stack(parent_layer_identifier, layer_type):
                    raise ValueError("Can't replace a layer of the same type as the parent layer.")
                self.remove_layers_of_type(layer_type, do_undo=False)

            # Create the sublayer
            success, new_layer_path = omni.kit.commands.execute(
                "CreateOrInsertSublayer",
                new_layer_path=str(path),
                layer_identifier=str(parent_layer_identifier),
                sublayer_position=sublayer_position,
                transfer_root_content=transfer_root_content,
                create_or_insert=create_or_insert,
                usd_context=self.context_name,
            )

            if not success:
                raise ValueError(f'An error occurred when creating the layer with identifier "{path}".')

            # Set the newly created sublayer as edit target
            if set_edit_target:
                self.set_edit_target(new_layer_path)

            # Update the newly created sublayer custom data to match the given layer type
            new_layer = Sdf.Layer.FindOrOpen(new_layer_path)
            if layer_type:
                if not new_layer:
                    raise ValueError(
                        f"Unable to update the created layer's metadata. "
                        f'Can\'t find the layer with identifier "{new_layer_path}".'
                    )
                try:
                    self._set_custom_layer_type_data_with_identifier(new_layer_path, layer_type, layer=new_layer)
                except ValueError as e:
                    raise ValueError(
                        f"Unable to update the created layer's metadata. "
                        f'Can\'t find the layer with identifier "{new_layer_path}".'
                    ) from e

            return new_layer

    def _layer_type_in_stack(self, layer_identifier: str, layer_type: LayerType) -> bool:
        """
        Get whether the layer or any of its parents are of type `layer_type`.

        Args:
            layer_identifier: The final layer in the stack to evaluate
            layer_type: The layer type to match

        Returns:
            Whether the layer type is found or not
        """

        def get_layer_stack(_layer: Sdf.Layer) -> list[Sdf.Layer]:
            _layer_stack = []
            if _layer is None:
                return _layer_stack
            if _layer.identifier == layer_identifier:
                _layer_stack.append(_layer)
            else:
                for sublayer_path in _layer.subLayerPaths:
                    sublayer_stack = get_layer_stack(Sdf.Layer.FindOrOpenRelativeToLayer(_layer, sublayer_path))
                    if sublayer_stack:
                        _layer_stack.append(_layer)
                        _layer_stack.extend(sublayer_stack)
                        break
            return _layer_stack

        root_layer = self.__context.get_stage().GetRootLayer()
        layer_stack = get_layer_stack(root_layer)

        return any(self.get_custom_data_layer_type(layer) == layer_type.value for layer in layer_stack)

    def broken_layers_stack(self) -> list[tuple[Sdf.Layer, str]]:
        """
        Return broken layers (like a layer in the stack but doesn't exist on the disk)

        Returns:
            A list of ``(parent_layer, broken_sublayer_path)`` tuples, where
            ``parent_layer`` is the Sdf.Layer that references the missing file,
            and ``broken_sublayer_path`` is the raw path string of the missing
            sublayer as recorded in the parent's ``subLayerPaths``.
        """
        result = []
        root_layer = self.__context.get_stage().GetRootLayer()
        for layer in LayerManagerValidators.iter_sublayer_tree(root_layer):
            for sublayer_path in layer.subLayerPaths:
                if not Sdf.Layer.FindOrOpenRelativeToLayer(layer, sublayer_path):
                    result.append((layer, sublayer_path))
        return result

    def remove_broken_layer(self, parent_layer_identifier: str, broken_layer: str) -> list[str]:
        """
        Remove a specific layer from a parent layer. Useful when we want to remove a layer that is not valid (for
        example a layer is set, but the layer doesn't exist on the disk)

        Args:
            parent_layer_identifier: the identifier of the layer we want to check sublayers from
            broken_layer: The sublayer path string (as it appears in the parent's
                          ``subLayerPaths``) of the missing layer to remove.

        Returns:
            List of removed layer path
        """
        result_list = []

        def ___cleaup_layers(layer):
            nonlocal result_list
            layer_edited = False
            sublayer_paths = layer.subLayerPaths.copy()
            invalid_paths = []
            children_layers = []
            for sublayer_path in sublayer_paths:
                if sublayer_path == broken_layer and parent_layer_identifier == layer.identifier:
                    invalid_paths.append(sublayer_path)
                    layer_edited = True
                # Make sure the sublayer path is pointing to a valid layer file
                sublayer = Sdf.Layer.FindOrOpenRelativeToLayer(layer, sublayer_path)
                if sublayer:
                    children_layers.append(sublayer)

            if layer_edited:
                result_list.extend(invalid_paths)
                for invalid_path in invalid_paths:
                    sublayer_paths.remove(invalid_path)

                layer.subLayerPaths = sublayer_paths

            for children_layer in children_layers:
                ___cleaup_layers(children_layer)

        root_layer = self.__context.get_stage().GetRootLayer()
        ___cleaup_layers(root_layer)
        return result_list

    @staticmethod
    def create_new_anonymous_layer() -> Sdf.Layer:
        """Create and return a new anonymous (in-memory, unsaved) Sdf.Layer."""
        return Sdf.Layer.CreateAnonymous()

    def save_layer_of_type(self, layer_type: LayerType, comment: str = None, show_checkpoint_error: bool = True):
        """
        Save a layer of the given type and create an Omniverse Nucleus checkpoint.

        Args:
            layer_type: The Remix layer type to save.
            comment: Checkpoint comment written to the Nucleus checkpoint record.
            show_checkpoint_error: If True, log an error when checkpoint
                                   creation fails. The layer save still succeeds.
        """
        layer = self.get_layer_of_type(layer_type)
        if layer is None:
            carb.log_error(f'Can\'t find the layer type "{layer_type.value}" in the stage')
            return
        LayerManagerCore.save_layer(layer.identifier)
        result, _ = omni.client.stat(layer.realPath)
        if result == omni.client.Result.OK:
            result, _ = omni.client.create_checkpoint(layer.realPath, "" if comment is None else comment, force=True)
            if result != omni.client.Result.OK and show_checkpoint_error:
                carb.log_error(f"Can't create a checkpoint for file {layer.realPath}")

    def save_layer_as(
        self, layer_type: LayerType, path: str, comment: str = None, show_checkpoint_error: bool = True
    ) -> bool:
        """
        Export a layer to a new file path and create an Omniverse Nucleus checkpoint.

        Creates the target file if it does not already exist, then exports the
        layer's content there and creates a checkpoint at the new path.

        Args:
            layer_type: The Remix layer type to export.
            path: Destination file path for the exported layer.
            comment: Checkpoint comment.
            show_checkpoint_error: If True, log an error when checkpoint creation fails.

        Returns:
            True if the export succeeded, False otherwise.
        """
        layer = self.get_layer_of_type(layer_type)
        if layer is None:
            carb.log_error(f'Can\'t find the layer type "{layer_type.value}" in the stage')
            return False
        existing_layer = Sdf.Layer.FindOrOpen(str(path))
        if not existing_layer:
            Sdf.Layer.CreateNew(path)
        if not layer.Export(path):
            carb.log_error(f'Failed to save layer type "{layer_type.value}" as {path}')
            return False
        result, _ = omni.client.stat(path)
        if result == omni.client.Result.OK:
            result, _ = omni.client.create_checkpoint(path, "" if comment is None else comment, force=True)
            if result != omni.client.Result.OK and show_checkpoint_error:
                # Not an error with saving, so still return True.
                carb.log_error(f"Can't create a checkpoint for file {path}")
        return True

    def get_layers_of_type(
        self, layer_type: LayerType | None, max_results: int = -1, find_muted_layers: bool = True
    ) -> list[Sdf.Layer]:
        """
        Get all layers of a given layer type.

        Args:
            layer_type: The type of layer to look for. None layer type is valid.
            max_results: The maximum number of results to return. Will quick return when the max is reached
            find_muted_layers: Whether to look in the stack of muted layers for the given layer type or not

        Returns:
            A list of layers with the given layer type
        """
        return LayerManagerValidators.get_layers_of_type(
            layer_type, max_results=max_results, context_name=self.context_name, find_muted_layers=find_muted_layers
        )

    def get_layer_of_type(self, layer_type: LayerType | None, find_muted_layers: bool = True) -> Sdf.Layer | None:
        """
        Get the top-most layer of a given layer type

        Args:
            layer_type: The type of layer to look for. None layer type is valid
            find_muted_layers: Whether to look in the stack of muted layers for the given layer type or not

        Returns:
            The top-most layer  with the given layer type if found, otherwise None
        """
        layers = self.get_layers_of_type(layer_type, max_results=1, find_muted_layers=find_muted_layers)
        if not layers:
            return None
        return layers[0]

    def get_replacement_layers(self) -> set[Sdf.Layer]:
        """
        Get all layers in the replacement layer tree.

        This method traverses the sublayer hierarchy starting from the replacement layer
        and returns all layers found. This is a workaround for sublayers created in the UI
        that do not receive the "replacement" layer type metadata.

        Note:
            This method may be removed in the future once sublayers properly inherit
            or receive the replacement layer type.

        Returns:
            A set containing the replacement layer and all its sublayers,
            or an empty set if no replacement layer exists.
        """
        layer = self.get_layer_of_type(LayerType.replacement)
        if not layer:
            return set()

        sub_layers = {layer}
        pending = [layer]

        while pending:
            new_layers = []
            for current_layer in pending:
                for child in current_layer.subLayerPaths:
                    child_layer = Sdf.Layer.FindRelativeToLayer(current_layer, child)
                    if child_layer is not None and child_layer not in sub_layers:
                        sub_layers.add(child_layer)
                        new_layers.append(child_layer)

            pending = new_layers

        return sub_layers

    @staticmethod
    def get_custom_data(layer: Sdf.Layer) -> dict[str, str]:
        """Return the customLayerData dict for the given Sdf.Layer."""
        return layer.customLayerData

    @staticmethod
    def set_custom_data_layer_type(layer: Sdf.Layer, layer_type: LayerType) -> dict:
        """
        Write the Remix layer type into a layer's customLayerData.

        Mutates ``layer.customLayerData`` in place and returns the updated dict.

        Args:
            layer: The Sdf.Layer to update.
            layer_type: The LayerType value to write under the ``lightspeed_layer_type`` key.

        Returns:
            The updated customLayerData dict.
        """
        custom_layer_data = layer.customLayerData
        custom_layer_data.update({LayerTypeKeys.layer_type.value: layer_type.value})
        layer.customLayerData = custom_layer_data
        return layer.customLayerData

    @staticmethod
    def get_custom_data_layer_type(layer: Sdf.Layer) -> str:
        """
        Read the Remix layer type string from a layer's customLayerData.

        Returns:
            The raw string value stored under the ``lightspeed_layer_type`` key,
            or None if the key is absent. This is a raw string, not a LayerType enum.
        """
        return layer.customLayerData.get(LayerTypeKeys.layer_type.value)

    def set_edit_target_layer_of_type(self, layer_type: LayerType, force_layer_identifier: str = None, do_undo=True):
        """
        Set the stage's Edit Target layer based on its type.

        If `force_layer_identifier` is provided it will be used instead of the layer type.

        WARNING: The last layer in the layer stack with the given `layer_type` will be set as edit target.
        If multiple layers share the same type, the bottom-most (last in stack order) is selected.

        Args:
            layer_type: The layer type used to find the layer to set as edit target.
                        Ignored if ``force_layer_identifier`` is provided.
            force_layer_identifier: Use this layer identifier instead of the layer type
            do_undo: Whether to use undo groups or not
        """
        if do_undo:
            omni.kit.undo.begin_group()
        layer_identifiers = (
            [force_layer_identifier]
            if force_layer_identifier is not None
            else [layer.identifier for layer in self.get_layers_of_type(layer_type, find_muted_layers=False)]
        )
        if layer_identifiers:
            self.set_edit_target(layer_identifiers[-1])
        if do_undo:
            omni.kit.undo.end_group()

    def lock_layers_of_type(self, layer_type: LayerType, value=True, do_undo=True):
        """
        Lock/Unlock all layers in the stage matching the given layer type.

        Args:
            layer_type: The layer type to lock
            value: Whether to lock or unlock the layer
            do_undo: Whether to use undo groups or not
        """
        if do_undo:
            omni.kit.undo.begin_group()
        for layer in self.get_layers_of_type(layer_type, find_muted_layers=False):
            self.lock_layer(layer.identifier, value)
        if do_undo:
            omni.kit.undo.end_group()

    def mute_layers_of_type(self, layer_type: LayerType, value: bool = True, do_undo: bool = True):
        """
        Mute/Unmute all layers in the stage matching the given layer type.

        Args:
            layer_type: The layer type to mute
            value: Whether to mute or unmute the layer
            do_undo: Whether to use undo groups or not
        """
        if do_undo:
            omni.kit.undo.begin_group()
        for layer in self.get_layers_of_type(layer_type, find_muted_layers=True):
            self.mute_layer(layer.identifier, value)
        if do_undo:
            omni.kit.undo.end_group()

    def remove_layers_of_type(self, layer_type: LayerType, do_undo=True):
        """
        Remove all layers in the stage matching the given layer type.

        Args:
            layer_type: The layer type to remove
            do_undo: Whether to use undo groups or not
        """
        if do_undo:
            omni.kit.undo.begin_group()
        for layer in self.__context.get_stage().GetLayerStack():
            if layer.expired:
                continue
            for sublayer_path in layer.subLayerPaths:
                sublayer = Sdf.Layer.FindOrOpenRelativeToLayer(layer, sublayer_path)
                if not sublayer:
                    continue
                if self.get_custom_data_layer_type(sublayer) == layer_type.value:
                    self.remove_layer(sublayer.identifier, layer.identifier)
        if do_undo:
            omni.kit.undo.end_group()

    @staticmethod
    def get_game_name_from_path(path: str) -> str:
        """
        Read the game name from a USD layer file's customLayerData without fully opening the stage.

        Opens the file with metadata-only mode (fast path — no prims loaded).

        Args:
            path: File path to the USD layer.

        Returns:
            The value of the ``lightspeed_game_name`` key, or ``"Unknown game"`` if absent.
        """
        layer = Sdf.Layer.OpenAsAnonymous(path, metadataOnly=True)
        default = "Unknown game"
        if not layer:
            return default
        return layer.customLayerData.get(LSS_LAYER_GAME_NAME, default)

    @staticmethod
    def get_layer_hashes_no_comp_arcs(layer: Sdf.Layer) -> dict[str, Sdf.Path]:
        """
        Collect hash-keyed prim paths from a single layer, ignoring composition arcs.

        Traverses only the given layer's own PrimSpecs (no references, payloads,
        or other composition arcs are followed). For prims whose path contains a
        hash identifier, the shortest matching prim path is recorded to make the
        result deterministic.

        Args:
            layer: The SdfLayer to traverse.

        Returns:
            A dict mapping hash string (e.g. ``"6CA2F12444DEBE09"``) to the
            shortest Sdf.Path of the matching prim in the layer.
        """

        def get_prims_recursive_no_comp_arcs(parents: list[Sdf.PrimSpec]):
            """
            Recursively collects PrimSpecs from ``parents`` within a single SdfLayer.
            Composition arcs (references, payloads, inherits, specializes) are not
            followed — only namespace children within the same layer are traversed.
            """
            prims = set()
            for prim in parents:
                prims.add(prim)
                prims = prims.union(get_prims_recursive_no_comp_arcs(prim.nameChildren))
            return prims

        hashes = {}
        regex_hash = re.compile(REGEX_HASH)
        regex_instance = re.compile(REGEX_INSTANCE_PATH)
        for prim in get_prims_recursive_no_comp_arcs(layer.rootPrims):
            match = regex_hash.match(str(prim.path))
            if not match:
                continue
            if regex_instance.match(str(prim.path)):
                continue
            # Always select the shortest path. This is an optimized way to make this function deterministic.
            # Otherwise, the order of the prim paths is not guaranteed, and we sometimes return:
            # - `/RootNode/meshes/mesh_6CA2F12444DEBE09/mesh` or `/RootNode/meshes/mesh_6CA2F12444DEBE09`
            # - `/RootNode/Looks/mat_8D1946B4993CE5A3/Shader` or `/RootNode/Looks/mat_8D1946B4993CE5A3`
            # etc.
            if match.group(3) not in hashes or len(str(prim.path)) < len(str(hashes[match.group(3)])):
                hashes[match.group(3)] = prim.path
        return hashes

    def open_stage(self, layer_identifier: str, callback: Callable[[], None] = None) -> str:
        """
        Schedule a USD stage open by file path using the USD context.

        The open is dispatched asynchronously via ``ensure_future`` so the
        call returns immediately and the stage may not yet be open when this
        method returns or when ``callback`` fires.

        Args:
            layer_identifier: The file path or URL of the stage to open.
            callback: Optional callable invoked immediately after scheduling
                the open (i.e. before the stage has finished loading).

        Returns:
            The identifier of the previously-open root layer, or None if no
            stage was open or the previous stage was anonymous.
        """
        # Obtain the previous stage root layer identifier if not anonymous
        if self.__context.get_stage():
            prev_stage_root_layer_identifier = self.__context.get_stage().GetRootLayer().identifier
            if "anon" in prev_stage_root_layer_identifier:
                prev_stage_root_layer_identifier = None
        else:
            prev_stage_root_layer_identifier = None

        ensure_future(self.__context.open_stage_async(layer_identifier))

        if callback:
            callback()

        return prev_stage_root_layer_identifier

    @staticmethod
    def is_valid_layer_type(file_path: str, layer_type: LayerType = None) -> bool:
        """
        Check whether a layer file has a valid Remix layer type.

        Args:
            file_path: Path to the USD layer file to inspect.
            layer_type: If provided, the file's layer type must match exactly.
                        If None, any recognised Remix LayerType is accepted.

        Returns:
            True if the layer exists and its customLayerData layer type matches
            the given ``layer_type`` (or any Remix LayerType if ``layer_type`` is
            None). False otherwise.
        """
        layer = Sdf.Layer.FindOrOpen(file_path)
        if not layer:
            return False
        input_layer_type = LayerManagerCore.get_custom_data_layer_type(layer)
        if input_layer_type is None:
            return False
        if layer_type is None:
            return any(input_layer_type == ltype.value for ltype in LayerType)
        return bool(input_layer_type == layer_type.value)

    def destroy(self):
        for layer_inst in self.__layer_cache.values():
            layer_inst.destroy()
        self.__layer_cache.clear()
        if self._default_attr:
            _reset_default_attrs(self)
