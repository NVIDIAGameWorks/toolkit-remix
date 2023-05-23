"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from omni.flux.layer_tree.usd.core import LayerCustomData as _LayerCustomData

from ..layer_types import LayerType, LayerTypeKeys
from .i_layer import ILayer


class CaptureBakerLayer(ILayer):
    def get_custom_layer_data(self):
        return {
            LayerTypeKeys.layer_type.value: self.layer_type.value,
            _LayerCustomData.ROOT.value: {
                _LayerCustomData.EXCLUDE_ADD_CHILD.value: True,
                _LayerCustomData.EXCLUDE_EDIT_TARGET.value: True,
                _LayerCustomData.EXCLUDE_LOCK.value: True,
                _LayerCustomData.EXCLUDE_MOVE.value: True,
                _LayerCustomData.EXCLUDE_MUTE.value: True,
                _LayerCustomData.EXCLUDE_REMOVE.value: True,
            },
        }

    @property
    def layer_type(self) -> LayerType:
        return LayerType.capture_baker
