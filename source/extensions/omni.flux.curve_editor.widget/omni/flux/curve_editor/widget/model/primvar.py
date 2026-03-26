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

PrimvarCurveModel - USD primvar-backed curve storage.
"""

from __future__ import annotations

from typing import Any
import omni.kit.commands
import omni.usd
from pxr import Tf, Usd

from omni.flux.fcurve.widget import FCurve

from .base import CurveModel
from .primvar_io import read_curve_from_primvars, snapshot_primvar_values, write_curve_to_prim

__all__ = ["PrimvarCurveModel"]


class PrimvarCurveModel(CurveModel):
    """
    CurveModel implementation backed by USD primvars.

    Each curve is stored as a set of primvars on a prim (uniform variability):
        - primvars:<curve_id>:times (double[])
        - primvars:<curve_id>:values (double[])
        - primvars:<curve_id>:inTangentTypes (token[])
        - primvars:<curve_id>:outTangentTypes (token[])
        - primvars:<curve_id>:inTangentTimes (double[])
        - primvars:<curve_id>:inTangentValues (double[])
        - primvars:<curve_id>:outTangentTimes (double[])
        - primvars:<curve_id>:outTangentValues (double[])
        - primvars:<curve_id>:preInfinity (token)
        - primvars:<curve_id>:postInfinity (token)

    Args:
        prim_path: USD prim path to store curves on.
        curve_ids: List of curve identifiers to manage.
        usd_context_name: USD context name. Defaults to "" (default context).
    """

    def __init__(
        self,
        prim_path: str,
        curve_ids: list[str],
        usd_context_name: str = "",
        display_names: dict[str, str] | None = None,
    ):
        super().__init__(display_names=display_names)

        self._prim_path = prim_path
        self._curve_ids = list(curve_ids)
        self._usd_context_name = usd_context_name

        prim = self._get_prim()
        if not prim or not prim.IsValid():
            raise ValueError(f"PrimvarCurveModel requires a valid prim at {prim_path}")

        self._editing: dict[str, dict[str, Any]] = {}
        self._is_committing = False

        self._usd_listener = Tf.Notice.Register(
            Usd.Notice.ObjectsChanged,
            self._on_usd_objects_changed,
            self._get_stage(),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────────────────

    def _get_stage(self) -> Usd.Stage:
        """Get the USD stage."""
        return omni.usd.get_context(self._usd_context_name).get_stage()

    def _get_prim(self) -> Usd.Prim:
        """Get the prim from stage."""
        return self._get_stage().GetPrimAtPath(self._prim_path)

    # ─────────────────────────────────────────────────────────────────────────
    # Read
    # ─────────────────────────────────────────────────────────────────────────

    def get_curve_ids(self) -> list[str]:
        """Get list of all curve identifiers."""
        return list(self._curve_ids)

    def get_curve(self, curve_id: str) -> FCurve | None:
        """Get a curve by ID. Returns None if not found."""
        if curve_id not in self._curve_ids:
            return None
        return read_curve_from_primvars(self._get_prim(), curve_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Write
    # ─────────────────────────────────────────────────────────────────────────

    def commit_curve(self, curve_id: str, curve: FCurve) -> None:
        """
        Write an entire curve to USD primvars.

        During a continuous edit (between begin_edit/end_edit), writes directly
        to USD without creating undo entries.

        Outside of continuous edits, creates a single undoable Kit command.
        """
        if curve_id not in self._curve_ids:
            raise ValueError(f"curve_id not in managed curves: {curve_id}")

        self._is_committing = True
        try:
            if curve_id in self._editing:
                write_curve_to_prim(self._get_prim(), curve_id, curve)
            else:
                omni.kit.commands.execute(
                    "SetCurvePrimvars",
                    prim_path=self._prim_path,
                    curve_id=curve_id,
                    curve=curve,
                    usd_context_name=self._usd_context_name,
                )
        finally:
            self._is_committing = False

    # ─────────────────────────────────────────────────────────────────────────
    # Continuous Editing (drag operations)
    # ─────────────────────────────────────────────────────────────────────────

    def begin_edit(self, curve_id: str) -> None:
        """Snapshot current USD values before a continuous edit begins."""
        if curve_id not in self._editing:
            self._editing[curve_id] = snapshot_primvar_values(self._get_prim(), curve_id)

    def end_edit(self, curve_id: str) -> None:
        """Finalize a continuous edit by creating a single undoable command.

        The undo target is the snapshot taken at :meth:`begin_edit`, so undo
        restores to the state before the drag started.  If another source
        modifies the same primvars during the drag (e.g. an async resolver,
        a ``Tf.Notice`` callback, or a background script), those changes will
        be silently overwritten by the final commit.  A proper fix would
        require compare-and-swap or per-attribute dirty tracking.
        """
        old_values = self._editing.pop(curve_id, None)
        if old_values is None:
            return

        final_curve = read_curve_from_primvars(self._get_prim(), curve_id)
        if final_curve is None:
            return

        omni.kit.commands.execute(
            "SetCurvePrimvars",
            prim_path=self._prim_path,
            curve_id=curve_id,
            curve=final_curve,
            usd_context_name=self._usd_context_name,
            old_values=old_values,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # USD Change Notification
    # ─────────────────────────────────────────────────────────────────────────

    def _on_usd_objects_changed(self, notice: Usd.Notice.ObjectsChanged, stage: Usd.Stage) -> None:
        """Handle USD stage changes for reactive UI updates."""
        if self._is_committing:
            return
        if stage != self._get_stage():
            return

        # Check if any of our primvars changed
        changed_paths = set()
        for path in notice.GetChangedInfoOnlyPaths():
            changed_paths.add(str(path))
        for path in notice.GetResyncedPaths():
            changed_paths.add(str(path))

        # Check each curve
        for curve_id in self._curve_ids:
            prefix = f"{self._prim_path}.primvars:{curve_id}"
            for changed_path in changed_paths:
                if changed_path.startswith(prefix):
                    self._notify(curve_id)
                    break

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def destroy(self) -> None:
        """Clean up resources."""
        self._editing.clear()
        if self._usd_listener:
            self._usd_listener.Revoke()
            self._usd_listener = None
        super().destroy()
