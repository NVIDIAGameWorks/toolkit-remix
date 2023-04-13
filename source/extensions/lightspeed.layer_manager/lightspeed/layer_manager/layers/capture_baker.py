"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from ..layer_types import LayerType
from .i_layer import ILayer


class CaptureBakerLayer(ILayer):
    @property
    def layer_type(self) -> LayerType:
        return LayerType.capture_baker
