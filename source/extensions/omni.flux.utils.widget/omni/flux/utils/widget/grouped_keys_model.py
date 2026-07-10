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

import copy
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from omni.flux.utils.common import Event, EventSubscription

__all__ = ["GroupedKeysModel", "GroupedKeysPayload", "InMemoryGroupedKeysModel"]

GroupedKeysPayload = dict[str, Any]


def _copy_payload(payload: GroupedKeysPayload | None) -> GroupedKeysPayload | None:
    """Return a defensive copy of a grouped-key payload.

    Args:
        payload: Payload to copy, or ``None``.

    Returns:
        Deep copy of ``payload`` or ``None``.
    """
    return copy.deepcopy(payload) if payload is not None else None


class GroupedKeysModel(ABC):
    """Shared grouped-key payload interface for curve and gradient editors."""

    def __init__(self, display_names: dict[str, str] | None = None) -> None:
        """Create a grouped-key model with optional display labels keyed by group id.

        Args:
            display_names: Optional UI labels keyed by group id.
        """
        self._on_change: Event | None = Event()
        self._display_names: dict[str, str] = dict(display_names) if display_names else {}

    @property
    @abstractmethod
    def group_ids(self) -> list[str]:
        """Return every editable group id managed by this model."""
        raise NotImplementedError

    @abstractmethod
    def get_payload(self, group_id: str) -> GroupedKeysPayload | None:
        """Return a suffix-keyed payload for ``group_id`` or ``None`` when no data exists.

        Args:
            group_id: Group id to read.

        Returns:
            Suffix-keyed payload, or ``None``.
        """
        raise NotImplementedError

    @abstractmethod
    def commit_payload(self, group_id: str, payload: GroupedKeysPayload) -> None:
        """Commit the full suffix-keyed payload for ``group_id``.

        Args:
            group_id: Group id to update.
            payload: Complete suffix-keyed payload to store.
        """
        raise NotImplementedError

    def begin_edit(self, group_id: str) -> None:  # noqa: B027
        """Signal that a continuous interactive edit for ``group_id`` is starting.

        Args:
            group_id: Group id being edited.
        """

    def end_edit(self, group_id: str) -> None:  # noqa: B027
        """Signal that a continuous interactive edit for ``group_id`` has ended.

        Args:
            group_id: Group id whose edit finished.
        """

    def subscribe(self, callback: Callable[[str], None]) -> EventSubscription:
        """Subscribe to external model changes for one group id.

        Args:
            callback: Function invoked with the changed group id.

        Returns:
            Subscription handle that keeps the callback registered.
        """
        if self._on_change is None:
            self._on_change = Event()
        return EventSubscription(self._on_change, callback)

    def get_display_name(self, group_id: str) -> str:
        """Return a human-readable display name for ``group_id``.

        Args:
            group_id: Group id to display.

        Returns:
            Configured display name, or ``group_id``.
        """
        return self._display_names.get(group_id, group_id)

    def _notify(self, group_id: str) -> None:
        """Notify subscribers that one group changed externally.

        Args:
            group_id: Changed group id.
        """
        if self._on_change is not None:
            self._on_change(group_id)

    def destroy(self) -> None:
        """Release model resources."""
        self._on_change = None


class InMemoryGroupedKeysModel(GroupedKeysModel):
    """Simple in-memory grouped-key model for tests and temporary editor state."""

    def __init__(
        self,
        group_ids: list[str] | None = None,
        payloads: dict[str, GroupedKeysPayload] | None = None,
        display_names: dict[str, str] | None = None,
    ) -> None:
        """Create an in-memory grouped-key model.

        Args:
            group_ids: Optional allowed group ids. When omitted, ids come from stored payloads.
            payloads: Initial suffix-keyed payloads keyed by group id.
            display_names: Optional UI labels keyed by group id.
        """
        super().__init__(display_names=display_names)
        self._allowed_ids: list[str] | None = list(group_ids) if group_ids else None
        self._allowed_id_set: set[str] | None = set(group_ids) if group_ids else None
        self._payloads: dict[str, GroupedKeysPayload] = {}
        if payloads:
            for group_id, payload in payloads.items():
                self._payloads[group_id] = copy.deepcopy(payload)

    @property
    def group_ids(self) -> list[str]:
        """Return allowed group ids or the ids currently carrying payloads.

        Returns:
            Copy of current group ids.
        """
        if self._allowed_ids is not None:
            return list(self._allowed_ids)
        return list(self._payloads.keys())

    def get_payload(self, group_id: str) -> GroupedKeysPayload | None:
        """Return a defensive copy of one stored payload.

        Args:
            group_id: Group id to read.

        Returns:
            Stored payload copy, or ``None``.
        """
        return _copy_payload(self._payloads.get(group_id))

    def commit_payload(self, group_id: str, payload: GroupedKeysPayload) -> None:
        """Store a defensive copy of one payload.

        Args:
            group_id: Group id to write.
            payload: Complete suffix-keyed payload.
        """
        if self._allowed_id_set is not None and group_id not in self._allowed_id_set:
            raise ValueError(f"group_id not in allowed groups: {group_id}")
        self._payloads[group_id] = copy.deepcopy(payload)

    def simulate_external_change(self, group_id: str, payload: GroupedKeysPayload) -> None:
        """Store ``payload`` and notify subscribers as if an external backend changed.

        Args:
            group_id: Group id whose payload changed externally.
            payload: Complete suffix-keyed payload to store before notifying.
        """
        self.commit_payload(group_id, payload)
        self._notify(group_id)

    def destroy(self) -> None:
        """Clear stored payloads and release subscriptions."""
        self._payloads.clear()
        super().destroy()
