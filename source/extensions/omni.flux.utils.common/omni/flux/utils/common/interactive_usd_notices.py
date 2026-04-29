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

import itertools
from collections.abc import Callable
from dataclasses import dataclass, field

from pxr import Sdf, Tf, Usd

__all__ = [
    "AggregatedObjectsChangedNotice",
    "InteractionToken",
    "InteractiveUsdNoticeService",
    "ListenerSubscription",
    "begin_interaction",
    "end_interaction",
    "get_interactive_usd_notice_service",
    "is_any_interaction_active",
    "register_interaction_end_listener",
    "register_objects_changed_listener",
]

_LISTENER_IDS = itertools.count(1)
_StageKey = tuple[str, str]
_InteractionEndCallback = Callable[[Usd.Stage], None]


@dataclass(slots=True)
class AggregatedObjectsChangedNotice:
    """ObjectsChanged-compatible view over notices merged during one interaction."""

    _changed_info_only_paths: tuple[Sdf.Path, ...]
    _resynced_paths: tuple[Sdf.Path, ...]
    _changed_fields_by_path: dict[Sdf.Path, tuple[str, ...]]

    def get_changed_info_only_paths(self) -> tuple[Sdf.Path, ...]:
        """Return paths whose object metadata changed without resyncing.

        Returns:
            Paths whose object metadata changed without resyncing.
        """

        return self._changed_info_only_paths

    def get_resynced_paths(self) -> tuple[Sdf.Path, ...]:
        """Return paths that were resynced by the merged notices.

        Returns:
            Paths that were resynced by the merged notices.
        """

        return self._resynced_paths

    def get_changed_fields(self, path: Sdf.Path) -> tuple[str, ...]:
        """Return changed field names for a path.

        Args:
            path: Path to inspect in the merged notice.

        Returns:
            Changed field names for the path, or an empty tuple when none were tracked.
        """

        return self._changed_fields_by_path.get(path, ())

    GetChangedInfoOnlyPaths = get_changed_info_only_paths
    GetResyncedPaths = get_resynced_paths
    GetChangedFields = get_changed_fields


_ObjectsChangedCallback = Callable[[Usd.Notice.ObjectsChanged | AggregatedObjectsChangedNotice, Usd.Stage], None]


class ListenerSubscription:
    """Application-facing listener handle with the same revoke shape as Tf.Notice.Listener."""

    def __init__(self, revoke_callback: Callable[[], None] | None = None):
        self._revoke_callback = revoke_callback
        self._revoked = False

    def revoke(self) -> None:
        """Revoke the subscription once."""

        if self._revoked:
            return
        self._revoked = True
        if self._revoke_callback is not None:
            self._revoke_callback()
            self._revoke_callback = None

    Revoke = revoke


@dataclass(slots=True, eq=False)
class InteractionToken:
    """Opaque token returned by begin_interaction and consumed by end_interaction.

    Attributes:
        stage: Stage whose notices are being deferred.
        stage_key: Stable key used to match stage wrappers that represent the same stage.
    """

    stage: Usd.Stage
    stage_key: _StageKey | None = None


@dataclass(slots=True)
class _ObjectsChangedListener:
    """Application listener registered against a stable stage key."""

    stage_key: _StageKey
    stage: Usd.Stage
    callback: _ObjectsChangedCallback


@dataclass(slots=True)
class _PendingNotice:
    """Accumulated ObjectsChanged data waiting for the interaction to end."""

    changed_info_only_paths: dict[Sdf.Path, None] = field(default_factory=dict)
    resynced_paths: dict[Sdf.Path, None] = field(default_factory=dict)
    changed_fields_by_path: dict[Sdf.Path, dict[str, None]] = field(default_factory=dict)

    def extend(self, notice: Usd.Notice.ObjectsChanged) -> None:
        """Merge one USD notice into the pending aggregate.

        Args:
            notice: USD notice to merge.
        """

        for path in notice.GetChangedInfoOnlyPaths():
            self.changed_info_only_paths.setdefault(path, None)
            self._merge_changed_fields(notice, path)
        for path in notice.GetResyncedPaths():
            self.resynced_paths.setdefault(path, None)
            self._merge_changed_fields(notice, path)

    def _merge_changed_fields(self, notice: Usd.Notice.ObjectsChanged, path: Sdf.Path) -> None:
        """Merge changed field names from one notice path.

        Args:
            notice: USD notice that owns the changed field data.
            path: Path whose changed fields should be merged.
        """

        changed_fields = notice.GetChangedFields(path) or ()
        if not changed_fields:
            return
        fields = self.changed_fields_by_path.setdefault(path, {})
        for field_name in changed_fields:
            fields.setdefault(field_name, None)

    def build_notice(self) -> AggregatedObjectsChangedNotice:
        """Build the aggregated notice passed to registered callbacks.

        Returns:
            Notice-compatible view over the accumulated paths and fields.
        """

        return AggregatedObjectsChangedNotice(
            tuple(self.changed_info_only_paths.keys()),
            tuple(self.resynced_paths.keys()),
            {path: tuple(fields.keys()) for path, fields in self.changed_fields_by_path.items()},
        )


class InteractiveUsdNoticeService:
    """Share Tf.Notice registrations and defer USD notices while interactions are active.

    This owns one backend Tf.Notice listener per stage key. Callers register normal
    ObjectsChanged callbacks and receive ListenerSubscription handles; the shared
    Tf.Notice listener stays alive until the last callback for that stage is revoked.
    """

    def __init__(self):
        self._active_tokens: dict[_StageKey, set[InteractionToken]] = {}
        self._listeners: dict[int, _ObjectsChangedListener] = {}
        self._stage_listeners: dict[_StageKey, tuple[Usd.Stage, Tf.Notice.Listener]] = {}
        self._pending_notices: dict[_StageKey, _PendingNotice] = {}
        self._interaction_end_listeners: dict[int, _InteractionEndCallback] = {}

    def begin_interaction(self, stage: Usd.Stage | None) -> InteractionToken | None:
        """Start deferring notices for a stage.

        Args:
            stage: Stage whose object-change notices should be deferred.

        Returns:
            Interaction token to pass to `end_interaction`, or None when the stage is unavailable.
        """

        self._prune_stale_stage_listeners()
        stage_key = self._get_stage_key(stage)
        if stage_key is None:
            return None
        if any(listener.stage_key == stage_key for listener in self._listeners.values()):
            self._ensure_stage_listener(stage_key, stage)
        token = InteractionToken(stage, stage_key)
        self._active_tokens.setdefault(stage_key, set()).add(token)
        return token

    def end_interaction(self, token: InteractionToken | None) -> None:
        """End a prior interaction and flush deferred notices when it was the last token.

        Args:
            token: Interaction token returned by `begin_interaction`.
        """

        if token is None:
            return
        stage_key = token.stage_key
        if stage_key is None:
            return
        stage_tokens = self._active_tokens.get(stage_key)
        if not stage_tokens or token not in stage_tokens:
            return
        stage_tokens.remove(token)
        if stage_tokens:
            return
        self._active_tokens.pop(stage_key, None)
        self._flush_pending_notices(stage_key)
        for callback in tuple(self._interaction_end_listeners.values()):
            callback(token.stage)

    def register_objects_changed_listener(
        self,
        stage: Usd.Stage | None,
        callback: _ObjectsChangedCallback,
    ) -> ListenerSubscription:
        """Register an ObjectsChanged callback through the shared per-stage Tf.Notice listener.

        Args:
            stage: Stage whose object-change notices should be observed.
            callback: Function called with either a live USD notice or an aggregated flush notice.

        Returns:
            Subscription handle that revokes the callback registration.
        """

        self._prune_stale_stage_listeners()
        stage_key = self._get_stage_key(stage)
        if stage_key is None:
            return ListenerSubscription()

        self._ensure_stage_listener(stage_key, stage)
        listener_id = next(_LISTENER_IDS)
        self._listeners[listener_id] = _ObjectsChangedListener(
            stage_key,
            stage,
            callback,
        )
        return ListenerSubscription(lambda: self.revoke_listener(listener_id))

    def register_interaction_end_listener(self, callback: _InteractionEndCallback) -> ListenerSubscription:
        """Register a callback fired after deferred notices flush for an ended interaction.

        Args:
            callback: Function called with the stage whose interaction ended.

        Returns:
            Subscription handle that revokes the callback registration.
        """

        listener_id = next(_LISTENER_IDS)
        self._interaction_end_listeners[listener_id] = callback
        return ListenerSubscription(lambda: self.revoke_interaction_end_listener(listener_id))

    def revoke_listener(self, listener_id: int) -> None:
        """Revoke one ObjectsChanged callback and release backend state when unused.

        Args:
            listener_id: Registered callback identifier to revoke.
        """

        record = self._listeners.pop(listener_id, None)
        if record is None or any(listener.stage_key == record.stage_key for listener in self._listeners.values()):
            return
        self._revoke_stage_listener(record.stage_key)

    def revoke_interaction_end_listener(self, listener_id: int) -> None:
        """Revoke one interaction-end callback.

        Args:
            listener_id: Registered callback identifier to revoke.
        """

        self._interaction_end_listeners.pop(listener_id, None)

    def _revoke_stage_listener(self, stage_key: _StageKey) -> None:
        """Revoke backend state for a stage key.

        Args:
            stage_key: Stable stage key whose backend listener and pending state should be removed.
        """

        _, listener = self._stage_listeners.pop(stage_key, (None, None))
        if listener is not None:
            listener.Revoke()
        self._pending_notices.pop(stage_key, None)
        self._active_tokens.pop(stage_key, None)

    def _prune_stale_stage_listeners(self) -> None:
        """Remove listener records whose stage wrappers no longer expose a root layer."""

        stale_stage_keys: set[_StageKey] = set()
        for listener_id, record in tuple(self._listeners.items()):
            if self._get_stage_key(record.stage) is not None:
                continue
            stale_stage_keys.add(record.stage_key)
            self._listeners.pop(listener_id, None)
        for stage_key in stale_stage_keys:
            if not any(listener.stage_key == stage_key for listener in self._listeners.values()):
                self._revoke_stage_listener(stage_key)

    def _ensure_stage_listener(self, stage_key: _StageKey, stage: Usd.Stage) -> None:
        """Ensure a backend Tf.Notice listener exists for a stage key.

        Args:
            stage_key: Stable stage key used for the listener bucket.
            stage: Current USD stage wrapper used for the backend notice registration.
        """

        current = self._stage_listeners.get(stage_key)
        if current is not None:
            current_stage, current_listener = current
            if current_stage is stage:
                return
            current_listener.Revoke()
        self._stage_listeners[stage_key] = (
            stage,
            Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_objects_changed, stage),
        )

    def _on_objects_changed(self, notice: Usd.Notice.ObjectsChanged, sender: Usd.Stage) -> None:
        """Route a USD ObjectsChanged notice to matching listeners or defer it.

        Args:
            notice: Live USD object-change notice.
            sender: Stage that emitted the notice.
        """

        stage_key = self._get_stage_key(sender)
        if stage_key is None:
            return
        listeners = [listener for listener in tuple(self._listeners.values()) if listener.stage_key == stage_key]
        if not listeners:
            return
        if not self._active_tokens.get(stage_key):
            for listener in listeners:
                listener.callback(notice, listener.stage)
            return

        self._pending_notices.setdefault(stage_key, _PendingNotice()).extend(notice)

    def _flush_pending_notices(self, stage_key: _StageKey) -> None:
        """Flush accumulated notices for one stage key.

        Args:
            stage_key: Stable stage key whose pending notice should be delivered.
        """

        pending_notice = self._pending_notices.pop(stage_key, None)
        if pending_notice is None:
            return
        notice = pending_notice.build_notice()
        for listener in tuple(self._listeners.values()):
            if listener.stage_key == stage_key:
                listener.callback(notice, listener.stage)

    @staticmethod
    def _get_stage_key(stage: Usd.Stage | None) -> _StageKey | None:
        """Build a stable key for a USD stage.

        Args:
            stage: Stage wrapper to key.

        Returns:
            Root-layer/session-layer key, or None when the stage is unavailable.
        """

        if stage is None:
            return None
        try:
            root_layer = stage.GetRootLayer()
        except Exception:  # noqa: BLE001
            return None
        if not root_layer:
            return None
        session_layer = stage.GetSessionLayer()
        return root_layer.identifier, session_layer.identifier if session_layer else ""

    def is_any_interaction_active(self) -> bool:
        """Return whether any stage currently has active interaction tokens.

        Returns:
            True if at least one stage has active interaction tokens.
        """

        return any(self._active_tokens.values())


_INTERACTIVE_USD_NOTICE_SERVICE: InteractiveUsdNoticeService | None = None


def get_interactive_usd_notice_service() -> InteractiveUsdNoticeService:
    """Return the process-wide interactive USD notice service.

    Returns:
        Shared interactive USD notice service instance.
    """

    global _INTERACTIVE_USD_NOTICE_SERVICE
    if _INTERACTIVE_USD_NOTICE_SERVICE is None:
        _INTERACTIVE_USD_NOTICE_SERVICE = InteractiveUsdNoticeService()
    return _INTERACTIVE_USD_NOTICE_SERVICE


def begin_interaction(stage: Usd.Stage | None) -> InteractionToken | None:
    """Start deferring USD object notices for a stage.

    Args:
        stage: Stage whose object-change notices should be deferred.

    Returns:
        Interaction token to pass to `end_interaction`, or None when the stage is unavailable.
    """

    return get_interactive_usd_notice_service().begin_interaction(stage)


def end_interaction(token: InteractionToken | None) -> None:
    """End a notice interaction and flush pending notices when appropriate.

    Args:
        token: Interaction token returned by `begin_interaction`.
    """

    get_interactive_usd_notice_service().end_interaction(token)


def register_objects_changed_listener(
    stage: Usd.Stage | None,
    callback: _ObjectsChangedCallback,
) -> ListenerSubscription:
    """Register an ObjectsChanged callback through the shared interactive notice service.

    Args:
        stage: Stage whose object-change notices should be observed.
        callback: Function called with either a live USD notice or an aggregated flush notice.

    Returns:
        Subscription handle that revokes the callback registration.
    """

    return get_interactive_usd_notice_service().register_objects_changed_listener(
        stage,
        callback,
    )


def register_interaction_end_listener(callback: _InteractionEndCallback) -> ListenerSubscription:
    """Register a callback fired after an interaction ends and deferred notices flush.

    Args:
        callback: Function called with the stage whose interaction ended.

    Returns:
        Subscription handle that revokes the callback registration.
    """

    return get_interactive_usd_notice_service().register_interaction_end_listener(callback)


def is_any_interaction_active() -> bool:
    """Return whether any stage currently has active interaction tokens.

    Returns:
        True if at least one stage has active interaction tokens.
    """

    return get_interactive_usd_notice_service().is_any_interaction_active()
