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

__all__ = ["DeleteRestoreActionWidgetPlugin", "PROTECTED_PATHS"]

from enum import Enum, auto
from functools import partial
from typing import Callable

import omni.kit.commands
import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore
from lightspeed.layer_manager.core.data_models import LayerType
from lightspeed.trex.asset_replacements.core.shared import Setup
from lightspeed.trex.utils.common import prim_utils
from lightspeed.trex.utils.widget.dialogs import confirm_remove_prim_overrides
from omni import ui
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel
from omni.flux.stage_manager.plugin.widget.usd.base import StageManagerStateWidgetPlugin
from pxr import Sdf, Usd

PROTECTED_PATHS = {
    Sdf.Path("/RootNode"),
    Sdf.Path("/RootNode/lights"),
    Sdf.Path("/RootNode/meshes"),
    Sdf.Path("/RootNode/Looks"),
    Sdf.Path("/RootNode/instances"),
    Sdf.Path("/RootNode/cameras"),
}


class DeleteRestoreActionWidgetPlugin(StageManagerStateWidgetPlugin):
    """Action to delete or restore prims"""

    # NOTE: we will use this enum to register different action types
    # based on object type and state rules defined in the code
    class ActionType(Enum):
        DELETE = auto()
        RESTORE = auto()
        RESTOREDISABLED = auto()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._core = Setup(self._context_name)  # NOTE: this is asset replacement core
        self._layer_manager = LayerManagerCore(self._context_name)

    def _get_prim_action_type(self, prim: Usd.Prim) -> ActionType:
        """
        Determines the action type for a prim based on USD layer analysis.

        Logic:
        - If prim is NOT from capture reference: returns DELETE
        - If prim IS from capture reference:
          - If prim has opinions in replacement layers: returns RESTORE
          - If prim has NO opinions in replacement layers: returns RESTOREDISABLED

        This ensures prims from capture can only be restored if they have been
        modified (have opinions) in replacement layers, otherwise restoration is disabled.
        """
        # NOTE: we never want to restore this (too much responsibility)

        if prim.GetPath() in PROTECTED_PATHS:
            return self.ActionType.RESTOREDISABLED
        proto = prim_utils.get_prototype(prim)
        if proto:
            prim = proto
        stack = prim.GetPrimStack()

        # NOTE: all objects that are not defined in the capture layer are deletable
        if not self._core.prim_is_from_a_capture_reference(prim):
            return self.ActionType.DELETE

        # NOTE: if asset originates in the capture file we will only restore it
        rep_sub_layers = self._layer_manager.get_replacement_layers()

        for ref in stack:
            ltype = self._layer_manager.get_custom_data_layer_type(ref.layer)

            if (ltype and ltype != LayerType.replacement.value) or ref.layer not in rep_sub_layers:
                continue
            return self.ActionType.RESTORE

        return self.ActionType.RESTOREDISABLED

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

        match self._get_prim_action_type(item.data):
            case self.ActionType.DELETE:
                icon = "TrashCan"
                tooltip = "Delete Prim"
                callback = self._delete_prim_cb
                enabled = True
                identifier = "delete_restore_widget_delete"

            case self.ActionType.RESTORE:
                icon = "Restore"
                tooltip = "Restore Prim To Capture State"
                callback = self._restore_prim_cb
                enabled = True
                identifier = "delete_restore_widget_restore"

            case self.ActionType.RESTOREDISABLED:
                icon = "Restore"
                tooltip = "The Prim may not be restored"
                callback = None
                enabled = False
                identifier = "delete_restore_widget_restore"
            case _:
                raise ValueError(f"could not sort out prim action type from {item.data}")

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
        _x: float,
        _y: float,
        button: int,
        _modifiers: int,
    ) -> None:
        if not enabled or button != 0:
            return
        callback()

    def _get_selected_by_action(self, action_type: ActionType) -> list[str]:
        context = omni.usd.get_context(self._context_name)
        sel_paths = context.get_selection().get_selected_prim_paths()
        stage = context.get_stage()

        return [
            str(prim.GetPath())
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
