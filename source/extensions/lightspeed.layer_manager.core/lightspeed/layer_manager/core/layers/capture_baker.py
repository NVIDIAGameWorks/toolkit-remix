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

from omni.flux.layer_tree.usd.core import LayerCustomData as _LayerCustomData

from ..data_models import LayerType, LayerTypeKeys
from .i_layer import ILayer


class CaptureBakerLayer(ILayer):
    """
    Layer type representing the Remix capture-baker scratch layer.

    This layer is fully locked down via its customLayerData: all edit operations
    (add child, edit target, lock, move, mute, and remove) are excluded by default
    so the user cannot accidentally modify it through normal layer-manager actions.
    """

    def get_custom_layer_data(self):
        """
        Return the customLayerData dict for the capture-baker layer.

        Overrides the base ``ILayer`` implementation to return a hard-coded dict that
        includes both the ``lightspeed_layer_type`` tag and a ``EXCLUDE_*`` block that
        disables all interactive layer operations for this layer type.

        Returns:
            A dict with ``lightspeed_layer_type`` set to ``LayerType.capture_baker`` and
            every ``LayerCustomData.EXCLUDE_*`` flag set to ``True``.
        """
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
