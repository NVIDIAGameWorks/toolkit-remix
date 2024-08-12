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

from pydantic import root_validator

from .base import StageManagerUSDInteractionPlugin as _StageManagerUSDInteractionPlugin


class AllPrimsPlugin(_StageManagerUSDInteractionPlugin):
    display_name: str = "Prims"
    tooltip: str = "View all the available prims"

    compatible_trees: list[str] = ["VirtualGroupsPlugin"]
    compatible_filters: list[str] = ["SearchPlugin"]
    compatible_widgets: list[str] = ["PrimTreePlugin"]

    @root_validator(allow_reuse=True)
    def check_tree_compatibility(cls, values):  # noqa N805
        # In the root validator, plugins are already resolved
        cls.check_compatibility(values.get("tree").name, values.get("compatible_trees"))
        for filter_plugin in values.get("filters"):
            cls.check_compatibility(filter_plugin.name, values.get("compatible_filters"))
        for column_plugin in values.get("columns"):
            for widget_plugin in column_plugin.widgets:
                cls.check_compatibility(widget_plugin.name, values.get("compatible_widgets"))

        return values
