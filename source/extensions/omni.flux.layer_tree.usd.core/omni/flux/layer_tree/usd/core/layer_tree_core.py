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

__all__ = ["LayerCustomData"]

from enum import Enum


class LayerCustomData(Enum):
    """
    The custom data should be organized in a dictionary where the property name matches the ROOT value.
    Every key inside that dictionary should match one of the following EXCLUDE_* values.
    """

    ROOT = "flux_layer_widget_exclusions"
    EXCLUDE_REMOVE = "exclude_remove"
    EXCLUDE_LOCK = "exclude_lock"
    EXCLUDE_MUTE = "exclude_mute"
    EXCLUDE_EDIT_TARGET = "exclude_edit_target"
    EXCLUDE_ADD_CHILD = "exclude_add_child"
    EXCLUDE_MOVE = "exclude_move"
