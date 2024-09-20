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

import omni.kit.app
from omni.flux.stage_manager.factory.plugins import StageManagerFilterPlugin as _StageManagerFilterPlugin

from .base import StageManagerUSDInteractionPlugin as _StageManagerUSDInteractionPlugin


class AllLightsInteractionPlugin(_StageManagerUSDInteractionPlugin):
    display_name: str = "Lights"
    tooltip: str = "View the available lights, grouped by light type"

    required_filters: list[_StageManagerFilterPlugin] = [{"name": "LightPrimsFilterPlugin"}]
    recursive_traversal: bool = True

    compatible_trees: list[str] = ["LightGroupsTreePlugin", "PrimGroupsTreePlugin", "VirtualGroupsTreePlugin"]
    compatible_filters: list[str] = [
        "IgnorePrimsFilterPlugin",
        "IsCaptureFilterPlugin",
        "LightPrimsFilterPlugin",
        "OmniPrimsFilterPlugin",
        "SearchFilterPlugin",
    ]
    # TODO StageManager: We have LSS plugin names in the flux ext because of this system
    compatible_widgets: list[str] = ["PrimTreeWidgetPlugin", "IsVisibleStateWidgetPlugin", "IsCaptureStateWidgetPlugin"]

    async def _update_context_items_deferred(self):
        await omni.kit.app.get_app().next_update_async()

        if not self._is_active:
            return

        self._set_context_name()

        # Only filter the items after getting all the children
        context_items = self._filter_context_items(
            self._traverse_children_recursive(self._context.get_items(), filter_prims=False)
        )

        self.tree.model.context_items = context_items
        self.tree.model.refresh()

    class Config(_StageManagerUSDInteractionPlugin.Config):
        fields = {
            **_StageManagerUSDInteractionPlugin.Config.fields,
            "recursive_traversal": {"exclude": True},
        }
