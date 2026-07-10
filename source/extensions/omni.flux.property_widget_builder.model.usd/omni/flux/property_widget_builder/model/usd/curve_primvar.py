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

from omni.flux.utils.widget import GroupedKeysPayload

from .grouped_keys_primvar import PropertyGroupedKeysModel
from .logical_group_constants import CURVE_LOGICAL_GROUP_DEFINITION, PRIMVAR_PREFIX
from .logical_row import LogicalGroupDefinition

__all__ = ["PropertyPrimvarCurveModel"]


class PropertyPrimvarCurveModel(PropertyGroupedKeysModel):
    """Thin curve-editor adapter around the generic USD grouped-key model."""

    def __init__(
        self,
        prim_paths: list[str],
        curve_ids: list[str],
        usd_context_name: str = "",
        display_names: dict[str, str] | None = None,
        mixed_curve_ids: set[str] | None = None,
        logical_group_definition: LogicalGroupDefinition = CURVE_LOGICAL_GROUP_DEFINITION,
    ) -> None:
        """Create an adapter that exposes curve-editor ids over full USD primvar group ids.

        The curve editor works with ids like ``particle:size``. The shared USD persistence model stores
        full base names like ``primvars:particle:size`` so writes can target concrete schema attrs.

        Args:
            prim_paths: Ordered selected prim paths to edit.
            curve_ids: Curve-editor ids or full primvar base names.
            usd_context_name: USD context containing targets.
            display_names: Optional UI labels keyed by curve id or full group id.
            mixed_curve_ids: Curve ids known to differ across targets.
            logical_group_definition: Suffix definition for these curve attrs.
        """
        self._curve_ids = [curve_id.removeprefix(PRIMVAR_PREFIX) for curve_id in curve_ids]
        self._curve_to_group_id = {curve_id: f"{PRIMVAR_PREFIX}{curve_id}" for curve_id in self._curve_ids}
        group_display_names = {
            f"{PRIMVAR_PREFIX}{curve_id.removeprefix(PRIMVAR_PREFIX)}": display_name
            for curve_id, display_name in (display_names or {}).items()
        }
        super().__init__(
            prim_paths=prim_paths,
            group_ids=list(self._curve_to_group_id.values()),
            logical_group_definition=logical_group_definition,
            usd_context_name=usd_context_name,
            display_names=group_display_names,
            mixed_group_ids={
                f"{PRIMVAR_PREFIX}{curve_id.removeprefix(PRIMVAR_PREFIX)}" for curve_id in mixed_curve_ids or set()
            },
            auto_begin_session=True,
        )

    @property
    def group_ids(self) -> list[str]:
        """Return curve-editor ids while the USD model stores full primvar group ids."""
        return list(self._curve_ids)

    def get_display_name(self, group_id: str) -> str:
        """Translate a curve-editor id to the USD group id before resolving display metadata.

        Args:
            group_id: Curve-editor id or full USD primvar group id.

        Returns:
            Display name registered for the corresponding USD group id.
        """
        curve_id = group_id.removeprefix(PRIMVAR_PREFIX)
        return super().get_display_name(self._curve_to_group_id.get(curve_id, group_id))

    def get_payload(self, group_id: str) -> GroupedKeysPayload | None:
        """Translate a curve-editor id to the USD group id before reading grouped payload data.

        Args:
            group_id: Curve-editor id or full USD primvar group id.

        Returns:
            Grouped-key payload for the matching USD group, or ``None`` when
            the group has no readable payload.
        """
        curve_id = group_id.removeprefix(PRIMVAR_PREFIX)
        return super().get_payload(self._curve_to_group_id.get(curve_id, group_id))

    def commit_payload(self, group_id: str, payload: GroupedKeysPayload) -> None:
        """Translate a curve-editor id to the USD group id before committing grouped payload data.

        Args:
            group_id: Curve-editor id or full USD primvar group id.
            payload: Complete suffix-keyed curve payload to commit.
        """
        curve_id = group_id.removeprefix(PRIMVAR_PREFIX)
        super().commit_payload(self._curve_to_group_id.get(curve_id, group_id), payload)

    def begin_edit(self, group_id: str) -> None:
        """Translate a curve-editor id to the USD group id before starting an edit session.

        Args:
            group_id: Curve-editor id or full USD primvar group id.
        """
        curve_id = group_id.removeprefix(PRIMVAR_PREFIX)
        super().begin_edit(self._curve_to_group_id.get(curve_id, group_id))

    def end_edit(self, group_id: str) -> None:
        """Translate a curve-editor id to the USD group id before finishing an edit session.

        Args:
            group_id: Curve-editor id or full USD primvar group id.
        """
        curve_id = group_id.removeprefix(PRIMVAR_PREFIX)
        super().end_edit(self._curve_to_group_id.get(curve_id, group_id))

    def _notify(self, group_id: str) -> None:
        """Translate internal USD group ids back to curve-editor ids before notifying subscribers.

        Args:
            group_id: Curve-editor id or full USD primvar group id that changed.
        """
        super()._notify(group_id.removeprefix(PRIMVAR_PREFIX))
