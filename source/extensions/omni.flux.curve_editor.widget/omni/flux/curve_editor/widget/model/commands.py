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

USD Command for curve primvar storage.
"""

from __future__ import annotations

from typing import Any

import omni.kit.commands
import omni.usd
from pxr import Usd

from omni.flux.fcurve.widget import FCurve

from .primvar_io import (
    curve_to_primvar_data,
    restore_primvar_data,
    snapshot_primvar_values,
    write_primvar_data,
)

__all__ = ["SetCurvePrimvarsCommand"]


class SetCurvePrimvarsCommand(omni.kit.commands.Command):
    """
    Atomically set all primvars for a curve.

    This command writes times, values, tangent types, tangents, and infinity types
    in a single undoable operation. On undo, all primvars are restored to their
    previous values.

    Args:
        prim_path: USD path to the prim holding the primvars.
        curve_id: Curve identifier (e.g., "particle:opacity:x").
        curve: The FCurve data to write.
        usd_context_name: USD context name. Defaults to "" (default context).
        stage: Optional stage for testing with in-memory stages.
        old_values: Pre-captured old values for undo. If provided, skips reading
            current values in do(). Used by end_edit to create a single undoable
            command after a continuous drag operation.
    """

    def __init__(
        self,
        prim_path: str,
        curve_id: str,
        curve: FCurve,
        usd_context_name: str = "",
        stage: Usd.Stage | None = None,
        old_values: dict[str, Any] | None = None,
    ):
        self._prim_path = prim_path
        self._curve_id = curve_id
        self._curve = curve
        self._usd_context_name = usd_context_name
        self._stage = stage
        self._old_values: dict[str, Any] = old_values or {}

    def _get_stage(self) -> Usd.Stage:
        """Get the USD stage from context or use injected stage for tests."""
        if self._stage is not None:
            return self._stage
        return omni.usd.get_context(self._usd_context_name).get_stage()

    def do(self) -> None:
        """Execute the command - write curve data to primvars."""
        stage = self._get_stage()
        prim = stage.GetPrimAtPath(self._prim_path)
        if not prim or not prim.IsValid():
            raise ValueError(f"Invalid prim path: {self._prim_path}")

        if not self._old_values:
            self._old_values = snapshot_primvar_values(prim, self._curve_id)

        data = curve_to_primvar_data(self._curve_id, self._curve)
        write_primvar_data(prim, data)

    def undo(self) -> None:
        """Undo the command - restore previous primvar values."""
        stage = self._get_stage()
        prim = stage.GetPrimAtPath(self._prim_path)
        if not prim or not prim.IsValid():
            raise ValueError(f"Cannot undo: prim no longer valid at {self._prim_path}")

        restore_primvar_data(prim, self._old_values)
