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
from typing import Dict

import omni.kit.commands
import omni.usd
import six

from ..layer_types import LayerType, LayerTypeKeys


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

    def create_sublayer(self, path: str = None):
        need_new_layer = self._core.get_layer(self.layer_type)
        if need_new_layer is not None:
            self._core.remove_layer(self.layer_type)
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        root_layer = stage.GetRootLayer()
        current_layers = stage.GetLayerStack()
        omni.kit.commands.execute(
            "CreateSublayer",
            layer_identifier=root_layer.identifier,
            sublayer_position=0,
            new_layer_path=path if path else "",
            transfer_root_content=False,
            create_or_insert=True,
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
        return layer

    def destroy(self):
        self._core = None
        for attr, value in self._default_attr.items():
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
