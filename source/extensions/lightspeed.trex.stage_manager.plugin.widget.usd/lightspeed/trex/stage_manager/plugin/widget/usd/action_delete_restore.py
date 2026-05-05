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
        DELETECAPTURE = auto()
        RESTOREGHOST = auto()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._core = Setup(self._context_name)  # NOTE: this is asset replacement core
        self._layer_manager = LayerManagerCore(self._context_name)
        self._restore_context_menu: ui.Menu | None = None

    def _get_prim_action_type(self, prim: Usd.Prim) -> ActionType:
        """Classify a prim into an action type that determines its icon and callback.

        Protected paths (e.g. ``/RootNode/meshes``) are always
        **RESTOREDISABLED** regardless of layer state.

        Capture prims (introduced by capture-layer references) follow this
        priority chain:

        1. **RESTOREGHOST** — the prim is a ghost (valid, typeless instance
           child whose prototype no longer exists).
        2. **DELETECAPTURE** — the prim or an ancestor still holds deletable
           capture references.
        3. **RESTORE** — no deletable references remain, but replacement layers
           contain reference list edits (e.g. an explicitly emptied ref list
           from a prior delete-capture) that can be reverted.
        4. **RESTOREDISABLED** — none of the above; nothing actionable.

        Non-capture prims use a simpler check: if a prim spec exists in the
        edit-target layer or any replacement layer it is **DELETE**-able,
        otherwise **RESTOREDISABLED**.

        Args:
            prim: The USD prim to classify.
        """
        if prim.GetPath() in PROTECTED_PATHS:
            return self.ActionType.RESTOREDISABLED

        rep_layers = self._layer_manager.get_replacement_layers()
        if self._core.prim_is_from_a_capture_reference(prim):
            if prim_utils.is_ghost_prim(prim):
                return self.ActionType.RESTOREGHOST

            _, refs = prim_utils.find_prim_with_references(prim)
            if refs:
                return self.ActionType.DELETECAPTURE

            if prim_utils.has_replacement_ref_edits(prim, rep_layers):
                return self.ActionType.RESTORE

            return self.ActionType.RESTOREDISABLED

        # Non-capture prims logic
        proto = prim_utils.get_prototype(prim)
        if proto:
            prim = proto

        edit_target_layer = omni.usd.get_context(self._context_name).get_stage().GetEditTarget().GetLayer()
        if edit_target_layer.GetPrimAtPath(prim.GetPath()):
            return self.ActionType.DELETE

        if any(layer.GetPrimAtPath(prim.GetPath()) for layer in rep_layers):
            return self.ActionType.DELETE

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
                tooltip = "Delete the prim"
                callback = self._delete_prim_cb
                enabled = True
                identifier = "delete_restore_widget_delete"

            case self.ActionType.RESTORE:
                icon = "Restore"
                tooltip = "Restore Prim To Capture State"
                callback = self._show_restore_context_menu
                enabled = True
                identifier = "delete_restore_widget_restore"

            case self.ActionType.DELETECAPTURE:
                icon = "TrashCan"
                tooltip = "Delete Capture Prim"
                callback = self._delete_capture_prim_cb
                enabled = True
                identifier = "delete_restore_widget_delete_capture"

            case self.ActionType.RESTOREGHOST:
                icon = "Restore"
                tooltip = "Restore captured asset reference"
                callback = self._restore_ghost_prim_cb
                enabled = True
                identifier = "delete_restore_widget_restore_ghost"

            case self.ActionType.RESTOREDISABLED:
                icon = "Restore"
                tooltip = "The prim cannot be restored"
                callback = None
                enabled = False
                identifier = "delete_restore_widget_restore_disabled"
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
        """Return deduplicated prim paths from the current selection that match the given action type.

        Instance paths are resolved to their prototype so layer operations
        target the prim that actually owns the spec.
        """
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

            # Ghost prims have no prototype — store the instance path directly.
            if action_type == self.ActionType.RESTOREGHOST:
                result.append(str(prim.GetPath()))
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
        """Delete all selected prims classified as DELETE from both the edit target and replacement layers."""
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

    def _delete_capture_prim_cb(self) -> None:
        """Remove the capture reference arc for all selected DELETECAPTURE prims.

        Only references introduced by non-replacement layers (i.e. the capture
        layer) are removed; replacement-layer references are left untouched.
        """
        sel = self._get_selected_by_action(self.ActionType.DELETECAPTURE)
        if not sel:
            return

        stage = omni.usd.get_context(self._context_name).get_stage()
        rep_layers = self._layer_manager.get_replacement_layers()
        with omni.kit.undo.group():
            for path in sel:
                prim = stage.GetPrimAtPath(path)
                if not prim or not prim.IsValid():
                    continue
                _, ref_items = prim_utils.find_prim_with_references(prim)
                for ref_prim, ref, layer, _ in ref_items:
                    if layer in rep_layers:
                        continue
                    self._core.remove_reference(stage, ref_prim.GetPath(), ref, layer)

    def _show_restore_context_menu(self) -> None:
        """Build and display a context menu with selective restore options for RESTORE prims."""
        if self._restore_context_menu is not None:
            self._restore_context_menu.destroy()
        self._restore_context_menu = ui.Menu("Restore Options")
        with self._restore_context_menu:
            ui.MenuItem(
                "Revert all modifications",
                triggered_fn=self._restore_prim_cb,
            )
            ui.Separator()
            ui.MenuItem(
                "Restore captured asset reference",
                triggered_fn=self._delete_ref_overrides,
            )

        self._restore_context_menu.show()

    def _restore_prim_cb(self) -> None:
        """Restore selected prims to their original asset by removing all replacement overrides."""
        sel_paths = self._get_selected_by_action(self.ActionType.RESTORE)
        confirm_remove_prim_overrides(sel_paths, self._context_name)

    def _delete_ref_overrides(self) -> None:
        """Remove only reference overrides from replacement layers for all selected RESTORE prims."""
        sel_paths = self._get_selected_by_action(self.ActionType.RESTORE)
        if not sel_paths:
            return
        with omni.kit.undo.group():
            for path in sel_paths:
                self._core.remove_prim_reference_overrides(path)

    def _restore_ghost_prim_cb(self) -> None:
        """Clear stale replacement-layer reference list edits for ghost prims.

        A ghost prim has no prototype and no composed references of its own
        (the capture reference that introduced it was already deleted).
        The cleanup targets the parent's prototype, which is the prim that
        originally held the reference arcs.
        """
        sel = self._get_selected_by_action(self.ActionType.RESTOREGHOST)
        if not sel:
            return
        stage = omni.usd.get_context(self._context_name).get_stage()
        seen: set[str] = set()
        with omni.kit.undo.group():
            for path in sel:
                prim = stage.GetPrimAtPath(path)
                if not prim or not prim.IsValid():
                    continue
                parent = prim.GetParent()
                if parent and parent.IsValid():
                    proto = prim_utils.get_prototype(parent)
                    target = str((proto or parent).GetPath())
                    if target in seen:
                        continue
                    seen.add(target)
                    self._core.remove_prim_reference_overrides(target)

    def __del__(self):
        if self._layer_manager is not None:
            self._layer_manager.destroy()
            self._layer_manager = None
        if self._restore_context_menu is not None:
            self._restore_context_menu.destroy()
            self._restore_context_menu = None
