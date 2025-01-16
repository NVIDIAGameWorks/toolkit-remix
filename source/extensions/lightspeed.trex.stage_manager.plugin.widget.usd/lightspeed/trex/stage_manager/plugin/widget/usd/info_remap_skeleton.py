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

__all__ = ["RemapSkeletonInfoWidgetPlugin"]

from typing import TYPE_CHECKING

from lightspeed.trex.asset_replacements.core.shared import Setup as AssetReplacementsCore
from omni import ui
from omni.flux.stage_manager.plugin.tree.usd.skeleton_groups import (
    SkeletonBoundMeshItem,
    SkeletonItem,
    SkeletonJointItem,
)
from omni.flux.stage_manager.plugin.widget.usd.base import StageManagerUSDWidgetPlugin

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel


class RemapSkeletonInfoWidgetPlugin(StageManagerUSDWidgetPlugin):
    """Remap replacement skeletons to captured skeletons to drive character animation"""

    def build_ui(self, model: StageManagerTreeModel, item: StageManagerTreeItem, level: int, expanded: bool):
        prim = item.data
        with ui.VStack(width=0):
            ui.Spacer(width=0)
            if isinstance(item, SkeletonBoundMeshItem) and item.bound_prim:
                is_captured = AssetReplacementsCore.prim_is_from_a_capture_reference(item.bound_prim)
                ui.Label(
                    f"{'Captured' if is_captured else 'Replacement'} Bound Mesh",
                )
            elif isinstance(item, SkeletonJointItem) and item.skel_prim:
                is_captured = AssetReplacementsCore.prim_is_from_a_capture_reference(item.skel_prim)
                ui.Label(
                    "Captured Joint" if is_captured else "Replacement Joint",
                )
            elif isinstance(item, SkeletonItem) and prim:
                is_captured = AssetReplacementsCore.prim_is_from_a_capture_reference(prim)
                ui.Label(
                    "Captured Skeleton" if is_captured else "Replacement Skeleton",
                )
            ui.Spacer(width=0)

    def build_overview_ui(self, model: StageManagerTreeModel):
        def is_remapped(item):
            return (
                item.bound_prim.GetAttribute("skel:remix_joints").HasAuthoredValue()
                or item.bound_prim.GetAttribute("skel:joints").HasAuthoredValue()
            )

        bound_prims = [i for i in model.iter_items_children() if isinstance(i, SkeletonBoundMeshItem)]
        manually_remapped_count = len([i for i in bound_prims if is_remapped(i)])
        ui.Label(
            f"{manually_remapped_count}/{len(bound_prims)} "
            f"skeleton{'s' if manually_remapped_count > 1 else ''} remapped"
        )
