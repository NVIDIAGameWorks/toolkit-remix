"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["PrimRenameNameActionWidgetPlugin"]

from functools import partial
from typing import TYPE_CHECKING, Callable

import omni.usd
from lightspeed.common.constants import LSS_NICKNAME as _LSS_NICKNAME
from lightspeed.common.constants import ROOTNODE as _ROOTNODE
from lightspeed.common.constants import ROOTNODE_INSTANCES as _ROOTNODE_INSTANCES
from lightspeed.common.constants import ROOTNODE_LIGHTS as _ROOTNODE_LIGHTS
from lightspeed.common.constants import ROOTNODE_MESHES as _ROOTNODE_MESHES
from lightspeed.trex.asset_replacements.core.shared.setup import Setup as _AssetReplacementsCoreSetup
from omni import ui
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin as _StageManagerMenuMixin
from omni.flux.stage_manager.plugin.widget.usd.base import (
    StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin,
)
from omni.flux.utils.common.menus import MenuGroup as _MenuGroup
from omni.flux.utils.common.menus import MenuItem as _MenuItem
from omni.flux.utils.widget.resources import get_icons as _get_icons
from pxr import Sdf

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel


TOP_LEVEL_PRIM_PATHS = [_ROOTNODE_MESHES, _ROOTNODE_LIGHTS, _ROOTNODE_INSTANCES, _ROOTNODE]


class PrimRenameNameActionWidgetPlugin(_StageManagerStateWidgetPlugin, _StageManagerMenuMixin):
    """Action to rename prim name"""

    def build_icon_ui(self, model: StageManagerTreeModel, item: StageManagerTreeItem, level: int, expanded: bool):
        if not item.data:
            ui.Spacer(width=self._icon_size, height=self._icon_size)
            return

        payload = {"context_name": self._context_name, "selected_paths": [item.data.GetPrimPath()]}
        enabled = self._can_rename_prim_name(payload)
        has_prim_nickname = self._has_prim_nickname(payload)

        if enabled:
            icon = "Subtract" if has_prim_nickname else "Add"
            tooltip = "Remove the Prim Nickname" if has_prim_nickname else "Create a Prim Nickname"
            callback = (
                partial(self._build_callback, payload, self._remove_prim_nickname)
                if has_prim_nickname
                else partial(self._build_callback, payload, self._change_prim_nickname)
            )
        else:
            icon = "AddDisabled"
            tooltip = (
                "Select a prim to create a nickname.\n\n"
                "NOTE: Only prims with nicknames can be renamed. Hashes will remain the same."
            )
            callback = None

        ui.Image(
            "",
            width=self._icon_size,
            name=icon,
            tooltip=tooltip,
            mouse_released_fn=callback,
        )

    def _build_callback(self, payload: dict, callback: Callable, x: int, y: int, button: int, modifiers: int):
        if button != 0 or not self._can_rename_prim_name(payload):
            return
        callback(payload)

    @classmethod
    def _get_menu_items(cls):
        particle_icon_path = _get_icons("nickname")
        plus_icon_path = _get_icons("add")
        minus_icon_path = _get_icons("subtract")

        return [
            (
                {
                    "name": {
                        _MenuItem.PRIM_NICENAME.value: [
                            {
                                "name": _MenuItem.RENAME_PRIM_NICENAME.value,
                                "glyph": plus_icon_path,
                                "onclick_fn": cls._change_prim_nickname,
                                "show_fn": cls._can_rename_prim_name,
                                # Enable if the prim is not a top level prim
                                "enabled_fn": cls._can_rename_prim_name,
                            },
                            {
                                "name": _MenuItem.REMOVE_PRIM_NICENAME.value,
                                "glyph": minus_icon_path,
                                "onclick_fn": cls._remove_prim_nickname,
                                "show_fn": cls._can_rename_prim_name,
                                # Enable if a prim nickname exists only
                                "enabled_fn": cls._has_prim_nickname,
                            },
                        ],
                    },
                    "glyph": particle_icon_path,
                    "appear_after": _MenuItem.ASSIGN_CATEGORY.value,
                },
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            )
        ]

    @classmethod
    def _can_rename_prim_name(cls, payload: dict):
        path = str(payload["selected_paths"][0])
        return path not in TOP_LEVEL_PRIM_PATHS

    @classmethod
    def _remove_prim_nickname(cls, payload: dict):
        context = omni.usd.get_context(payload["context_name"])
        core_setup = _AssetReplacementsCoreSetup(payload["context_name"])
        stage = context.get_stage()
        if not stage:
            return
        path = str(payload["selected_paths"][0])
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            return
        attrs = [str(attr.GetName()) for attr in prim.GetAttributes()]
        if _LSS_NICKNAME not in attrs:
            return
        core_setup.add_attribute(
            [path], _LSS_NICKNAME, "", prim.GetAttribute(_LSS_NICKNAME).Get(), Sdf.ValueTypeNames.String
        )

    @classmethod
    def _has_prim_nickname(cls, payload: dict) -> bool:
        context = omni.usd.get_context(payload["context_name"])
        stage = context.get_stage()
        if not stage:
            return False
        path = str(payload["selected_paths"][0])
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            return False
        attrs = [str(attr.GetName()) for attr in prim.GetAttributes()]
        return _LSS_NICKNAME in attrs

    @classmethod
    def _change_prim_nickname(cls, payload: dict):
        if "item" not in payload or "model" not in payload:
            return
        item = payload["item"]
        item.pending_edit = True
        payload["model"].notify_item_changed(item)
