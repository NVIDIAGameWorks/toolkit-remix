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

from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementCore
from omni import ui
from omni.flux.stage_manager.plugin.widget.usd.base import (
    StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin,
)

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class IsCaptureStateWidgetPlugin(_StageManagerStateWidgetPlugin):
    def build_ui(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool):
        prim = item.data.get("prim")
        if prim:
            is_captured = _AssetReplacementCore.prim_is_from_a_capture_reference(prim)
            ui.Image(
                "",
                width=self._icon_size,
                height=self._icon_size,
                name="Capture" if is_captured else "Collection",
                tooltip=f"The prim originates from a {'capture' if is_captured else 'mod'} layer.",
            )
        else:
            ui.Spacer(width=self._icon_size, height=self._icon_size)

    def build_result_ui(self, model: "_StageManagerTreeModel"):
        pass
