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

__all__ = ["LightClipboardMenuPlugin"]

from typing import ClassVar

from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin
from omni.flux.stage_manager.factory.plugins.base import StageManagerPluginBase
from omni.flux.utils.common.menus import MenuGroup as _MenuGroup
from omni.flux.utils.common.menus import MenuItem as _MenuItem


class LightClipboardMenuPlugin(StageManagerPluginBase, StageManagerMenuMixin):
    """Provide light copy and paste actions in the Stage Manager menu."""

    # Keep the shared cache out of Pydantic's per-instance model state.
    _cores: ClassVar[dict[str, _AssetReplacementsCore]] = {}

    @classmethod
    def _get_menu_items(cls) -> list[tuple[dict, str, str]]:
        """Return the light clipboard menu registrations."""
        return [
            (
                {
                    "name": "Copy Light",
                    "glyph": "copy.svg",
                    "appear_after": _MenuItem.COPY_PRIM_PATH.value,
                    "onclick_fn": cls._copy_light,
                    "enabled_fn": cls._can_copy_light,
                },
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            ),
            (
                {
                    "name": "Paste Light",
                    "glyph": "copy.svg",
                    "appear_after": "Copy Light",
                    "onclick_fn": cls._paste_light,
                    "enabled_fn": cls._can_paste_light,
                },
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            ),
            (
                {"name": _MenuItem.DYNAMIC_SPLITTER.value, "appear_after": "Paste Light"},
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            ),
        ]

    @classmethod
    def _get_target(cls, payload: dict):
        """Return the shared core and path for a valid right-click payload."""
        context_name = payload.get("context_name")
        item = payload.get("right_clicked_item")
        if context_name is None or not item or not item.data or not item.data.IsValid():
            return None
        core = cls._cores.get(context_name)
        if core is None:
            core = cls._cores[context_name] = _AssetReplacementsCore(context_name)
        return core, str(item.data.GetPath())

    @classmethod
    def unregister_menu(cls):
        """Release context-bound cores with the menu registrations."""
        super().unregister_menu()
        for core in cls._cores.values():
            core.destroy()
        cls._cores.clear()

    @classmethod
    def _can_copy_light(cls, payload: dict) -> bool:
        """Return whether the right-clicked prim is an added light."""
        target = cls._get_target(payload)
        return target is not None and target[0].can_copy_light(target[1])

    @classmethod
    def _copy_light(cls, payload: dict) -> None:
        """Copy the right-clicked light through the shared asset core."""
        target = cls._get_target(payload)
        if target is not None:
            target[0].copy_light_to_clipboard(target[1])

    @classmethod
    def _can_paste_light(cls, payload: dict) -> bool:
        """Return whether the shared asset core accepts the right-clicked target."""
        target = cls._get_target(payload)
        return target is not None and target[0].can_paste_light_from_clipboard(target[1])

    @classmethod
    def _paste_light(cls, payload: dict) -> None:
        """Paste the copied light through the shared asset core."""
        target = cls._get_target(payload)
        if target is not None:
            target[0].paste_light_from_clipboard(target[1])
