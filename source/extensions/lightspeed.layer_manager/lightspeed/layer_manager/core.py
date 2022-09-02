"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from pathlib import Path
from typing import Dict, Optional

import carb
import omni.client
import omni.kit.commands
import omni.usd
from lightspeed.common.constants import CAPTURE_FOLDER
from lightspeed.widget.content_viewer.scripts.core import ContentData
from omni.kit.usd.layers import LayerUtils
from pxr import Sdf

from .constants import LSS_LAYER_GAME_NAME
from .layer_types import LayerType, LayerTypeKeys
from .layers import autoupscale, capture, i_layer, replacement


class LayerManagerCore:
    def __init__(self):
        self.__default_attr = {}
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)
        self.__capture_layer = capture.CaptureLayer(self)
        self.__replacement_layer = replacement.ReplacementLayer(self)
        self.__autoupscale_layer = autoupscale.AutoUpscaleLayer(self)
        self.__layers = [self.__capture_layer, self.__replacement_layer, self.__autoupscale_layer]

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
        sublayer_create_position=0,
        parent_layer=None,
    ):
        for layer_obj in self.__layers:  # noqa R503
            if layer_obj.layer_type == layer_type:
                layer = layer_obj.create_sublayer(
                    path=path, sublayer_create_position=sublayer_create_position, parent_layer=parent_layer
                )
                if set_as_edit_target:
                    self.set_edit_target_layer(layer_obj.layer_type, force_layer_identifier=layer.identifier)
                return layer
        return None

    def insert_sublayer(
        self,
        path,
        layer_type: LayerType,
        set_as_edit_target: bool = True,
        sublayer_insert_position=-1,
        add_custom_layer_data=True,
        parent_layer=None,
    ):
        stage = omni.usd.get_context().get_stage()
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
                    self.set_edit_target_layer(layer_type, force_layer_identifier=layer.identifier)
                return layer
        return None

    @staticmethod
    def create_new_anonymous_layer():
        return Sdf.Layer.CreateAnonymous()

    def save_layer(self, layer_type: LayerType, comment: str = None):
        layer = self.get_layer(layer_type)
        if layer is None:
            carb.log_error(f'Can\'t find the layer type "{layer_type.value}" in the stage')
            return
        layer.Save()
        result, _ = omni.client.stat(layer.realPath)
        if result == omni.client.Result.OK:
            result, _ = omni.client.create_checkpoint(layer.realPath, "" if comment is None else comment, force=True)
            if result != omni.client.Result.OK:
                carb.log_error(f"Can't create a checkpoint for file {layer.realPath}")

    def save_layer_as(self, layer_type: LayerType, path: str, comment: str = None):
        layer = self.get_layer(layer_type)
        if layer is None:
            carb.log_error(f'Can\'t find the layer type "{layer_type.value}" in the stage')
            return
        existing_layer = Sdf.Layer.FindOrOpen(path)
        if not existing_layer:
            Sdf.Layer.CreateNew(path)
        layer.Export(path)
        result, _ = omni.client.stat(path)
        if result == omni.client.Result.OK:
            result, _ = omni.client.create_checkpoint(path, "" if comment is None else comment, force=True)
            if result != omni.client.Result.OK:
                carb.log_error(f"Can't create a checkpoint for file {path}")

    @staticmethod
    def get_layer(layer_type: LayerType) -> Optional[Sdf.Layer]:
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        if stage is None:
            return None
        for layer in stage.GetLayerStack():
            if layer.customLayerData.get(LayerTypeKeys.layer_type.value) == layer_type.value:
                return layer
        return None

    @staticmethod
    def get_custom_data(layer: Sdf.Layer) -> Dict[str, str]:
        return layer.customLayerData

    @staticmethod
    def set_edit_target_layer(layer_type: LayerType, force_layer_identifier: str = None):
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        for layer in stage.GetLayerStack():
            if force_layer_identifier is not None and layer.identifier == force_layer_identifier:
                omni.kit.commands.execute("SetEditTarget", layer_identifier=layer.identifier)
                break
            if layer.customLayerData.get(LayerTypeKeys.layer_type.value) == layer_type.value:
                omni.kit.commands.execute("SetEditTarget", layer_identifier=layer.identifier)

    @staticmethod
    def lock_layer(layer_type: LayerType, value=True):
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        for layer in stage.GetLayerStack():
            if layer.customLayerData.get(LayerTypeKeys.layer_type.value) == layer_type.value:
                omni.kit.commands.execute(
                    "LockLayer", usd_context=usd_context, layer_identifier=layer.identifier, locked=value
                )

    @staticmethod
    def remove_layer(layer_type: LayerType):
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        for layer in stage.GetLayerStack():
            for sublayerpath in layer.subLayerPaths:
                sublayer = Sdf.Layer.FindOrOpen(layer.ComputeAbsolutePath(sublayerpath))
                if not sublayer:
                    continue
                if sublayer.customLayerData.get(LayerTypeKeys.layer_type.value) == layer_type.value:
                    position = LayerUtils.get_sublayer_position_in_parent(layer.identifier, sublayer.identifier)
                    omni.kit.commands.execute(
                        "RemoveSublayer", layer_identifier=layer.identifier, sublayer_position=position
                    )
                    carb.log_info(f"Layer {layer} removed")

    def game_current_game_capture_folder(self) -> Optional["ContentData"]:
        """Get the current capture folder from the current capture layer"""
        layer = self.get_layer(LayerType.capture)
        # we only save stage that have a replacement layer
        if not layer:
            carb.log_error("Can't find the capture layer in the current stage")
            return None
        capture_folder = Path(layer.realPath)
        if capture_folder.parent.name != CAPTURE_FOLDER:
            carb.log_error(f'Can\'t find the "{CAPTURE_FOLDER}" folder from the {LayerType.capture} layer')
            return None
        game_name = layer.customLayerData.get(LSS_LAYER_GAME_NAME, "MyGame")
        return ContentData(title=game_name, path=str(capture_folder.parent))

    def destroy(self):
        for attr, value in self.__default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()
                del m_attr
                setattr(self, attr, value)
