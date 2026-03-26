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

CurveModel - Abstract interface for curve data storage.

This module defines the minimal interface for curve persistence backends.
The model uses FCurve/FCurveKey types from omni.flux.fcurve.widget directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from omni.flux.fcurve.widget import FCurve
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription

__all__ = ["CurveModel"]


class CurveModel(ABC):
    """
    Abstract interface for curve data storage.

    Implementations provide the actual storage backend (USD primvars, memory, etc.)

    Core operations:
    - get_curve_ids(): List all curves
    - get_curve(): Read a curve (returns None if not found)
    - commit_curve(): Write an entire curve (create or update)

    The "commit entire curve" pattern is intentional:
    - Simple: one code path for all modifications
    - Self-correcting: no accumulated delta errors
    - Storage-friendly: backends like USD reauthor entire arrays anyway

    Raises:
        ValueError: On write to an unmanaged curve_id.
    """

    def __init__(self, display_names: dict[str, str] | None = None):
        self._on_change = _Event()
        self._display_names: dict[str, str] = dict(display_names) if display_names else {}

    # ─────────────────────────────────────────────────────────────────────────
    # Read
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def get_curve_ids(self) -> list[str]:
        """
        Get list of all curve identifiers.

        Returns:
            List of curve ID strings.
        """
        raise NotImplementedError

    @abstractmethod
    def get_curve(self, curve_id: str) -> FCurve | None:
        """
        Get a curve by ID.

        Args:
            curve_id: The curve identifier.

        Returns:
            The FCurve data, or None if curve doesn't exist.
        """
        raise NotImplementedError

    def get_display_name(self, curve_id: str) -> str:
        """
        Get a human-readable display name for a curve.

        Looks up the display_names mapping first, falls back to curve_id.
        Subclasses can override for custom logic.

        Args:
            curve_id: The curve identifier.

        Returns:
            A display name for UI presentation.
        """
        return self._display_names.get(curve_id, curve_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Write
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def commit_curve(self, curve_id: str, curve: FCurve) -> None:
        """
        Write an entire curve to storage.

        This is the ONLY write method. It handles both creation and updates.
        The implementation should:
        - Create the curve if it doesn't exist
        - Replace the entire curve if it does exist
        - Make the operation undoable (via commands if applicable)

        Args:
            curve_id: The curve identifier.
            curve: The complete FCurve data to write.

        Raises:
            ValueError: If curve_id is not a managed curve.
        """
        raise NotImplementedError

    # ─────────────────────────────────────────────────────────────────────────
    # Continuous Editing (drag operations)
    # ─────────────────────────────────────────────────────────────────────────

    def begin_edit(self, curve_id: str) -> None:  # noqa: B027
        """Signal that a continuous edit (drag) is starting.

        During a continuous edit, commit_curve may be called many times per
        second. Implementations can optimize for this (e.g., write directly
        to USD without creating undo entries, then create a single undoable
        command at end_edit).

        Args:
            curve_id: The curve being edited.
        """
        pass

    def end_edit(self, curve_id: str) -> None:  # noqa: B027
        """Signal that a continuous edit (drag) has ended.

        Called after the final commit_curve for this drag operation.
        Implementations should finalize any pending undo state.

        Args:
            curve_id: The curve that was edited.
        """
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Change Notifications (backend → UI)
    # ─────────────────────────────────────────────────────────────────────────

    def subscribe(self, callback: Callable[[str], None]) -> _EventSubscription:
        """
        Subscribe to backend changes.

        Called when storage changes externally (undo, redo, external editor).
        The callback receives the curve_id that changed.

        Returns an EventSubscription that auto-unsubscribes when destroyed.
        Caller must hold the returned subscription object.

        Args:
            callback: Function called with curve_id when storage changes.

        Returns:
            Subscription object. Keep reference to maintain subscription.
        """
        return _EventSubscription(self._on_change, callback)

    def _notify(self, curve_id: str) -> None:
        """
        Notify subscribers of a storage change.

        Call this when storage changes externally (not via commit_curve).
        For example: USD undo, external file modification, etc.

        Args:
            curve_id: The curve that changed.
        """
        if self._on_change is not None:
            self._on_change(curve_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def destroy(self) -> None:
        """Clean up resources. Must be called when done."""
        self._on_change = None
