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

__all__ = ["AssignCategoryActionWidgetPlugin"]

from functools import partial
from typing import TYPE_CHECKING

from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.utils.widget import RemixCategoriesDialog as _RemixCategoriesDialog
from omni import ui, usd
from omni.flux.stage_manager.plugin.widget.usd.base import StageManagerStateWidgetPlugin
from pydantic import PrivateAttr

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel
    from pxr import Usd


class AssignCategoryActionWidgetPlugin(StageManagerStateWidgetPlugin):
    """Action to assign Remix Categories"""

    _categories_dialog: _RemixCategoriesDialog = PrivateAttr(None)

    def build_overview_ui(self, model: StageManagerTreeModel):
        pass

    def build_icon_ui(self, model: StageManagerTreeModel, item: StageManagerTreeItem, level: int, expanded: bool):
        if not item.data:
            ui.Spacer(width=self._icon_size, height=self._icon_size)
            return

        if item.data:
            ui.Image(
                "",
                width=self._icon_size,
                height=self._icon_size,
                name="CategoriesWhite" if item.data.GetTypeName() == "Mesh" else "CategoriesDisabled",
                tooltip=(
                    "Assign Remix Categories to prim"
                    if item.data.GetTypeName() == "Mesh"
                    else "Remix Categories can only be assigned to mesh prims."
                ),
                mouse_released_fn=(
                    partial(self._show_category_window, item) if item.data.GetTypeName() == "Mesh" else None
                ),
            )

    def _assignment_callback(self, meshes: list[Usd.Prim]):
        core = _AssetReplacementsCore(self._context_name)
        paths = [str(m.GetPath()) for m in meshes]
        core.select_prim_paths(paths)

    def _show_category_window(self, item: StageManagerTreeItem, x, y, button, modifier):
        if button != 0:
            return
        if self._categories_dialog:
            self._categories_dialog = None

        context = usd.get_context(self._context_name)
        selected_prim_paths = context.get_selection().get_selected_prim_paths()
        self._categories_dialog = _RemixCategoriesDialog(
            usd.get_context().get_name(),
            paths=selected_prim_paths if selected_prim_paths else [str(item.data.GetPath())],
            refresh_func=self._assignment_callback,
        )
