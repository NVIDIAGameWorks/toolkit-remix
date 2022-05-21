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

from lightspeed.layer_manager.core import LayerManagerCore, LayerType
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
        self._layer_manager.insert_sublayer(
            new_layer.path, LayerType.capture, set_as_edit_target=False, add_custom_layer_data=False
        )
        self._layer_manager.lock_layer(LayerType.capture)

    def game_current_game_capture_folder(self) -> Optional["ContentData"]:
        """Get the current capture folder from the current capture layer"""
        return self._layer_manager.game_current_game_capture_folder()
