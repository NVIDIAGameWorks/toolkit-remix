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

In-memory CurveModel implementation for testing and temporary storage.
"""

from __future__ import annotations

from omni.flux.fcurve.widget import FCurve

from .base import CurveModel

__all__ = ["InMemoryCurveModel"]


class InMemoryCurveModel(CurveModel):
    """
    In-memory implementation of CurveModel.

    Stores curves in memory without any persistence.
    Useful for:
    - Testing
    - Temporary editing before saving to USD
    - Preview/scratchpad functionality
    """

    def __init__(
        self,
        curve_ids: list[str] | None = None,
        display_names: dict[str, str] | None = None,
    ):
        """
        Create an in-memory curve model.

        Args:
            curve_ids: Optional list of allowed curve IDs. If None, any ID is allowed.
            display_names: Optional mapping of curve_id to human-readable display name.
        """
        super().__init__(display_names=display_names)
        self._curves: dict[str, FCurve] = {}
        self._allowed_ids: set[str] | None = set(curve_ids) if curve_ids else None

    def get_curve_ids(self) -> list[str]:
        """Get all curve IDs in this model."""
        return list(self._curves.keys())

    def get_curve(self, curve_id: str) -> FCurve | None:
        """Get a curve by ID."""
        return self._curves.get(curve_id)

    def commit_curve(self, curve_id: str, curve: FCurve) -> None:
        """
        Write an entire curve to memory.

        Args:
            curve_id: The curve identifier.
            curve: The complete FCurve data to store.

        Raises:
            ValueError: If curve_id is not allowed (when curve_ids was specified).
        """
        if self._allowed_ids is not None and curve_id not in self._allowed_ids:
            raise ValueError(f"curve_id not in allowed curves: {curve_id}")

        self._curves[curve_id] = curve

    def simulate_external_change(self, curve_id: str, curve: FCurve) -> None:
        """
        Simulate an external change (for testing undo/redo behavior).

        This stores the curve AND fires the notification, as would happen
        when USD undo/redo modifies the backing storage.
        """
        if self._allowed_ids is not None and curve_id not in self._allowed_ids:
            raise ValueError(f"curve_id not in allowed curves: {curve_id}")

        self._curves[curve_id] = curve
        self._notify(curve_id)

    def destroy(self) -> None:
        """Clean up resources."""
        self._curves.clear()
        super().destroy()
