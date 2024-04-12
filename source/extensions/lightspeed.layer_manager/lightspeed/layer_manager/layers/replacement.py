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
from typing import Dict

from ..constants import LSS_LAYER_GAME_NAME
from ..layer_types import LayerType
from .i_layer import ILayer


class ReplacementLayer(ILayer):
    def set_custom_layer_data(self, value: Dict[str, str]):
        if LSS_LAYER_GAME_NAME not in value:
            raise ValueError(f"{LSS_LAYER_GAME_NAME} need to be set")

        super().set_custom_layer_data(value)

    @property
    def layer_type(self) -> LayerType:
        return LayerType.replacement
