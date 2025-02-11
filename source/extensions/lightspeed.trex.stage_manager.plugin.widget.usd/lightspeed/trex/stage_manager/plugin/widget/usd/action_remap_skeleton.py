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

__all__ = ["RemapSkeletonActionWidgetPlugin"]

from functools import partial
from typing import TYPE_CHECKING

from lightspeed.trex.asset_replacements.core.shared import CachedReplacementSkeletons
from lightspeed.trex.asset_replacements.core.shared import Setup as AssetReplacementsCore
from lightspeed.trex.asset_replacements.core.shared import SkeletonReplacementBinding
from lightspeed.trex.skeleton_replacements.widget import SkeletonRemappingWindow
from omni import ui
from omni.flux.stage_manager.plugin.tree.usd.skeleton_groups import SkeletonBoundMeshItem
from omni.flux.stage_manager.plugin.widget.usd.base import StageManagerStateWidgetPlugin
from pxr import Sdf
from pydantic import PrivateAttr

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel


class RemapSkeletonActionWidgetPlugin(StageManagerStateWidgetPlugin):
    """Remap replacement skeletons to captured skeletons to drive character animation"""

    _capture_layer: Sdf.Layer = PrivateAttr(None)
    _remap_window: SkeletonRemappingWindow | None = PrivateAttr(None)
    _skel_replacement_cache: CachedReplacementSkeletons = PrivateAttr(None)

    def set_context_name(self, context: str) -> None:
        """Clear skeleton replacement cache to make sure its updated before we build the items."""
        super().set_context_name(context)
        self._remap_window: SkeletonRemappingWindow = None
        self._skel_replacement_cache = CachedReplacementSkeletons()

    def build_ui(self, model: StageManagerTreeModel, item: StageManagerTreeItem, level: int, expanded: bool):
        if not self._remap_window:
            # cannot build in plugin __init__, because it is too early for uis.
            self._remap_window = SkeletonRemappingWindow()
        super().build_ui(model, item, level, expanded)

    def build_overview_ui(self, model: StageManagerTreeModel):
        pass

    def build_icon_ui(self, model: StageManagerTreeModel, item: StageManagerTreeItem, level: int, expanded: bool):
        if not isinstance(item, SkeletonBoundMeshItem):
            return

        # if all conditions are met, enable the remap button
        enabled = False
        tooltip = (
            "Remap Joint Indices disabled: In order to remap skeletons, a skinned replacement asset (with a "
            "mesh and a skeleton) must be added to mod over the top of a captured skeleton asset."
        )
        if not item.skel_prim:
            tooltip = "Cannot Remap Joint Indices because bound skeleton can not be found."
        elif not item.skel_root:
            tooltip = "Cannot Remap Joint Indices because mesh is not under a skel root."
        else:
            skel_replacement = self.get_skel_replacement(item)
            if skel_replacement:
                # if skels are the same, we didn't find a distinct capture skel and replacement skel in the prim stack
                if skel_replacement.captured_skeleton == skel_replacement.original_skeleton:
                    tooltip = (
                        "Cannot Remap Joint Indices, no replacement skeleton found. \n"
                        f'Mesh is bound to "{item.skel_prim.GetName()}"'
                    )
                else:
                    enabled = True
                    tooltip = (
                        "Remap Joint Indices. \n"
                        f'Mesh is bound to "{item.skel_prim.GetName()}", but was originally bound to '
                        f'"{skel_replacement.original_skeleton.GetPrim().GetName()}"'
                    )

        if enabled:
            name = "RemapSkeleton"
        else:
            name = "RemapSkeletonDisabled"
        ui.Image(
            "",
            width=self._icon_size,
            height=self._icon_size,
            name=name,
            tooltip=tooltip,
            mouse_released_fn=partial(self._show_remapping_window, item) if enabled else None,
        )

    def get_skel_replacement(self, item: SkeletonBoundMeshItem) -> SkeletonReplacementBinding | None:
        if not item.skel_root or not item.bound_prim:
            return None
        stage = item.skel_root.GetStage()
        skel_root, bound_prim = AssetReplacementsCore.get_corresponding_prototype_prims(
            [item.skel_root, item.bound_prim]
        )
        skel_replacement = self._skel_replacement_cache.add_skel_replacement(
            stage.GetPrimAtPath(skel_root), stage.GetPrimAtPath(bound_prim)
        )
        return skel_replacement

    def _show_remapping_window(self, item: SkeletonBoundMeshItem, x, y, button, modifier):
        if button != 0:
            return
        skel_replacement = self.get_skel_replacement(item)
        self._remap_window.show_window(value=True, skel_replacement=skel_replacement)
