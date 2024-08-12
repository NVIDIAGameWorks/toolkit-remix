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

from typing import TYPE_CHECKING

from omni import ui
from omni.flux.stage_manager.factory.plugins import StageManagerColumnPlugin as _StageManagerColumnPlugin
from pydantic import Field

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class HorizontalColumnPlugin(_StageManagerColumnPlugin):
    display_name: str = Field(...)

    @property
    def tooltip(self) -> str:
        return self.display_name

    def build_ui(
        self,
        model: "_StageManagerTreeModel",
        item: "_StageManagerTreeItem",
        column_id: int,
        level: int,
        expanded: bool,
    ):
        with ui.HStack():
            for widget in self.widgets:
                widget.build_ui(model, item, column_id, level, expanded)

    def build_result_ui(self, model: "_StageManagerTreeModel", column_id: int):
        with ui.HStack():
            for widget in self.widgets:
                widget.build_result_ui(model, column_id)
