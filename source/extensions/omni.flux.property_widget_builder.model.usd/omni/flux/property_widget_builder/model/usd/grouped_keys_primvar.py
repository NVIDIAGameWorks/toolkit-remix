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

import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import carb
import omni.kit.commands
import omni.usd
from omni.flux.utils.common.interactive_usd_notices import InteractionToken, begin_interaction, end_interaction
from omni.flux.utils.widget import GroupedKeysModel, GroupedKeysPayload
from pxr import Tf, Usd

from .commands import (
    _snapshot_group_payload,
    _snapshot_targets,
    _write_payload_to_targets,
)
from .extension import get_usd_listener_instance
from .listener import DisableAllListenersBlock
from .logical_row import LogicalGroupDefinition

if TYPE_CHECKING:
    from .items import _BaseUSDAttributeItem

__all__ = ["PropertyGroupedKeysModel"]


class PropertyGroupedKeysModel(GroupedKeysModel):
    """USD-backed grouped-key model shared by property-panel curve and gradient editors.

    This class owns the storage and lifecycle details for grouped primvar editors. It opens and closes
    interactive USD notice sessions through ``begin_session`` and ``finish_session``, registers the USD
    object-change listener while the editor is live, suppresses the property-panel listener during self-authored
    writes, defers USD notices for grouped writes/restores, and uses an internal commit flag to ignore its own
    USD change notices. Continuous edits are bracketed with ``begin_edit`` and ``end_edit`` so drag-like changes
    write directly during interaction and collapse to one undoable command at the end. This is the shared
    replacement for the old quiet curve model behavior; curve and gradient adapters should only provide
    constructor wiring and widget-facing affordances such as ``pre_open_callback``.
    """

    @staticmethod
    def from_item(item: _BaseUSDAttributeItem) -> PropertyGroupedKeysModel:
        """Create a USD grouped-key model from a logical USD property row item.

        Args:
            item: Primary property row item claimed for a logical grouped-key editor.

        Returns:
            USD grouped-key model configured from the row-owned logical group API.

        Raises:
            ValueError: If the row does not have a logical group definition.
        """
        logical_group_definition = item.logical_group_definition
        if logical_group_definition is None:
            raise ValueError(f"{PropertyGroupedKeysModel.__name__} requires a logical group definition")

        base_name = PropertyGroupedKeysModel._get_item_base_name(item)
        return PropertyGroupedKeysModel(
            prim_paths=item.get_target_paths(),
            group_ids=[base_name] if base_name is not None else [],
            logical_group_definition=logical_group_definition,
            usd_context_name=item.context_name,
            mixed_group_ids={base_name} if base_name is not None and item.get_row_state().is_mixed else set(),
            pre_open_callback=item.pre_open_callback,
        )

    @staticmethod
    def _get_item_base_name(item: _BaseUSDAttributeItem) -> str | None:
        """Return the logical group base name represented by a property row item.

        Args:
            item: Property row item with logical group metadata.

        Returns:
            Full USD base name for the logical group, or ``None`` when the row has no attribute path.
        """
        if item.logical_group_definition is None or not item.attribute_paths:
            return None
        attr_name = item.attribute_paths[0].name
        if attr_name is None:
            return None
        return item.logical_group_definition.get_base_name(attr_name)

    def __init__(
        self,
        prim_paths: list[str],
        group_ids: list[str],
        logical_group_definition: LogicalGroupDefinition,
        usd_context_name: str = "",
        display_names: dict[str, str] | None = None,
        mixed_group_ids: set[str] | None = None,
        pre_open_callback: Callable[[Callable[[], None]], None] | None = None,
        auto_begin_session: bool = False,
    ) -> None:
        """Create a USD-backed grouped-key model for already-defined schema attributes.

        Args:
            prim_paths: Ordered selected prim paths to read/write. The last path is the editor source.
            group_ids: Full USD base names for managed logical groups, such as ``primvars:particle:color``.
            logical_group_definition: Suffix definition that maps each group id to concrete USD attrs.
            usd_context_name: USD context containing the targets.
            display_names: Optional UI labels keyed by full group id.
            mixed_group_ids: Groups known to be mixed before the editor opens.
            pre_open_callback: Optional callback run by adapters before opening an editor.
            auto_begin_session: Whether to immediately start the USD notice/listener session.
        """
        super().__init__(display_names=display_names)
        self._prim_paths = list(prim_paths)
        if not self._prim_paths:
            raise ValueError(f"{type(self).__name__} requires at least one prim path")
        self._source_prim_path = self._prim_paths[-1]
        self._group_ids = list(group_ids)
        self._logical_group_definition = logical_group_definition
        self._usd_context_name = usd_context_name
        self._mixed_group_ids = set(mixed_group_ids or set())
        self._pre_open_callback = pre_open_callback
        self._editing: dict[str, dict[str, GroupedKeysPayload]] = {}
        self._is_committing = False
        self._usd_listener = None
        self._usd_notice_token = None
        self._destroyed = False

        prim = self._get_prim()
        if not prim or not prim.IsValid():
            raise ValueError(f"{type(self).__name__} requires a valid prim at {self._source_prim_path}")

        if auto_begin_session:
            self.begin_session()

    @property
    def pre_open_callback(self) -> Callable[[Callable[[], None]], None] | None:
        """Optional adapter callback run before opening the widget editor.

        Returns:
            Callback that accepts the final open action, or ``None``.
        """
        return self._pre_open_callback

    @property
    def usd_notice_token(self) -> InteractionToken | None:
        """Active interactive USD notice token, if this model has an open session.

        Returns:
            Current deferred-notice interaction token, or ``None``.
        """
        return self._usd_notice_token

    @property
    def usd_listener(self) -> Tf.Notice.Listener | None:
        """Active Tf.Notice listener for external USD changes, if registered.

        Returns:
            Current USD object-change listener, or ``None``.
        """
        return self._usd_listener

    def begin_session(self) -> None:
        """Begin an idempotent USD interaction/listener session for this editor."""
        stage = self._get_stage()
        if self._usd_notice_token is None:
            self._usd_notice_token = begin_interaction(stage)
        if self._usd_listener is None:
            self._usd_listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_usd_objects_changed, stage)

    def finish_session(self) -> None:
        """Finish any active edit and tear down this model's USD listener/session."""
        for group_id in tuple(self._editing):
            try:
                self.end_edit(group_id)
            except (RuntimeError, ValueError) as exc:
                carb.log_warn(f"Failed to finalize grouped-key edit for {group_id!r}: {exc}")
        self.revoke_usd_listener()
        self._end_usd_notice_interaction()

    def revoke_usd_listener(self) -> None:
        """Revoke the object-change listener without ending the deferred notice session."""
        listener = self._usd_listener
        self._usd_listener = None
        if listener is not None:
            try:
                listener.Revoke()
            except Exception as exc:  # noqa: BLE001 - listener cleanup must be best-effort.
                carb.log_warn(f"Failed to revoke grouped-key USD notice listener: {exc}")

    @property
    def group_ids(self) -> list[str]:
        """Return full USD base names for every managed logical group.

        Returns:
            Copy of managed group ids.
        """
        return list(self._group_ids)

    def get_payload(self, group_id: str) -> GroupedKeysPayload | None:
        """Read the source prim's suffix-keyed payload for one full USD group id.

        Args:
            group_id: Full USD base name for the logical group.

        Returns:
            Suffix-keyed payload from the source prim, or ``None`` when unavailable.
        """
        if group_id not in self._group_ids:
            return None
        return _snapshot_group_payload(self._get_prim(), self._logical_group_definition, group_id)

    def commit_payload(self, group_id: str, payload: GroupedKeysPayload) -> None:
        """Commit one complete grouped payload to all targets.

        During an interactive edit this writes directly under listener suppression. Outside an edit it uses the
        undoable ``SetDataPrimvars`` command, with mixed groups first flattened into one per-target undo snapshot.

        Args:
            group_id: Full USD base name for the logical group.
            payload: Complete suffix-keyed payload to commit.
        """
        self._validate_group_id(group_id)
        with self._suppress_panel_listener():
            if group_id in self._editing:
                self._with_commit_flag(
                    lambda: _write_payload_to_targets(
                        self._get_stage(), self._prim_paths, self._logical_group_definition, group_id, payload
                    )
                )
                return
            if group_id in self._mixed_group_ids:
                self._with_commit_flag(lambda: self._commit_mixed_group_as_single_undo(group_id, payload))
                self._mixed_group_ids.discard(group_id)
                return
            self._with_commit_flag(
                lambda: omni.kit.commands.execute(
                    "SetDataPrimvars",
                    prim_paths=self._prim_paths,
                    group_id=group_id,
                    payload=payload,
                    logical_group_definition=self._logical_group_definition,
                    usd_context_name=self._usd_context_name,
                    stage=self._get_stage(),
                )
            )

    def begin_edit(self, group_id: str) -> None:
        """Start a continuous edit and capture per-target undo snapshots.

        Args:
            group_id: Full USD base name for the logical group.
        """
        self._validate_group_id(group_id)
        if group_id in self._mixed_group_ids:
            self._flatten_mixed_group(group_id)
        if group_id in self._editing:
            return
        self._editing[group_id] = _snapshot_targets(
            self._get_stage(), self._prim_paths, self._logical_group_definition, group_id
        )

    def end_edit(self, group_id: str) -> None:
        """Finish a continuous edit and collapse changed direct writes into one undo command.

        Args:
            group_id: Full USD base name for the logical group.
        """
        old_values = self._editing.pop(group_id, None)
        if old_values is None:
            return
        final_payload = self.get_payload(group_id)
        if final_payload is None:
            return
        current = _snapshot_targets(self._get_stage(), self._prim_paths, self._logical_group_definition, group_id)
        if current == old_values:
            return
        with self._suppress_panel_listener():
            self._with_commit_flag(
                lambda: omni.kit.commands.execute(
                    "SetDataPrimvars",
                    prim_paths=self._prim_paths,
                    group_id=group_id,
                    payload=final_payload,
                    logical_group_definition=self._logical_group_definition,
                    usd_context_name=self._usd_context_name,
                    stage=self._get_stage(),
                    old_values=old_values,
                )
            )

    def destroy(self) -> None:
        """Release USD listeners, pending edit state, and base model subscriptions."""
        if self._destroyed:
            return
        self._destroyed = True
        self.finish_session()
        super().destroy()

    def __del__(self) -> None:
        """Best-effort cleanup for editor paths that are torn down by garbage collection."""
        with contextlib.suppress(Exception):
            self.destroy()

    def _get_stage(self) -> Usd.Stage:
        """Return the model's USD stage.

        Returns:
            Stage resolved from the configured USD context.
        """
        return omni.usd.get_context(self._usd_context_name).get_stage()  # pyright: ignore[reportAttributeAccessIssue]

    def _get_prim(self) -> Usd.Prim:
        """Return the source prim used to load widget payloads.

        Returns:
            Source USD prim for the last selected target path.
        """
        return self._get_stage().GetPrimAtPath(self._source_prim_path)

    def _validate_group_id(self, group_id: str) -> None:
        """Raise when ``group_id`` is not managed by this model.

        Args:
            group_id: Full USD base name to validate.

        Raises:
            ValueError: If ``group_id`` is not managed by this model.
        """
        if group_id not in self._group_ids:
            raise ValueError(f"group_id not in managed groups: {group_id}")

    def _commit_mixed_group_as_single_undo(self, group_id: str, payload: GroupedKeysPayload) -> None:
        """Commit a mixed group using current per-target values as the undo snapshot.

        Args:
            group_id: Full USD base name for the mixed logical group.
            payload: Source payload to apply to every target.
        """
        old_values = _snapshot_targets(self._get_stage(), self._prim_paths, self._logical_group_definition, group_id)
        omni.kit.commands.execute(
            "SetDataPrimvars",
            prim_paths=self._prim_paths,
            group_id=group_id,
            payload=payload,
            logical_group_definition=self._logical_group_definition,
            usd_context_name=self._usd_context_name,
            stage=self._get_stage(),
            old_values=old_values,
        )

    def _flatten_mixed_group(self, group_id: str) -> None:
        """Apply the source payload to every target before starting an edit on a mixed group.

        Args:
            group_id: Full USD base name for the mixed logical group.
        """
        payload = self.get_payload(group_id)
        if payload is None:
            self._mixed_group_ids.discard(group_id)
            return
        with self._suppress_panel_listener():
            self._with_commit_flag(
                lambda: omni.kit.commands.execute(
                    "SetDataPrimvars",
                    prim_paths=self._prim_paths,
                    group_id=group_id,
                    payload=payload,
                    logical_group_definition=self._logical_group_definition,
                    usd_context_name=self._usd_context_name,
                    stage=self._get_stage(),
                )
            )
        self._mixed_group_ids.discard(group_id)

    def _on_usd_objects_changed(self, notice: Usd.Notice.ObjectsChanged, stage: Usd.Stage) -> None:
        """Refresh mixed state for groups touched by external USD notices.

        Args:
            notice: USD object-change notice.
            stage: Stage that emitted the notice.
        """
        if self._is_committing or stage != self._get_stage():
            return
        changed_paths = [str(path) for path in notice.GetChangedInfoOnlyPaths()]
        changed_paths.extend(str(path) for path in notice.GetResyncedPaths())
        if not changed_paths:
            return
        for group_id in self._group_ids:
            if not self._notice_touches_group(group_id, changed_paths):
                continue
            if self._is_group_mixed(group_id):
                self._mixed_group_ids.add(group_id)
            else:
                self._mixed_group_ids.discard(group_id)
            self._notify(group_id)

    def _notice_touches_group(self, group_id: str, changed_paths: list[str]) -> bool:
        """Return whether any changed USD path belongs to this logical group on a target prim.

        Args:
            group_id: Full USD base name for the logical group.
            changed_paths: Changed USD paths from a notice.

        Returns:
            ``True`` when any changed path is under the group on a managed target.
        """
        prefixes = tuple(f"{prim_path}.{group_id}:" for prim_path in self._prim_paths)
        return any(changed_path.startswith(prefixes) for changed_path in changed_paths)

    def _is_group_mixed(self, group_id: str) -> bool:
        """Return whether this logical group has different payload values across targets.

        Args:
            group_id: Full USD base name for the logical group.

        Returns:
            ``True`` when target payload signatures differ.
        """
        return self._logical_group_definition.is_mixed(self._usd_context_name, self._prim_paths, group_id)

    def _with_commit_flag(self, callback: Callable[[], None]) -> None:
        """Run ``callback`` while self-authored USD notices are ignored.

        Args:
            callback: Write operation to execute under the commit flag.
        """
        was_committing = self._is_committing
        self._is_committing = True
        try:
            callback()
        finally:
            self._is_committing = was_committing

    def _suppress_panel_listener(self) -> contextlib.AbstractContextManager:
        """Temporarily suppress the broad property-panel listener during self-authored writes."""
        listener = get_usd_listener_instance()
        return DisableAllListenersBlock(listener) if listener is not None else contextlib.nullcontext()

    def _end_usd_notice_interaction(self) -> None:
        """End and clear the active deferred USD notice token."""
        token = self._usd_notice_token
        self._usd_notice_token = None
        if token is not None:
            end_interaction(token)
