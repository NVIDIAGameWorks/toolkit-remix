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

from typing import Iterable

from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.stage_manager.factory.plugins import StageManagerFilterPlugin as _StageManagerFilterPlugin
from omni.flux.stage_manager.factory.plugins import StageManagerTreePlugin as _StageManagerTreePlugin

from .base import StageManagerUSDInteractionPlugin as _StageManagerUSDInteractionPlugin


class AllLightsInteractionPlugin(_StageManagerUSDInteractionPlugin):
    display_name: str = "Lights"
    tooltip: str = "View the available lights, grouped by light type"

    internal_filters: list[_StageManagerFilterPlugin] = [{"name": "LightPrimsFilterPlugin"}]
    tree: _StageManagerTreePlugin = {"name": "LightGroupsTreePlugin"}

    compatible_trees: list[str] = ["LightGroupsTreePlugin", "PrimGroupsTreePlugin", "VirtualGroupsTreePlugin"]
    compatible_filters: list[str] = [
        "IgnorePrimsFilterPlugin",
        "IsCaptureFilterPlugin",
        "LightPrimsFilterPlugin",
        "OmniPrimsFilterPlugin",
        "SearchFilterPlugin",
    ]
    # TODO StageManager: We have LSS plugin names in the flux ext because of this system
    compatible_widgets: list[str] = [
        "PrimTreeWidgetPlugin",
        "FocusInViewportActionWidgetPlugin",
        "IsVisibleActionWidgetPlugin",
        "IsCaptureStateWidgetPlugin",
    ]

    def _update_context_items(self):
        if not self._is_active:
            return

        self._set_context_name()

        def flatten_items(items: Iterable[_StageManagerItem]):
            flat_items = []
            for item in items:
                flat_items.append(item)
                flat_items.extend(flatten_items(item.children))
            return flat_items

        self.tree.model.context_items = self._filter_context_items(  # noqa PLE1101
            flatten_items(self._context.get_items())
        )

        self._context_items_changed()

    def _filter_context_items(self, items: Iterable[_StageManagerItem]) -> list[_StageManagerItem]:
        """
        Filter the given items using the active context & internal filter plugins.

        Since the items will be store as a flat list, we can simply apply the predicates to every item

        Args:
            items: A list of items to filter

        Returns:
            The filtered list of items
        """

        predicates = [
            filter_plugin.filter_predicate
            for filter_plugin in (self.context_filters + self.internal_filters)
            if filter_plugin.enabled
        ]

        return [item for item in items if all(predicate(item) for predicate in predicates)]
