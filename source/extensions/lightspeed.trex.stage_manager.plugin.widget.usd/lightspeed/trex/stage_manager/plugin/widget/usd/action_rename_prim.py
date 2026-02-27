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

from collections.abc import Callable
from typing import TYPE_CHECKING

import omni.usd
from lightspeed.common.constants import LSS_NICKNAME as _LSS_NICKNAME
from lightspeed.trex.asset_replacements.core.shared.setup import Setup as _AssetReplacementsCoreSetup
from lightspeed.trex.utils.common.prim_utils import is_instance as _is_instance
from omni import ui
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin as _StageManagerMenuMixin
from omni.flux.stage_manager.plugin.tree.usd.virtual_groups import VirtualGroupsItem as _VirtualGroupsItem
from omni.flux.stage_manager.plugin.widget.usd.base import (
    StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin,
)
from omni.flux.utils.common.menus import MenuGroup as _MenuGroup
from omni.flux.utils.common.menus import MenuItem as _MenuItem
from omni.flux.utils.widget.resources import get_icons as _get_icons
from pxr import Sdf, Usd

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel


class PrimRenameNameActionWidgetPlugin(_StageManagerStateWidgetPlugin, _StageManagerMenuMixin):
    """Action to rename prim name"""

    def build_icon_ui(self, model: StageManagerTreeModel, item: StageManagerTreeItem, level: int, expanded: bool):
        # NOTE: we build an empty widget here
        ui.Spacer(height=0, width=0)
        item.build_widget()

    def _build_callback(self, payload: dict, callback: Callable, x: int, y: int, button: int, modifiers: int):
        if button != 0 or not self._can_rename_prim_name(payload):
            return
        callback(payload)

    @classmethod
    def _get_menu_items(cls):
        nickname_icon_path = _get_icons("nickname")
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
                    "glyph": nickname_icon_path,
                    "appear_after": _MenuItem.ASSIGN_CATEGORY.value,
                },
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            )
        ]

    @classmethod
    def _can_rename_prim_name(cls, payload: dict):
        item = payload["item"]
        if isinstance(item, _VirtualGroupsItem) and item.is_virtual:
            return False

        return item.is_prim_editable(item.data)

    @classmethod
    def _remove_prim_nickname(cls, payload: dict):
        context = omni.usd.get_context(payload["context_name"])
        core_setup = _AssetReplacementsCoreSetup(payload["context_name"])
        stage = context.get_stage()
        if not stage:
            return

        if "item" in payload and payload["item"].data:
            path = payload["item"].data.GetPath()
            prim = stage.GetPrimAtPath(path)
            if prim and prim.IsValid() and _is_instance(prim) and payload.get("selected_paths"):
                path = str(payload["selected_paths"][0])
                prim = stage.GetPrimAtPath(path)
        else:
            path = str(payload["selected_paths"][0])
            prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            return

        attrs = [str(attr.GetName()) for attr in prim.GetAttributes()]
        if _LSS_NICKNAME not in attrs:
            return
        root_layer = stage.GetRootLayer()
        with Usd.EditContext(stage, root_layer):
            core_setup.add_attribute(
                [path], _LSS_NICKNAME, "", prim.GetAttribute(_LSS_NICKNAME).Get(), Sdf.ValueTypeNames.String
            )

    @classmethod
    def _has_prim_nickname(cls, payload: dict) -> bool:
        context = omni.usd.get_context(payload["context_name"])
        stage = context.get_stage()
        if not stage:
            return False

        if "item" in payload and payload["item"].data:
            path = payload["item"].data.GetPath()
        else:
            path = str(payload["selected_paths"][0])
        prim = stage.GetPrimAtPath(path)

        if not prim or not prim.IsValid():
            return False
        attrs = [str(attr.GetName()) for attr in prim.GetAttributes()]
        if _LSS_NICKNAME in attrs:
            return bool(prim.GetAttribute(_LSS_NICKNAME).Get())
        return False

    @classmethod
    def _change_prim_nickname(cls, payload: dict):
        if "item" not in payload or "model" not in payload:
            return
        item = payload["item"]
        if not item.nickname_field:
            return
        item.nickname_field.enter_edit_mode()

        # NOTE: notify_item_changed is required here because this action is triggered
        # from a context menu callback — external to the TreeView's widget hierarchy.
        # Unlike in-tree event handlers (e.g. double-click on a cell widget), where
        # container.rebuild() propagates within the same rendering pass, external
        # calls don't cause the TreeView to re-render the cell on their own.
        payload["model"].notify_item_changed(item)
