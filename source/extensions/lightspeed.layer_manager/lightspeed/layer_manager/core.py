"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import carb
import omni.client
import omni.kit.commands
import omni.kit.undo
import omni.usd
from lightspeed.common.constants import CAPTURE_FOLDER, REGEX_HASH, REGEX_INSTANCE_PATH, REMIX_CAPTURE_FOLDER
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.usd.layers import LayerUtils
from pxr import Sdf

from .constants import LSS_LAYER_GAME_NAME
from .layer_types import LayerType, LayerTypeKeys
from .layers import autoupscale, capture, capture_baker, i_layer, replacement, workfile


class LayerManagerCore:
    def __init__(self, context_name=None):
        self.__default_attr = {}
        for attr, value in self.__default_attr.items():
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

    def get_layer_instance(self, layer_type: LayerType) -> Optional[i_layer.ILayer]:
        for layer_obj in self.__layers:
            if layer_obj.layer_type == layer_type:
                return layer_obj
        return None

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
        if do_undo:
            omni.kit.undo.begin_group()
        stage = self.__context.get_stage()
        if parent_layer is None:
            parent_layer = stage.GetRootLayer()
        omni.kit.commands.execute(
            "CreateSublayer",
            layer_identifier=parent_layer.identifier,
            sublayer_position=sublayer_insert_position,
            new_layer_path=path,
            transfer_root_content=False,
            create_or_insert=False,
            layer_name="",
            usd_context=self.__context,
        )
        for layer in stage.GetLayerStack():
            if omni.client.normalize_url(layer.realPath) == omni.client.normalize_url(path):
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
    def create_new_anonymous_layer():
        return Sdf.Layer.CreateAnonymous()

    def save_layer(self, layer_type: LayerType, comment: str = None, show_checkpoint_error: bool = True):
        layer = self.get_layer(layer_type)
        if layer is None:
            carb.log_error(f'Can\'t find the layer type "{layer_type.value}" in the stage')
            return
        layer.Save()
        result, _ = omni.client.stat(layer.realPath)
        if result == omni.client.Result.OK:
            result, _ = omni.client.create_checkpoint(layer.realPath, "" if comment is None else comment, force=True)
            if result != omni.client.Result.OK and show_checkpoint_error:
                carb.log_error(f"Can't create a checkpoint for file {layer.realPath}")

    def save_layer_as(self, layer_type: LayerType, path: str, comment: str = None) -> bool:
        layer = self.get_layer(layer_type)
        if layer is None:
            carb.log_error(f'Can\'t find the layer type "{layer_type.value}" in the stage')
            return False
        existing_layer = Sdf.Layer.FindOrOpen(path)
        if not existing_layer:
            Sdf.Layer.CreateNew(path)
        if not layer.Export(path):
            carb.log_error(f'Failed to save layer type "{layer_type.value}" as {path}')
            return False
        result, _ = omni.client.stat(path)
        if result == omni.client.Result.OK:
            result, _ = omni.client.create_checkpoint(path, "" if comment is None else comment, force=True)
            if result != omni.client.Result.OK:
                # Not an error with saving, so still return True.
                carb.log_error(f"Can't create a checkpoint for file {path}")
        return True

    def get_layer(self, layer_type: LayerType) -> Optional[Sdf.Layer]:
        stage = self.__context.get_stage()
        if stage is None:
            return None
        for layer in stage.GetLayerStack():
            if layer.customLayerData.get(LayerTypeKeys.layer_type.value) == layer_type.value:
                return layer
        for layer_identifier in stage.GetMutedLayers():
            layer = LayerUtils.find_layer(layer_identifier)
            if layer.customLayerData.get(LayerTypeKeys.layer_type.value) == layer_type.value:
                return layer
        return None

    @staticmethod
    def get_custom_data(layer: Sdf.Layer) -> Dict[str, str]:
        return layer.customLayerData

    @staticmethod
    def set_custom_data_layer_type(layer: Sdf.Layer, layer_type: LayerType):
        custom_layer_data = layer.customLayerData
        custom_layer_data.update({LayerTypeKeys.layer_type.value: layer_type.value})
        layer.customLayerData = custom_layer_data
        return layer.customLayerData

    @staticmethod
    def get_custom_data_layer_type(layer: Sdf.Layer):
        return layer.customLayerData.get(LayerTypeKeys.layer_type.value)

    def set_edit_target_layer(self, layer_type: LayerType, force_layer_identifier: str = None, do_undo=True):
        if do_undo:
            omni.kit.undo.begin_group()
        stage = self.__context.get_stage()
        for layer in stage.GetLayerStack():
            if force_layer_identifier is not None and layer.identifier == force_layer_identifier:
                omni.kit.commands.execute(
                    "SetEditTarget", layer_identifier=layer.identifier, usd_context=self.__context
                )
                break
            if layer.customLayerData.get(LayerTypeKeys.layer_type.value) == layer_type.value:
                omni.kit.commands.execute(
                    "SetEditTarget", layer_identifier=layer.identifier, usd_context=self.__context
                )
        if do_undo:
            omni.kit.undo.end_group()

    def lock_layer(self, layer_type: LayerType, value=True, do_undo=True):
        if do_undo:
            omni.kit.undo.begin_group()
        stage = self.__context.get_stage()
        for layer in stage.GetLayerStack():
            if layer.customLayerData.get(LayerTypeKeys.layer_type.value) == layer_type.value:
                omni.kit.commands.execute(
                    "LockLayer", usd_context=self.__context, layer_identifier=layer.identifier, locked=value
                )
        if do_undo:
            omni.kit.undo.end_group()

    def mute_layer(self, layer_type: LayerType, value: bool = True, do_undo: bool = True):
        """
        Mute the giving layer

        Args:
            layer_type: the layer type to mute
            value: the value of the mute
            do_undo: set the undo or not
        """
        if do_undo:
            omni.kit.undo.begin_group()
        stage = self.__context.get_stage()
        for layer in stage.GetLayerStack():
            if layer.customLayerData.get(LayerTypeKeys.layer_type.value) == layer_type.value:
                omni.kit.commands.execute(
                    "SetLayerMuteness", layer_identifier=layer.identifier, muted=value, usd_context=self.__context
                )
        if do_undo:
            omni.kit.undo.end_group()

    def remove_layer(self, layer_type: LayerType, do_undo=True):
        if do_undo:
            omni.kit.undo.begin_group()
        stage = self.__context.get_stage()
        for layer in stage.GetLayerStack():
            for sublayerpath in layer.subLayerPaths:
                sublayer = Sdf.Layer.FindOrOpen(layer.ComputeAbsolutePath(sublayerpath))
                if not sublayer:
                    continue
                if sublayer.customLayerData.get(LayerTypeKeys.layer_type.value) == layer_type.value:
                    position = LayerUtils.get_sublayer_position_in_parent(layer.identifier, sublayer.identifier)
                    omni.kit.commands.execute(
                        "RemoveSublayer",
                        layer_identifier=layer.identifier,
                        sublayer_position=position,
                        usd_context=self.__context,
                    )
                    carb.log_info(f"Layer {layer} removed")
        if do_undo:
            omni.kit.undo.end_group()

    @staticmethod
    def get_game_name_from_path(path: str) -> str:
        layer = Sdf.Layer.FindOrOpen(path)
        default = "Unknow game"
        if not layer:
            return default
        return layer.customLayerData.get(LSS_LAYER_GAME_NAME, "default")

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
                    f'Can\'t find the "{CAPTURE_FOLDER}|{REMIX_CAPTURE_FOLDER}" folder from the {LayerType.capture}'
                    f" layer"
                )
            return None, None
        game_name = layer.customLayerData.get(LSS_LAYER_GAME_NAME, "MyGame")
        return game_name, str(capture_folder.parent)

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
            if match.group(3) not in hashes:
                hashes[match.group(3)] = prim.path
        return hashes

    def destroy(self):
        _reset_default_attrs(self)
