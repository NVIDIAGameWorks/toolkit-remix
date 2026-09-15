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

from __future__ import annotations

__all__ = ["SkeletonPrimsFilterPlugin"]

from omni.flux.stage_manager.factory import StageManagerItem
from pxr import UsdSkel
from pydantic import Field

from .base import ToggleableUSDFilterPlugin as _ToggleableUSDFilterPlugin


class SkeletonPrimsFilterPlugin(_ToggleableUSDFilterPlugin):
    display_name: str = Field(default="Skeleton Prims", exclude=True)
    tooltip: str = Field(default="Filter for skeleton prims", exclude=True)

    def _evaluate_item(self, item: StageManagerItem) -> bool:
        """Evaluate whether an item contains a skeleton-related prim.

        Args:
            item: Stage Manager item containing the prim to evaluate.

        Returns:
            Whether the prim uses skeleton bindings or is a skeleton container.
        """
        prim = item.data
        return prim.HasAPI(UsdSkel.BindingAPI) or prim.GetTypeName() in {"Skeleton", "SkelRoot"}
