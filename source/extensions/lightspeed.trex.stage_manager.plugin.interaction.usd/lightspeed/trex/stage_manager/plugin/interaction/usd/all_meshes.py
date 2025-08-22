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

from lightspeed.trex.utils.common.prim_utils import get_extended_selection as _get_extended_selection
from omni.flux.stage_manager.factory.plugins import StageManagerFilterPlugin as _StageManagerFilterPlugin
from omni.flux.stage_manager.factory.plugins import StageManagerTreePlugin as _StageManagerTreePlugin
from omni.flux.stage_manager.plugin.interaction.usd.base import (
    StageManagerUSDInteractionPlugin as _StageManagerUSDInteractionPlugin,
)
from pydantic import Field


class AllMeshesInteractionPlugin(_StageManagerUSDInteractionPlugin):
    display_name: str = Field(default="Meshes", exclude=True)
    tooltip: str = Field(default="View the available meshes and their respective instances", exclude=True)

    internal_context_filters: list[_StageManagerFilterPlugin] = Field(
        default=[{"name": "MeshPrimsFilterPlugin"}], exclude=True
    )
    tree: _StageManagerTreePlugin = Field(default={"name": "MeshGroupsTreePlugin"}, exclude=True)

    compatible_trees: list[str] = Field(default=["MeshGroupsTreePlugin", "PrimGroupsTreePlugin"], exclude=True)
    compatible_filters: list[str] = Field(
        default=[
            "IgnorePrimsFilterPlugin",
            "IsCaptureFilterPlugin",
            "LightPrimsFilterPlugin",
            "MeshPrimsFilterPlugin",
            "OmniPrimsFilterPlugin",
            "SearchFilterPlugin",
        ],
        exclude=True,
    )
    # TODO StageManager: We have LSS plugin names in the flux ext because of this system
    compatible_widgets: list[str] = Field(
        default=[
            "AssignCategoryActionWidgetPlugin",
            "CustomTagsWidgetPlugin",
            "FocusInViewportActionWidgetPlugin",
            "IsCaptureStateWidgetPlugin",
            "IsCategoryHiddenStateWidgetPlugin",
            "IsVisibleActionWidgetPlugin",
            "ParticleSystemsActionWidgetPlugin",
            "PrimTreeWidgetPlugin",
        ],
        exclude=True,
    )

    def _get_selection(self):
        return _get_extended_selection(self._context_name)
