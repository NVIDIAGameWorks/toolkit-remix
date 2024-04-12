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
import typing
from typing import Optional, Tuple

from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from lightspeed.widget.content_viewer.scripts.core import ContentData

if typing.TYPE_CHECKING:
    from pxr import Sdf


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

    def game_current_game_capture_folder(self) -> Tuple[Optional[str], Optional[str]]:
        """Get the current capture folder from the current capture layer"""
        return self._layer_manager.game_current_game_capture_folder()
