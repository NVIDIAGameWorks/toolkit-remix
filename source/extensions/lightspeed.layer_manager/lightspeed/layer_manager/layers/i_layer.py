"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import abc
from typing import TYPE_CHECKING, Dict, Optional

import omni.kit.commands
import omni.kit.undo
import omni.usd
import six
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from ..layer_types import LayerType, LayerTypeKeys

if TYPE_CHECKING:
    from pxr import Sdf


@six.add_metaclass(abc.ABCMeta)
class ILayer:
    def __init__(self, core):
        self._default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self._layer_type = None
        self.__custom_layer_data = None
        self._core = core

    @property
    def default_attr(self):
        return {}

    @property
    @abc.abstractmethod
    def layer_type(self) -> LayerType:
        pass

    def set_custom_layer_data(self, value: Dict[str, str]):
        """Custom layer data to be saved"""
        self.__custom_layer_data = value

    def get_custom_layer_data(self):
        return self.__custom_layer_data

    def flatten_sublayers(self, delete_sublayer_files: bool = True):
        usd_context = omni.usd.get_context(self._core.context_name or "")
        stage = usd_context.get_stage()
        root_layer = stage.GetRootLayer()
        layers = stage.GetLayerStack()
        omni.kit.commands.execute("FlattenLayers", usd_context=self._core.context_name or "")
        if delete_sublayer_files:
            for layer in layers:
                if layer.realPath == root_layer.realPath or not layer.realPath:
                    continue
                omni.client.delete(layer.realPath)

    def create_sublayer(
        self,
        path: str = None,
        sublayer_create_position: int = 0,
        parent_layer: Optional["Sdf.Layer"] = None,
        do_undo: bool = True,
        replace_existing: bool = True,
    ):
        if do_undo:
            omni.kit.undo.begin_group()
        if replace_existing:
            need_new_layer = self._core.get_layer(self.layer_type)
            if need_new_layer is not None:
                self._core.remove_layer(self.layer_type, do_undo=False)
        usd_context = omni.usd.get_context(self._core.context_name or "")
        stage = usd_context.get_stage()
        if not parent_layer:
            parent_layer = stage.GetRootLayer()
        current_layers = stage.GetLayerStack()
        omni.kit.commands.execute(
            "CreateSublayer",
            layer_identifier=parent_layer.identifier,
            sublayer_position=sublayer_create_position,
            new_layer_path=path if path else "",
            transfer_root_content=False,
            create_or_insert=True,
            usd_context=self._core.context_name or "",
        )
        layers = stage.GetLayerStack()
        new_layers = list(set(layers) - set(current_layers))
        layer = sorted(new_layers, key=lambda x: x.GetDisplayName())[0]
        custom_layer_data = layer.customLayerData
        custom_layer_data.update({LayerTypeKeys.layer_type.value: self.layer_type.value})
        if self.__custom_layer_data:
            custom_layer_data.update(self.__custom_layer_data)
        layer.customLayerData = custom_layer_data
        layer.Save()
        if do_undo:
            omni.kit.undo.end_group()
        return layer

    def get_sdf_layer(self):
        usd_context = omni.usd.get_context(self._core.context_name or "")
        stage = usd_context.get_stage()
        if stage is None:
            return None
        for layer in stage.GetLayerStack():
            if layer.customLayerData.get(LayerTypeKeys.layer_type.value) == self.layer_type.value:
                return layer
        return None

    def destroy(self):
        self._core = None
        _reset_default_attrs(self)
