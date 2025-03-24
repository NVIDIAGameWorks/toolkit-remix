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

import omni.kit.commands
from omni import ui
from pxr import Usd, UsdGeom

from .base import StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class IsVisibleActionWidgetPlugin(_StageManagerStateWidgetPlugin):
    def build_icon_ui(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool):
        enabled = item.data and UsdGeom.Imageable(item.data)

        if enabled:
            is_visible = (
                UsdGeom.Imageable(item.data).ComputeVisibility(Usd.TimeCode.Default()) != UsdGeom.Tokens.invisible
            )

            icon = "Eye" if is_visible else "EyeOff"
            tooltip = (
                f"The prim is {'visible' if is_visible else 'hidden'}. "
                f"Click to {'hide' if is_visible else 'show'} the prim"
            )
        else:
            icon = "EyeDisabled"
            tooltip = "The prim cannot be hidden"

        # Build the icon
        ui.Image(
            "",
            width=self._icon_size,
            height=self._icon_size,
            name=icon,
            tooltip=tooltip,
            enabled=enabled,
            mouse_released_fn=lambda x, y, b, m: self._on_icon_clicked(b, enabled, model, item),
        )

    def build_overview_ui(self, model: "_StageManagerTreeModel"):
        pass

    def _on_icon_clicked(
        self, button: int, enabled: bool, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem"
    ):
        if button != 0 or not enabled:
            return

        # TODO StageManager: We change the selection after the selection.
        #  Ideally we don't change the selection after the action is performed to keep multi-selections.

        self._item_clicked(button, True, model, item)

        context = omni.usd.get_context(self._context_name)
        target_value = (
            UsdGeom.Imageable(item.data).ComputeVisibility(Usd.TimeCode.Default()) == UsdGeom.Tokens.invisible
        )

        omni.kit.commands.execute(
            "SetVisibilitySelectedPrims",
            selected_paths=context.get_selection().get_selected_prim_paths(),
            value=target_value,
            context_name=self._context_name,
        )
