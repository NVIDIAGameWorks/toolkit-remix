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

__all__ = ["MeshGroupFilterPlugin"]

from lightspeed.common.constants import ROOTNODE_MESHES as _ROOTNODE_MESHES
from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.stage_manager.factory.plugins.filter_plugin import FilterCategory as _FilterCategory
from omni.flux.stage_manager.plugin.filter.usd.base import ToggleableUSDFilterPlugin as _ToggleableUSDFilterPlugin
from pydantic import Field


class MeshGroupFilterPlugin(_ToggleableUSDFilterPlugin):
    """
    Filter plugin for USD mesh group.

    Filters prims based on whether they are instances.
    """

    display_name: str = Field(default="Mesh Group", exclude=True)
    tooltip: str = Field(default="Filter for mesh group", exclude=True)
    filter_category: _FilterCategory = Field(default=_FilterCategory.GROUP, exclude=True)

    def _evaluate_item(self, item: StageManagerItem) -> bool:
        """Evaluate whether an item belongs to the mesh group.

        Args:
            item: Stage Manager item containing the prim to evaluate.

        Returns:
            Whether the prim path belongs to the mesh-group namespace.
        """
        return str(item.data.GetPath()).startswith(_ROOTNODE_MESHES)
