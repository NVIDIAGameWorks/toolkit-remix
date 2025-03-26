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

import asyncio
import re
from contextlib import nullcontext
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

import carb
import omni.client
import omni.kit.app
import omni.kit.commands
import omni.kit.undo
import omni.kit.window.file
import omni.usd
from lightspeed.common.constants import CAPTURE_FOLDER, REGEX_HASH, REGEX_INSTANCE_PATH, REMIX_CAPTURE_FOLDER
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl
from omni.kit.usd.layers import LayerUtils
from pxr import Sdf

from .constants import LSS_LAYER_GAME_NAME
from .data_models import (
    CreateLayerRequestModel,
    DeleteLayerPathParamModel,
    DeleteLayerRequestModel,
    GetLayerPathParamModel,
    GetLayersQueryModel,
    LayerManagerValidators,
    LayerModel,
    LayerResponseModel,
    LayerStackResponseModel,
    LayerType,
    LayerTypeKeys,
    LockLayerPathParamModel,
    LockLayerRequestModel,
    MoveLayerPathParamModel,
    MoveLayerRequestModel,
    MuteLayerPathParamModel,
    MuteLayerRequestModel,
    OpenProjectPathParamModel,
    SaveLayerPathParamModel,
    SetEditTargetPathParamModel,
)
from .layers import autoupscale, capture, capture_baker, i_layer, replacement, workfile


class LayerManagerCore:
    def __init__(self, context_name: str = ""):
        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self.context_name = context_name
        self.__context = omni.usd.get_context(context_name or "")
        self.__capture_layer = capture.CaptureLayer(self)
        self.__capture_baker_layer = capture_baker.CaptureBakerLayer(self)
        self.__replacement_layer = replacement.ReplacementLayer(self)
        self.__autoupscale_layer = autoupscale.AutoUpscaleLayer(self)
        self.__workfile_layer = workfile.WorkfileLayer(self)
        self.__layers = [
            self.__capture_layer,
            self.__capture_baker_layer,
            self.__replacement_layer,
            self.__autoupscale_layer,
            self.__workfile_layer,
        ]

    # DATA MODEL FUNCTIONS

    def get_loaded_project_with_data_models(self) -> LayerResponseModel:
        project_layer = self.get_layer(LayerType.workfile)
        if not project_layer:
            raise ValueError("No project is currently loaded.")
        return LayerResponseModel(layer_id=project_layer.identifier)

    def open_project_with_data_models(self, params: OpenProjectPathParamModel):
        self.__context.open_stage(str(params.layer_id))

    def get_layer_stack_with_data_models(self, query: GetLayersQueryModel) -> LayerStackResponseModel:
        if query.layer_types is not None:
            layers_dict = {}
            for layer_type in query.layer_types:
                layers_dict[layer_type] = self.get_layers(layer_type, max_results=query.layer_count)
            layer_models = []
            for layer_type, layers in layers_dict.items():
                for layer in layers:
                    layer_models.append(LayerModel(layer_id=layer.identifier, layer_type=layer_type, children=[]))
            return LayerStackResponseModel(layers=layer_models)

        def get_layer_info(layer: Sdf.Layer) -> Optional[LayerModel]:
            if not layer:
                return None
            layer_type = layer.customLayerData.get(LayerTypeKeys.layer_type.value)
            children = []
            for sublayer_path in layer.subLayerPaths:
                sublayer = Sdf.Layer.FindOrOpenRelativeToLayer(layer, sublayer_path)
                if not sublayer:
                    continue
                children.append(get_layer_info(sublayer))
            return LayerModel(layer_id=layer.identifier, layer_type=layer_type, children=children)

        return LayerStackResponseModel(layers=[get_layer_info(self.__context.get_stage().GetRootLayer())])

    def get_sublayers_with_data_models(
        self, params: GetLayerPathParamModel, query: GetLayersQueryModel
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

    def create_layer_with_data_model(self, body: CreateLayerRequestModel):
        self.create_layer(
            body.layer_path,
            layer_type=body.layer_type,
            set_edit_target=body.set_edit_target,
            sublayer_position=body.sublayer_position,
            parent_layer_identifier=body.parent_layer_id,
            create_or_insert=body.create_or_insert,
            replace_existing=body.replace_existing,
        )

    def get_edit_target_with_data_model(self) -> LayerResponseModel:
        return LayerResponseModel(layer_id=self.get_edit_target().identifier)

    def set_edit_target_with_data_model(self, params: SetEditTargetPathParamModel):
        self.set_edit_target_with_identifier(params.layer_id)

    def move_layer_with_data_model(self, params: MoveLayerPathParamModel, body: MoveLayerRequestModel):
        self.move_layer_with_identifier(
            params.layer_id,
            body.current_parent_layer_id,
            new_parent_layer_identifier=body.new_parent_layer_id,
            layer_index=body.layer_index,
        )

    def remove_layer_with_data_model(self, params: DeleteLayerPathParamModel, body: DeleteLayerRequestModel):
        self.remove_layer_with_identifier(params.layer_id, body.parent_layer_id)

    def mute_layer_with_data_model(self, params: MuteLayerPathParamModel, body: MuteLayerRequestModel):
        self.mute_layer_with_identifier(params.layer_id, body.value)

    def lock_layer_with_data_model(self, params: LockLayerPathParamModel, body: LockLayerRequestModel):
        self.lock_layer_with_identifier(params.layer_id, body.value)

    def save_layer_with_data_model(self, params: SaveLayerPathParamModel):
        self.save_layer_with_identifier(params.layer_id)

    # TRADITIONAL FUNCTIONS

    def get_edit_target(self) -> Sdf.Layer:
        """
        Get the current edit target in the stage

        Returns:
            The current edit target layer
        """
        return self.__context.get_stage().GetEditTarget().GetLayer()

    def set_edit_target_with_identifier(self, layer_identifier: Union[str, Path, OmniUrl]):
        """
        Set the current edit target in the stage based on its identifier

        Args:
            layer_identifier: The layer identifier of the layer to set as edit target
        """
        omni.kit.commands.execute(
            "SetEditTarget", layer_identifier=str(layer_identifier), usd_context=self.context_name
        )

    def move_layer_with_identifier(
        self,
        layer_identifier: Union[str, Path, OmniUrl],
        current_parent_layer_identifier: Union[str, Path, OmniUrl],
        new_parent_layer_identifier: Union[str, Path, OmniUrl] = None,
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
        current_parent_layer = Sdf.Layer.FindOrOpen(str(current_parent_layer_identifier))

        if not current_parent_layer:
            raise ValueError(f'Can\'t find the parent layer with identifier "{current_parent_layer_identifier}".')

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

    def remove_layer_with_identifier(
        self, layer_identifier: Union[str, Path, OmniUrl], parent_layer_identifier: Union[str, Path, OmniUrl]
    ):
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

    def mute_layer_with_identifier(self, layer_identifier: Union[str, Path, OmniUrl], value: bool):
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

    def lock_layer_with_identifier(self, layer_identifier: Union[str, Path, OmniUrl], value: bool):
        """
        Lock a layer in the current stage based on its identifier

        Args:
            layer_identifier: The layer identifier of the layer to lock
            value: Whether the layer should be locked or unlocked
        """
        omni.kit.commands.execute(
            "LockLayer", layer_identifier=str(layer_identifier), locked=value, usd_context=self.context_name
        )

    def save_layer_with_identifier(self, layer_identifier: Union[str, Path, OmniUrl], force: bool = False):
        """
        Save a layer in the current stage based on its identifier

        Args:
            layer_identifier: The layer identifier of the layer to save
            force: Whether to save the layer even if no changes were detected
        """
        layer = Sdf.Layer.FindOrOpen(str(layer_identifier))

        if not layer:
            raise ValueError(f'Can\'t find the layer with identifier "{layer_identifier}".')

        layer.Save(force=force)

    def set_custom_layer_type_data_with_identifier(
        self, layer_identifier: Union[str, Path, OmniUrl], layer_type: LayerType
    ) -> Optional[Dict]:
        """
        Set a layer's custom data based on the Layer Type's pre-defined custom data.

        Args:
            layer_identifier: The layer identifier of the layer to update
            layer_type: The Layer Type of the selected layer

        Returns:
             The custom layer data
        """
        layer = Sdf.Layer.FindOrOpen(str(layer_identifier))

        if not layer:
            raise ValueError(f'Can\'t find the layer with identifier "{layer_identifier}".')

        custom_layer_data = layer.customLayerData
        custom_layer_data.update({LayerTypeKeys.layer_type.value: layer_type.value})

        layer_inst = self.get_layer_instance(layer_type)
        custom_data_layer_inst = layer_inst.get_custom_layer_data()
        if custom_data_layer_inst:
            custom_layer_data.update(custom_data_layer_inst)

        layer.customLayerData = custom_layer_data
        layer.Save()

        return layer.customLayerData

    def get_layer_instance(self, layer_type: LayerType) -> Optional[i_layer.ILayer]:
        for layer_obj in self.__layers:
            if layer_obj.layer_type == layer_type:
                return layer_obj
        return None

    def create_layer(
        self,
        path: Union[str, Path, OmniUrl],
        layer_type: LayerType = None,
        set_edit_target: bool = False,
        sublayer_position: int = 0,
        parent_layer_identifier: Union[str, Path, OmniUrl] = None,
        replace_existing: bool = True,
        create_or_insert: bool = True,
        transfer_root_content: bool = False,
        do_undo: bool = True,
    ):
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
        """
        with omni.kit.undo.group() if do_undo else nullcontext():
            # Make sure the parent layer identifier is valid
            stage = self.__context.get_stage()
            if not parent_layer_identifier:
                parent_layer_identifier = stage.GetRootLayer().identifier
            parent_layer = Sdf.Layer.FindOrOpen(str(parent_layer_identifier))
            if not parent_layer:
                raise ValueError(f'Can\'t find the parent layer with identifier "{parent_layer_identifier}".')

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
                if self.layer_type_in_stack(parent_layer_identifier, layer_type):
                    raise ValueError("Can't replace a layer of the same type as the parent layer.")
                self.remove_layer(layer_type, do_undo=False)

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
                self.set_edit_target_with_identifier(new_layer_path)

            # Update the newly created sublayer custom data to match the given layer type
            if layer_type:
                try:
                    self.set_custom_layer_type_data_with_identifier(new_layer_path, layer_type)
                except ValueError as e:
                    raise ValueError(
                        f"Unable to update the created layer's metadata. "
                        f'Can\'t find the layer with identifier "{path}".'
                    ) from e

    def layer_type_in_stack(self, layer_identifier: str, layer_type: LayerType) -> bool:
        """
        Get whether the layer or any of its parents are of type `layer_type`.

        Args:
            layer_identifier: The final layer in the stack to evaluate
            layer_type: The layer type to match

        Returns:
            Whether the layer type is found or not
        """

        def get_layer_stack(_layer: Sdf.Layer) -> List[Sdf.Layer]:
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
            Tuple of the broken layers + the parent like: (parent layer, broken layer)
        """

        result = []

        def get_layer_stack(_layer: Sdf.Layer) -> List[Sdf.Layer]:
            _layer_stack = []
            for sublayer_path in _layer.subLayerPaths:
                sdf_layer = Sdf.Layer.FindOrOpenRelativeToLayer(_layer, sublayer_path)
                if sdf_layer:
                    _layer_stack.extend(get_layer_stack(sdf_layer))
                else:
                    _layer_stack.append((_layer, sublayer_path))

            return _layer_stack

        root_layer = self.__context.get_stage().GetRootLayer()
        result.extend(get_layer_stack(root_layer))

        return result

    def remove_broken_layer(self, parent_layer_identifier: str, broken_layer: str) -> list[str]:
        """
        Remove a specific layer from a parent layer. Useful when we want to remove a layer that is not valid (for
        example a layer is set, but the layer doesn't exist on the disk)

        Args:
            parent_layer_identifier: the identifier of the layer we want to check sublayers from
            broken_layer: the name of the layer to check

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

    def create_new_sublayer(
        self,
        layer_type: LayerType,
        path: str = None,
        set_as_edit_target: bool = True,
        sublayer_create_position: int = 0,
        parent_layer: Optional[Sdf.Layer] = None,
        do_undo: bool = True,
        replace_existing: bool = True,
    ):
        """
        WARNING: This function is deprecated, use `create_layer` instead.
        """
        omni.kit.app.log_deprecation(
            "The function `LayerManagerCore.create_new_sublayer` is deprecated. "
            "Use `LayerManagerCore.create_layer` instead."
        )
        if do_undo:
            omni.kit.undo.begin_group()
        for layer_obj in self.__layers:  # noqa R503
            if layer_obj.layer_type == layer_type:
                layer = layer_obj.create_sublayer(
                    path=path,
                    sublayer_create_position=sublayer_create_position,
                    parent_layer=parent_layer,
                    do_undo=False,
                    replace_existing=replace_existing,
                )
                if set_as_edit_target:
                    self.set_edit_target_layer(
                        layer_obj.layer_type, force_layer_identifier=layer.identifier, do_undo=False
                    )
                if do_undo:
                    omni.kit.undo.end_group()
                return layer
        if do_undo:
            omni.kit.undo.end_group()
        return None

    def insert_sublayer(
        self,
        path,
        layer_type: LayerType,
        set_as_edit_target: bool = True,
        sublayer_insert_position=-1,
        add_custom_layer_data=True,
        parent_layer=None,
        do_undo=True,
    ):
        """
        WARNING: This function is deprecated, use `create_layer` instead.
        """
        omni.kit.app.log_deprecation(
            "The function `LayerManagerCore.insert_sublayer` is deprecated. "
            "Use `LayerManagerCore.create_layer` instead."
        )
        if do_undo:
            omni.kit.undo.begin_group()
        stage = self.__context.get_stage()
        if parent_layer is None:
            parent_layer = stage.GetRootLayer()
        success, new_layer_path = omni.kit.commands.execute(
            "CreateOrInsertSublayer",
            layer_identifier=parent_layer.identifier,
            sublayer_position=sublayer_insert_position,
            new_layer_path=path,
            transfer_root_content=False,
            create_or_insert=False,
            layer_name="",
            usd_context=self.__context,
        )
        if success:
            for layer in stage.GetLayerStack():
                if omni.client.normalize_url(layer.realPath) == omni.client.normalize_url(new_layer_path):
                    # add customData
                    if add_custom_layer_data:
                        custom_layer_data = layer.customLayerData
                        custom_layer_data.update({LayerTypeKeys.layer_type.value: layer_type.value})
                        layer_inst = self.get_layer_instance(layer_type)
                        custom_data_layer_inst = layer_inst.get_custom_layer_data()
                        if custom_data_layer_inst:
                            custom_layer_data.update(custom_data_layer_inst)
                        layer.customLayerData = custom_layer_data
                        layer.Save()  # because of new customLayerData
                    if set_as_edit_target:
                        self.set_edit_target_layer(layer_type, force_layer_identifier=layer.identifier, do_undo=False)
                    if do_undo:
                        omni.kit.undo.end_group()
                    return layer
        if do_undo:
            omni.kit.undo.end_group()
        return None

    @staticmethod
    def create_new_anonymous_layer() -> Sdf.Layer:
        return Sdf.Layer.CreateAnonymous()

    def save_layer(self, layer_type: LayerType, comment: str = None, show_checkpoint_error: bool = True):
        layer = self.get_layer(layer_type)
        if layer is None:
            carb.log_error(f'Can\'t find the layer type "{layer_type.value}" in the stage')
            return
        self.save_layer_with_identifier(layer.identifier)
        result, _ = omni.client.stat(layer.realPath)
        if result == omni.client.Result.OK:
            result, _ = omni.client.create_checkpoint(layer.realPath, "" if comment is None else comment, force=True)
            if result != omni.client.Result.OK and show_checkpoint_error:
                carb.log_error(f"Can't create a checkpoint for file {layer.realPath}")

    def save_layer_as(
        self, layer_type: LayerType, path: str, comment: str = None, show_checkpoint_error: bool = True
    ) -> bool:
        layer = self.get_layer(layer_type)
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

    def get_layers(
        self, layer_type: LayerType | None, max_results: int = -1, find_muted_layers: bool = True
    ) -> List[Sdf.Layer]:
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

    def get_layer(self, layer_type: LayerType | None, find_muted_layers: bool = True) -> Optional[Sdf.Layer]:
        """
        Get the top-most layer of a given layer type

        Args:
            layer_type: The type of layer to look for. None layer type is valid
            find_muted_layers: Whether to look in the stack of muted layers for the given layer type or not

        Returns:
            The top-most layer  with the given layer type if found, otherwise None
        """
        layers = self.get_layers(layer_type, max_results=1, find_muted_layers=find_muted_layers)
        if not layers:
            return None
        return layers[0]

    @staticmethod
    def get_custom_data(layer: Sdf.Layer) -> Dict[str, str]:
        return layer.customLayerData

    @staticmethod
    def set_custom_data_layer_type(layer: Sdf.Layer, layer_type: LayerType) -> Dict:
        custom_layer_data = layer.customLayerData
        custom_layer_data.update({LayerTypeKeys.layer_type.value: layer_type.value})
        layer.customLayerData = custom_layer_data
        return layer.customLayerData

    @staticmethod
    def get_custom_data_layer_type(layer: Sdf.Layer) -> str:
        return layer.customLayerData.get(LayerTypeKeys.layer_type.value)

    def set_edit_target_layer(self, layer_type: LayerType, force_layer_identifier: str = None, do_undo=True):
        """
        Set the stage's Edit Target layer based on its type.

        If `force_layer_identifier` is provided it will be used instead of the layer type.

        WARNING: The last texture in the Layer Stack with the given `layer_type` will be set as edit target.

        Args:
            layer_type: The layer type to remove
            force_layer_identifier: Use this layer identifier instead of the layer type
            do_undo: Whether to use undo groups or not
        """
        if do_undo:
            omni.kit.undo.begin_group()
        layer_identifiers = (
            [force_layer_identifier]
            if force_layer_identifier is not None
            else [layer.identifier for layer in self.get_layers(layer_type, find_muted_layers=False)]
        )
        if layer_identifiers:
            self.set_edit_target_with_identifier(layer_identifiers[-1])
        if do_undo:
            omni.kit.undo.end_group()

    def lock_layer(self, layer_type: LayerType, value=True, do_undo=True):
        """
        Lock/Unlock all layer in the stage matching the given layer type.

        Args:
            layer_type: The layer type to lock
            value: Whether to lock or unlock the layer
            do_undo: Whether to use undo groups or not
        """
        if do_undo:
            omni.kit.undo.begin_group()
        for layer in self.get_layers(layer_type, find_muted_layers=False):
            self.lock_layer_with_identifier(layer.identifier, value)
        if do_undo:
            omni.kit.undo.end_group()

    def mute_layer(self, layer_type: LayerType, value: bool = True, do_undo: bool = True):
        """
        Mute/Unmute all layer in the stage matching the given layer type.

        Args:
            layer_type: The layer type to mute
            value: Whether to mute or unmute the layer
            do_undo: Whether to use undo groups or not
        """
        if do_undo:
            omni.kit.undo.begin_group()
        for layer in self.get_layers(layer_type, find_muted_layers=True):
            self.mute_layer_with_identifier(layer.identifier, value)
        if do_undo:
            omni.kit.undo.end_group()

    def remove_layer(self, layer_type: LayerType, do_undo=True):
        """
        Remove all layer in the stage matching the given layer type.

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
                    self.remove_layer_with_identifier(sublayer.identifier, layer.identifier)
        if do_undo:
            omni.kit.undo.end_group()

    @staticmethod
    def get_game_name_from_path(path: str) -> str:
        layer = Sdf.Layer.OpenAsAnonymous(path, metadataOnly=True)
        default = "Unknown game"
        if not layer:
            return default
        return layer.customLayerData.get(LSS_LAYER_GAME_NAME, default)

    def game_current_game_capture_folder(self, show_error: bool = True) -> Tuple[Optional[str], Optional[str]]:
        """Get the current capture folder from the current capture layer"""
        layer = self.get_layer(LayerType.capture)
        # we only save stage that have a replacement layer
        if not layer:
            if show_error:
                carb.log_error("Can't find the capture layer in the current stage")
            return None, None
        capture_folder = Path(layer.realPath)
        if capture_folder.parent.name not in [CAPTURE_FOLDER, REMIX_CAPTURE_FOLDER]:
            if show_error:
                carb.log_error(
                    f'Can\'t find the "{CAPTURE_FOLDER}" or "{REMIX_CAPTURE_FOLDER}" folder from the capture layer'
                )
            return None, None
        return self.get_game_name_from_path(layer.realPath), str(capture_folder.parent)

    def get_layer_hashes_no_comp_arcs(self, layer: Sdf.Layer) -> Dict[str, Sdf.Path]:
        """
        This function does not take in consideration the layer composition arcs.
        It only evaluates the given layer and no sub-layers.

        Args:
            layer: The layer to traverse

        Returns:
            A dictionary of the various hashes found and their respective prims
        """

        def get_prims_recursive_no_comp_arcs(parents: List[Sdf.PrimSpec]):
            """
            Composition Arcs are not taken in consideration when fetching the prims.
            The prims will therefore all belong to the same layer but prims in
            sub-layers will be ignored.
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
        # Obtain the previous stage root layer identifier if not anonymous
        if self.__context.get_stage():
            prev_stage_root_layer_identifier = self.__context.get_stage().GetRootLayer().identifier
            if "anon" in prev_stage_root_layer_identifier:
                prev_stage_root_layer_identifier = None
        else:
            prev_stage_root_layer_identifier = None

        omni.kit.window.file.open_stage(layer_identifier)
        if callback:
            callback()

        return prev_stage_root_layer_identifier

    def create_new_stage(self) -> str:
        # Obtain the previous stage root layer identifier if not anonymous
        prev_stage_root_layer_identifier = self.__context.get_stage().GetRootLayer().identifier
        if "anon" in prev_stage_root_layer_identifier:
            prev_stage_root_layer_identifier = None

        self.__context.new_stage_with_callback(self._on_new_stage_created)

        return prev_stage_root_layer_identifier

    def _on_new_stage_created(self, result: bool, error: str):
        asyncio.ensure_future(self._deferred_startup(self.__context))

    @omni.usd.handle_exception
    async def _deferred_startup(self, context):
        """Or crash"""
        await omni.kit.app.get_app_interface().next_update_async()
        await context.new_stage_async()
        await omni.kit.app.get_app_interface().next_update_async()
        stage = context.get_stage()
        while (context.get_stage_state() in [omni.usd.StageState.OPENING, omni.usd.StageState.CLOSING]) or not stage:
            await asyncio.sleep(0.1)
        # set some metadata
        root_layer = stage.GetRootLayer()
        self.set_custom_data_layer_type(root_layer, LayerType.workfile)

    def is_valid_layer_type(self, file_path: str, layer_type: LayerType = None) -> bool:
        """Check if layer type is of the given type or a Remix layer type."""
        layer = Sdf.Layer.FindOrOpen(file_path)
        if not layer:
            return False
        input_layer_type = self.get_custom_data_layer_type(layer)
        if input_layer_type is None:
            return False
        if input_layer_type and input_layer_type != layer_type.value:
            return False
        if not layer_type and input_layer_type:
            return any(input_layer_type == ltype.value for ltype in LayerType)
        return True

    def destroy(self):
        if self._default_attr:
            _reset_default_attrs(self)
