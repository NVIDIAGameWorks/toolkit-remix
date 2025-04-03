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

from omni.flux.stage_manager.factory.plugins import StageManagerTreePlugin as _StageManagerTreePlugin

from .base import StageManagerUSDInteractionPlugin as _StageManagerUSDInteractionPlugin


class AllTagsInteractionPlugin(_StageManagerUSDInteractionPlugin):
    display_name: str = "Custom Tags"
    tooltip: str = "View the available prims, grouped by custom tags"

    tree: _StageManagerTreePlugin = {"name": "CustomTagGroupsTreePlugin"}

    compatible_trees: list[str] = ["CustomTagGroupsTreePlugin", "PrimGroupsTreePlugin"]
    compatible_filters: list[str] = [
        "IgnorePrimsFilterPlugin",
        "IsCaptureFilterPlugin",
        "OmniPrimsFilterPlugin",
        "SearchFilterPlugin",
    ]
    # TODO StageManager: We have LSS plugin names in the flux ext because of this system
    compatible_widgets: list[str] = [
        "AssignCategoryActionWidgetPlugin",
        "CustomTagsWidgetPlugin",
        "FocusInViewportActionWidgetPlugin",
        "IsCaptureStateWidgetPlugin",
        "IsCategoryHiddenStateWidgetPlugin",
        "IsVisibleActionWidgetPlugin",
        "PrimTreeWidgetPlugin",
    ]
