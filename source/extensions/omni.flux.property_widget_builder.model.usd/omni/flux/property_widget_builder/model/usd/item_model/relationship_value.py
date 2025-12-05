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

__all__ = ["UsdRelationshipValueModel"]

import omni.kit.commands
import omni.usd
from omni.flux.property_widget_builder.widget import ItemValueModel as _ItemValueModel
from pxr import Sdf

from ..utils import get_item_relationships as _get_item_relationships
from ..utils import is_relationship_overridden as _is_relationship_overridden


class UsdRelationshipValueModel(_ItemValueModel):
    """
    Value model for USD relationships.

    Parallel to UsdAttributeBase but for relationships.
    Handles reading/writing single-target relationship using proper USD commands.
    """

    def __init__(
        self,
        context_name: str,
        relationship_paths: list[Sdf.Path],
        read_only: bool = False,
    ):
        """
        Initialize relationship value model.

        Args:
            context_name: USD context name
            relationship_paths: Paths to relationship properties
            read_only: Whether relationship can be modified
        """
        super().__init__()
        self._context_name = context_name
        self._stage = omni.usd.get_context(context_name).get_stage()  # type: ignore[union-attr]
        self._relationship_paths = relationship_paths
        self._read_only = read_only

        self._value: str = ""
        self._is_mixed: bool = False
        self._relationships = _get_item_relationships(self._stage, self._relationship_paths)

        self._read_value_from_usd()

    @property
    def context_name(self):
        return self._context_name

    @property
    def stage(self):
        return self._stage

    @property
    def read_only(self):
        return self._read_only

    @property
    def is_mixed(self):  # type: ignore[override]
        return self._is_mixed

    @property
    def is_overriden(self):
        """Note: Framework uses 'overriden' (typo kept for compatibility)."""
        return _is_relationship_overridden(self._stage, self._relationships)

    @property
    def is_default(self):
        return not bool(self._value)

    def _read_value_from_usd(self) -> bool:
        """
        Read relationship targets from USD.

        Returns:
            True if value changed, False otherwise
        """
        if not self._stage:
            return False

        last_value = None
        values_read = 0
        value_changed = False
        is_mixed = False

        for rel_path in self._relationship_paths:
            prim = self._stage.GetPrimAtPath(rel_path.GetPrimPath())
            if not prim.IsValid():
                continue

            rel = prim.GetRelationship(rel_path.name)
            if not rel or not rel.IsValid():
                continue

            targets = rel.GetTargets()
            value = str(targets[0]) if targets else ""

            if values_read == 0:
                last_value = value
                if self._value != value:
                    self._value = value
                    value_changed = True
            elif last_value != value:
                is_mixed = True

            values_read += 1

        if self._is_mixed != is_mixed:
            value_changed = True
        self._is_mixed = is_mixed

        return value_changed

    def _set_value(self, value: str):
        """Set relationship target using SetRelationshipTargets command."""
        if self._read_only or not self._stage:
            return

        self._value = value if value else ""

        for rel_path in self._relationship_paths:
            prim = self._stage.GetPrimAtPath(rel_path.GetPrimPath())
            if not prim.IsValid():
                continue

            rel = prim.GetRelationship(rel_path.name)
            if not rel or not rel.IsValid():
                continue

            target_paths = [Sdf.Path(value)] if value and value.strip() else []

            omni.kit.commands.execute(
                "SetRelationshipTargets",
                relationship=rel,
                targets=target_paths,
            )

        self._value_changed()

    def get_value(self) -> str:
        """Get current relationship target as string."""
        return self._value

    def _get_value_as_string(self) -> str:
        return "<Mixed>" if self._is_mixed else self._value

    def _get_value_as_float(self) -> float:
        return 0.0

    def _get_value_as_bool(self) -> bool:
        return bool(self._value)

    def _get_value_as_int(self) -> int:
        return 0

    def _on_dirty(self):
        self._value_changed()

    def refresh(self):
        """Refresh value from USD."""
        if self._read_value_from_usd():
            self._value_changed()
