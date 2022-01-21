"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import typing

import carb
from lightspeed.layer_manager.scripts.core import LayerManagerCore, LayerType
from lightspeed.layer_manager.scripts.layers.replacement import LSS_LAYER_GAME_NAME, LSS_LAYER_GAME_PATH
from lightspeed.widget.content_viewer.scripts.core import ContentData

if typing.TYPE_CHECKING:
    from pxr import Sdf

from typing import Optional


class CaptureSwapperCore:
    def __init__(self):
        self._layer_manager = LayerManagerCore()

    def is_capture_layer(self, objects):
        """Returns true if the layer is already watched"""
        item = objects["item"]
        layer = item().layer
        return layer == self._layer_manager.get_layer(LayerType.capture)

    def swap_current_capture_layer_with(self, capture_layer: "Sdf.Layer", new_layer: "ContentData"):
        # we remove the current capture layer
        if capture_layer == self._layer_manager.get_layer(LayerType.capture):
            self._layer_manager.remove_layer(LayerType.capture)
        # add the new one
        self._layer_manager.insert_sublayer(new_layer.path, LayerType.capture, set_as_edit_target=False)
        self._layer_manager.lock_layer(LayerType.capture)

    def game_current_game_from_replacement_layer(self) -> Optional["ContentData"]:
        """Returns true if the layer is already watched"""
        layer_replacement = self._layer_manager.get_layer(LayerType.replacement)
        # we only save stage that have a replacement layer
        if not layer_replacement:
            carb.log_error("Can't find the replacement layer in the current stage")
            return None
        title = layer_replacement.customLayerData.get(LSS_LAYER_GAME_NAME)
        if not title:
            carb.log_error("Can't find the game title from the replacement layer")
            return None
        path = layer_replacement.customLayerData.get(LSS_LAYER_GAME_PATH)
        if not path:
            carb.log_error("Can't find the game path from the replacement layer")
            return None
        return ContentData(title=title, path=path)
