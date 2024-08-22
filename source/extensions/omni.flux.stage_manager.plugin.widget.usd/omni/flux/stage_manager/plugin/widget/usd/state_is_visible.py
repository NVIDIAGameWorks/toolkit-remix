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

from .base import StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class IsVisibleStateWidgetPlugin(_StageManagerStateWidgetPlugin):
    # TODO StageManager: Build proper plugin

    def build_ui(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool):
        ui.Image(
            "",
            width=self._icon_size,
            height=self._icon_size,
            name="Eye",
            tooltip="The prim is visible",
            mouse_released_fn=self._on_icon_clicked,
        )

    def build_result_ui(self, model: "_StageManagerTreeModel"):
        pass

    def _on_icon_clicked(self, x: int, y: int, button: int, modifier: int):
        if button != 0:
            return

        print("Visible clicked")
