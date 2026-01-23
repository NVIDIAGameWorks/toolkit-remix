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

from lightspeed.common.constants import REMIX_CATEGORIES_ALLOWED_PRIM_TYPES as _REMIX_CATEGORIES_ALLOWED_PRIM_TYPES
from lightspeed.trex.utils.widget import RemixCategoriesDialog as _RemixCategoriesDialog
from omni import ui, usd
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin as _StageManagerMenuMixin
from omni.flux.stage_manager.plugin.widget.usd.base import (
    StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin,
)
from omni.flux.utils.common.menus import MenuGroup as _MenuGroup
from omni.flux.utils.common.menus import MenuItem as _MenuItem
from omni.flux.utils.widget.resources import get_icons as _get_icons
from pydantic import PrivateAttr

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel
    from pxr import Usd


class AssignCategoryActionWidgetPlugin(_StageManagerStateWidgetPlugin, _StageManagerMenuMixin):
    """Action to assign Render Categories"""

    _categories_dialog: _RemixCategoriesDialog = PrivateAttr(default=None)

    def build_icon_ui(self, model: StageManagerTreeModel, item: StageManagerTreeItem, level: int, expanded: bool):
        if not item.data:
            ui.Spacer(width=self._icon_size, height=self._icon_size)
            return

        if item.data:
            ui.Image(
                "",
                width=self._icon_size,
                height=self._icon_size,
                name=(
                    "CategoriesWhite"
                    if item.data.GetTypeName() in _REMIX_CATEGORIES_ALLOWED_PRIM_TYPES
                    else "CategoriesDisabled"
                ),
                tooltip=(
                    "Assign Render Categories to prim"
                    if item.data.GetTypeName() in _REMIX_CATEGORIES_ALLOWED_PRIM_TYPES
                    else "Render Categories can only be assigned to mesh prims."
                ),
                mouse_released_fn=(
                    partial(self._show_category_window, item, self._context_name)
                    if item.data.GetTypeName() in _REMIX_CATEGORIES_ALLOWED_PRIM_TYPES
                    else None
                ),
            )

    @classmethod
    def _get_menu_items(cls):
        categories_icon = _get_icons("categories_white")
        return [
            (
                {
                    "name": _MenuItem.ASSIGN_CATEGORY.value,
                    "glyph": categories_icon,
                    "appear_after": _MenuItem.FOCUS_IN_VIEWPORT.value,
                    "onclick_fn": cls._on_menu_assign_category,
                    "show_fn": cls._on_menu_assign_category_show_fn,
                },
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            ),
        ]

    @classmethod
    def _assignment_callback(cls, context_name: str, meshes: list[Usd.Prim]):
        usd.get_context(context_name).get_selection().set_selected_prim_paths([str(m.GetPath()) for m in meshes])

    @classmethod
    def _show_category_window(cls, item: StageManagerTreeItem, context_name: str, x=0, y=0, b=0, m=None):
        if b != 0:
            return

        if cls._categories_dialog:
            cls._categories_dialog = None

        selected_prim_paths = usd.get_context(context_name).get_selection().get_selected_prim_paths()
        cls._categories_dialog = _RemixCategoriesDialog(
            context_name=context_name,
            paths=selected_prim_paths if selected_prim_paths else [str(item.data.GetPath())],
            refresh_func=partial(cls._assignment_callback, context_name),
        )

    @classmethod
    def _on_menu_assign_category(cls, payload: dict):
        cls._show_category_window(payload.get("right_clicked_item"), payload.get("context_name", ""))

    @classmethod
    def _on_menu_assign_category_show_fn(cls, payload: dict):
        right_clicked_item = payload.get("right_clicked_item")
        return right_clicked_item and right_clicked_item.data.GetTypeName() in _REMIX_CATEGORIES_ALLOWED_PRIM_TYPES
