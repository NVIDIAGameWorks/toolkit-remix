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

__all__ = ["AssetModifierSettings"]

import enum
from typing import TYPE_CHECKING, Any

from carb.settings import get_settings
from lightspeed.trex.asset_modifiers.factory import get_instance as _get_asset_modifier_factory

from .constants import SETTINGS_ROOT

if TYPE_CHECKING:
    from lightspeed.trex.asset_modifiers.factory import AssetModifierBase, ModifierInput


class AssetModifierSettings:
    """Read and update the persistent active modifier and modifier input values."""

    _ACTIVE_MODIFIER_KEY = f"{SETTINGS_ROOT}/active_modifier"

    @property
    def active_modifier_name(self) -> str | None:
        """Return the stored active modifier name."""
        return get_settings().get(self._ACTIVE_MODIFIER_KEY)

    def set_active_modifier_name(self, name: str) -> None:
        """Store the active modifier name and notify listeners."""
        get_settings().set(self._ACTIVE_MODIFIER_KEY, name)
        _get_asset_modifier_factory().notify_changed()

    def get_value(self, modifier: type[AssetModifierBase], item: ModifierInput) -> Any:
        """Return the stored typed value of one modifier input, or its default."""
        value = get_settings().get(self.get_value_key(modifier, item))
        try:
            return item.default if value is None else item.value_type(value)
        except (TypeError, ValueError):
            return item.default

    def set_value(self, modifier: type[AssetModifierBase], item: ModifierInput, value: Any) -> None:
        """Store one modifier input value and notify listeners."""
        # An enum stores its value, which its type rebuilds. str() of a plain Enum member is its qualified name.
        if isinstance(value, enum.Enum):
            value = value.value
        stored = value if isinstance(value, (bool, int, float)) else str(value)
        get_settings().set(self.get_value_key(modifier, item), stored)
        _get_asset_modifier_factory().notify_changed()

    @staticmethod
    def get_modifier_key(modifier: type[AssetModifierBase]) -> str:
        """Return the settings key that holds every stored input value of one modifier."""
        return f"{SETTINGS_ROOT}/modifiers/{modifier.name}"

    @classmethod
    def get_value_key(cls, modifier: type[AssetModifierBase], item: ModifierInput) -> str:
        """Return the settings key of one modifier input value."""
        return f"{cls.get_modifier_key(modifier)}/{item.name}"
