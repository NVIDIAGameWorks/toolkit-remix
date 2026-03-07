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

__all__ = ["PROTECTED_PATHS", "DeleteRestoreActionWidgetPlugin"]

from enum import Enum, auto
from functools import partial
from collections.abc import Callable

import carb
import omni.kit.commands
import omni.kit.undo
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

        Preconditions (evaluated before layer analysis):
        - Protected paths in PROTECTED_PATHS immediately return RESTOREDISABLED.
        - Instance prims are resolved to their prototype; all subsequent
          layer analysis is performed against the prototype prim.

        Logic:
        - If prim is NOT from capture reference:
          - If prim has a spec in the edit target or any replacement layer: returns DELETE
          - If prim has no deletable spec (composition-only): returns RESTOREDISABLED
        - If prim IS from capture reference:
          - If prim has opinions in replacement layers: returns RESTORE
          - If prim has NO opinions in replacement layers: returns RESTOREDISABLED
        """
        # NOTE: we never want to restore this (too much responsibility)

        if prim.GetPath() in PROTECTED_PATHS:
            return self.ActionType.RESTOREDISABLED
        proto = prim_utils.get_prototype(prim)
        if proto:
            prim = proto

        rep_layers = self._layer_manager.get_replacement_layers()

        if not self._core.prim_is_from_a_capture_reference(prim):
            edit_target_layer = omni.usd.get_context(self._context_name).get_stage().GetEditTarget().GetLayer()
            if edit_target_layer.GetPrimAtPath(prim.GetPath()):
                return self.ActionType.DELETE

            if any(layer.GetPrimAtPath(prim.GetPath()) for layer in rep_layers):
                return self.ActionType.DELETE

            return self.ActionType.RESTOREDISABLED

        # NOTE: if asset originates in the capture file we will only restore it
        stack = prim.GetPrimStack()
        for ref in stack:
            ltype = self._layer_manager.get_custom_data_layer_type(ref.layer)

            if (ltype and ltype != LayerType.replacement.value) or ref.layer not in rep_layers:
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
        if not item.data or not item.data.IsValid():
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

        seen: set[str] = set()
        result: list[str] = []
        for path in sel_paths:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue
            if self._get_prim_action_type(prim) != action_type:
                continue
            # Resolve instance paths to their prototype so layer operations
            # target the prim that actually owns the spec.
            proto = prim_utils.get_prototype(prim)
            effective_path = str(proto.GetPath()) if proto else path
            if effective_path not in seen:
                seen.add(effective_path)
                result.append(effective_path)
        return result

    def _delete_ancestral_prims(self, paths: list[str], rep_layers: set[Sdf.Layer]) -> None:
        """
        Delete prims that are ancestral in the current edit target by finding and removing
        their specs from the replacement layer(s) where they are actually defined.
        """
        for layer in rep_layers:
            for path in paths:
                if layer.GetPrimAtPath(path):
                    success, _ = omni.kit.commands.execute(
                        "RemovePrimSpecCommand",
                        layer_identifier=layer.identifier,
                        prim_spec_path=path,
                        usd_context=self._context_name,
                    )
                    if not success:
                        carb.log_error(f"Failed to remove prim spec '{path}' from layer '{layer.identifier}'")

    def _delete_prim_cb(self) -> None:
        sel = self._get_selected_by_action(self.ActionType.DELETE)
        if not sel:
            return

        context = omni.usd.get_context(self._context_name)
        edit_target_layer = context.get_stage().GetEditTarget().GetLayer()

        local_paths = []
        ancestral_paths = []
        rep_layers = self._layer_manager.get_replacement_layers()

        # NOTE: These two checks are intentionally independent (not elif).
        # A prim can have a local spec in the edit target AND an ancestral
        # spec in one or more replacement layers simultaneously. Both must
        # be removed for a complete delete. This is safe because
        # DeletePrimsCommand only removes the spec from the edit target
        # layer, while _delete_ancestral_prims removes specs from the
        # replacement layers via RemovePrimSpecCommand — they operate on
        # different layers and do not conflict.
        for path in sel:
            if edit_target_layer.GetPrimAtPath(path):
                local_paths.append(path)
            if any(layer.GetPrimAtPath(path) for layer in rep_layers):
                ancestral_paths.append(path)

        with omni.kit.undo.group():
            if local_paths:
                omni.kit.commands.execute("DeletePrimsCommand", paths=local_paths)
            if ancestral_paths:
                self._delete_ancestral_prims(ancestral_paths, rep_layers)

    def _restore_prim_cb(self) -> None:
        sel_paths = self._get_selected_by_action(self.ActionType.RESTORE)
        confirm_remove_prim_overrides(sel_paths, self._context_name)
