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

import abc
from typing import TYPE_CHECKING

from omni import ui

from .usd_base import StageManagerUSDWidgetPlugin as _StageManagerUSDWidgetPlugin

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class StageManagerStateWidgetPlugin(_StageManagerUSDWidgetPlugin, abc.ABC):
    display_name: str = ""
    tooltip: str = ""  # The tooltip will be dynamically built on the state icon

    @property
    def _icon_size(self) -> ui.Length:
        return ui.Pixel(20)

    @abc.abstractmethod
    def build_icon_ui(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool):
        pass

    def build_ui(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool):
        with ui.VStack():
            ui.Spacer(width=0)
            self.build_icon_ui(model, item, level, expanded)
            ui.Spacer(width=0)
