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

from ..constants import LSS_LAYER_GAME_NAME
from ..data_models import LayerType
from .i_layer import ILayer


class ReplacementLayer(ILayer):
    """
    Layer type representing a Remix mod replacement layer.

    Extends ``ILayer`` to enforce that ``LSS_LAYER_GAME_NAME`` is always present in
    the customLayerData, which is required for the replacement layer to be associated
    with a specific game capture.
    """

    def set_custom_layer_data(self, value: dict[str, str]):
        """
        Store extra customLayerData for the replacement layer.

        Raises ValueError if ``LSS_LAYER_GAME_NAME`` is not present in ``value``,
        since every replacement layer must be linked to a game name.

        Args:
            value: Key/value pairs to add to ``Sdf.Layer.customLayerData``.  Must
                contain the ``LSS_LAYER_GAME_NAME`` key.
        """
        if LSS_LAYER_GAME_NAME not in value:
            raise ValueError(f"{LSS_LAYER_GAME_NAME} need to be set")

        super().set_custom_layer_data(value)

    @property
    def layer_type(self) -> LayerType:
        return LayerType.replacement
