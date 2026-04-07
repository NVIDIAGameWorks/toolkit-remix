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

from __future__ import annotations

import abc

import omni.kit.commands
import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from ..data_models import LayerType, LayerTypeKeys


class ILayer(abc.ABC):
    """
    Abstract base class for Remix layer type objects.

    Each concrete subclass represents one Remix layer type (capture, replacement,
    autoupscale, etc.) and is responsible for locating and managing the
    USD sublayer that carries that type's ``lightspeed_layer_type`` customLayerData tag.

    Instances hold a reference to the owning ``LayerManagerCore`` (``_core``) and an
    optional dict of extra customLayerData to stamp onto newly created sublayers.
    """

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
        """The Remix ``LayerType`` enum value that identifies this layer."""
        pass

    def set_custom_layer_data(self, value: dict[str, str]):
        """
        Store extra customLayerData entries to be merged into the layer on creation.

        Args:
            value: Key/value pairs to add to ``Sdf.Layer.customLayerData`` when
                ``LayerManagerCore._set_custom_layer_type_data_with_identifier`` is called.
                The ``lightspeed_layer_type`` key is always written automatically; entries
                here supplement it.
        """
        self.__custom_layer_data = value

    def get_custom_layer_data(self):
        """
        Return the extra customLayerData dict previously set via ``set_custom_layer_data``.

        Returns:
            The stored dict, or ``None`` if ``set_custom_layer_data`` has not been called.
        """
        return self.__custom_layer_data

    def _flatten_sublayers(self, delete_sublayer_files: bool = True):
        """
        Flatten the entire stage layer stack into the root layer and optionally delete the
        now-redundant sublayer files from disk.

        Args:
            delete_sublayer_files: When ``True`` (default), every sublayer file that is not
                the root layer is deleted via ``omni.client.delete`` after flattening.
        """
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

    def _get_sdf_layer(self):
        """
        Find and return the ``Sdf.Layer`` in the current stage that carries this
        layer type's ``lightspeed_layer_type`` tag.

        Returns:
            The matching ``Sdf.Layer``, or ``None`` if the stage is not open or no
            layer with the expected type tag is present in the layer stack.
        """
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
