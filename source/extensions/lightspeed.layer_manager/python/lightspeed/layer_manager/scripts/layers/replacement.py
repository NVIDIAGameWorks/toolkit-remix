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
from ..constants import LAYER_ATTRIBUTE_PREFIX
from typing import Dict

LSS_LAYER_GAME_NAME = f"{LAYER_ATTRIBUTE_PREFIX}game_name"


class ReplacementLayer(ILayer):
    def set_custom_layer_data(self, value: Dict[str, str]):
        if LSS_LAYER_GAME_NAME not in value:
            raise ValueError(f"{LSS_LAYER_GAME_NAME} need to be set")

        super().set_custom_layer_data(value)

    @property
    def layer_type(self) -> LayerType:
        return LayerType.replacement
