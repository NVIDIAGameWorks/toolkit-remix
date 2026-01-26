"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["NicknameToggleActionWidgetPlugin"]

from functools import partial
from typing import TYPE_CHECKING

from lightspeed.common.constants import LSS_NICKNAME as _LSS_NICKNAME
from omni import ui
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin as _StageManagerMenuMixin
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
from omni.flux.stage_manager.plugin.widget.usd.base import (
    StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin,
)
from omni.flux.utils.common.menus import MenuGroup as _MenuGroup
from omni.flux.utils.common.menus import MenuItem as _MenuItem
from omni.flux.utils.widget.resources import get_icons as _get_icons

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel


class NicknameToggleActionWidgetPlugin(_StageManagerStateWidgetPlugin, _StageManagerMenuMixin):
    """Action to toggle the nickname of a prim"""

    def build_icon_ui(self, model: StageManagerTreeModel, item: _StageManagerTreeItem, level: int, expanded: bool):
        if not item.data:
            ui.Spacer(width=self._icon_size, height=self._icon_size)
            return

        ui.Image(
            "",
            width=self._icon_size,
            height=self._icon_size,
            name=("Nickname" if item.data.GetAttribute(_LSS_NICKNAME).IsValid() else "NicknameDisabled"),
            tooltip="Toggle the nickname of a prim",
            mouse_released_fn=partial(self._toggle_nickname, model, item),
        )

    def build_overview_ui(self, model: StageManagerTreeModel):
        with ui.HStack():
            ui.Image(
                "",
                width=self._icon_size,
                height=self._icon_size,
                name="Nickname",
                tooltip="Toggle the nickname of all prims in the stage",
                mouse_released_fn=partial(self._toggle_nickname, model),
            )

    @classmethod
    def _get_menu_items(cls):
        nickname_icon = _get_icons("nickname")
        return [
            (
                {
                    "name": _MenuItem.TOGGLE_NICKNAME.value,
                    "glyph": nickname_icon,
                    "appear_after": _MenuItem.FOCUS_IN_VIEWPORT.value,
                    "onclick_fn": cls._on_menu_toggle_nickname,
                    "show_fn": cls._on_menu_toggle_nickname_show_fn,
                },
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            ),
        ]

    @classmethod
    def _toggle_nickname(
        cls,
        model: StageManagerTreeModel,
        item: _StageManagerTreeItem | None = None,
        x: int = 0,
        y: int = 0,
        button: int = 0,
        modifiers: int = 0,
    ):
        if not model:
            return

        if item and isinstance(item, _StageManagerTreeItem):
            item.show_nickname = not item.show_nickname
            model.set_show_nickname_override(item)
            model.notify_item_changed(item)
            return
        model.toggle_nickname()

    @classmethod
    def _on_menu_toggle_nickname(cls, payload: dict):
        cls._toggle_nickname(payload["model"], payload["item"])

    @classmethod
    def _on_menu_toggle_nickname_show_fn(cls, payload: dict):
        return payload["model"] is not None
