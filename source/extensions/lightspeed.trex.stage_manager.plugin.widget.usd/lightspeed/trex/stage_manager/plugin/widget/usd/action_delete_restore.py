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

__all__ = ["DeleteRestoreActionWidgetPlugin"]

from enum import Enum, auto
from functools import partial
from typing import Callable

import omni.kit.commands
import omni.kit.undo
import omni.usd
import OmniGraphSchema
from lightspeed.trex.asset_replacements.core.shared import Setup
from lightspeed.trex.utils.common import prim_utils
from lightspeed.trex.utils.widget.dialogs import confirm_remove_prim_overrides
from omni import ui
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel
from omni.flux.stage_manager.plugin.widget.usd.base import StageManagerStateWidgetPlugin
from pxr import Sdf, Usd


class DeleteRestoreActionWidgetPlugin(StageManagerStateWidgetPlugin):
    """Action to delete or restore prims"""

    # NOTE: we will use this enum to register different action types
    # based on object type and state rules defined in the code
    class ActionType(Enum):
        DELETE = auto()
        RESTORE = auto()
        DISABLED = auto()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._core = Setup(self._context_name)  # NOTE: this is asset replacement core

    @classmethod
    def _get_prim_action_type(cls, prim: Usd.Prim) -> ActionType:
        # NOTE: only work on prototypes for now
        if not prim_utils.is_a_prototype(prim):
            return cls.ActionType.DISABLED

        if prim.IsA(OmniGraphSchema.OmniGraph):
            return cls.ActionType.DELETE

        # NOTE: early simple implementation this will get more complex
        if prim_utils.is_mesh_asset(prim):
            return cls.ActionType.RESTORE

        return cls.ActionType.DISABLED

    def build_icon_ui(
        self,
        model: StageManagerTreeModel,
        item: StageManagerTreeItem,
        level: int,
        expanded: bool,
    ) -> None:
        if not item.data:
            ui.Spacer(width=self._icon_size, height=self._icon_size)
            return

        context = omni.usd.get_context(self._context_name)
        stage = context.get_stage()
        if not stage:
            return

        def empty_callback():
            return

        match self._get_prim_action_type(item.data):
            case self.ActionType.DISABLED:
                icon = "TrashCan"
                tooltip = "The Primitive may not be deleted"
                callback = empty_callback
                enabled = False
                identifier = "delete_restore_widget_none"
            case self.ActionType.DELETE:
                icon = "TrashCan"
                tooltip = "Delete Primitive"
                callback = self._delete_prim_cb
                enabled = True
                identifier = "delete_restore_widget_delete"
            case self.ActionType.RESTORE:
                icon = "Restore"
                tooltip = "Restore To Capture State"
                callback = self._restore_prim_cb
                enabled = True
                identifier = "delete_restore_widget_restore"

        ui.Image(
            "",
            width=self._icon_size,
            height=self._icon_size,
            name=icon,
            tooltip=tooltip,
            mouse_released_fn=partial(self._build_callback, callback, enabled),
            enabled=enabled,
            identifier=identifier,
        )

    @staticmethod
    def _build_callback(
        callback: Callable[[], None],
        enabled: bool,
        x: int,
        y: int,
        button: int,
        modifiers: int,
    ) -> None:
        if not enabled or button != 0:
            return
        callback()

    def _get_selected_by_action(self, action_type: ActionType) -> list[str]:
        context = omni.usd.get_context(self._context_name)
        sel_paths = context.get_selection().get_selected_prim_paths()
        stage = context.get_stage()

        return [
            str(path)
            for path in sel_paths
            if (prim := stage.GetPrimAtPath(path))
            and prim.IsValid()
            and self._get_prim_action_type(prim) == action_type
        ]

    def _delete_prim_cb(self) -> None:
        sel = self._get_selected_by_action(self.ActionType.DELETE)
        if not sel:
            return
        omni.kit.commands.execute("DeletePrimsCommand", paths=sel)

    def _restore_prim_cb(self) -> None:
        sel_paths = self._get_selected_by_action(self.ActionType.RESTORE)
        confirm_remove_prim_overrides(sel_paths, self._context_name)

    def build_overview_ui(self, *args, **kwargs):
        pass
