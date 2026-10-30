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

__all__ = ["SubmitAssetModifierJobActionWidgetPlugin"]

from typing import TYPE_CHECKING

from lightspeed.common.constants import WindowNames
from lightspeed.trex.asset_modifiers.core import AssetModifiersCore
from lightspeed.trex.asset_modifiers.widget.submitter import AssetModifierSubmitter
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin as _StageManagerMenuMixin
from omni.flux.stage_manager.plugin.widget.usd.base import (
    StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin,
)
from omni.flux.utils.common.menus import MenuGroup as _MenuGroup
from omni.flux.utils.common.menus import MenuItem as _MenuItem
from omni.flux.utils.widget.resources import get_icons as _get_icons
from pxr import Usd

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class SubmitAssetModifierJobActionWidgetPlugin(_StageManagerStateWidgetPlugin, _StageManagerMenuMixin):
    """Provide Stage Manager controls for submitting selected prims to the active asset modifier."""

    def build_icon_ui(
        self,
        model: _StageManagerTreeModel,
        item: _StageManagerTreeItem,
        level: int,
        expanded: bool,
    ):
        """Build the submission icon for the row's prim and the active modifier."""
        core = AssetModifiersCore(self._context_name)
        reason = core.get_selection_block_reason(item.data or Usd.Prim())
        if reason is None:
            name = "VectorSquareEdit"
            tooltip = f"Run '{core.active_modifier.display_name}' for this selection using the current settings."
        else:
            name = "VectorSquareEditDisabled"
            tooltip = f"{reason} Select to open Asset Modifiers."
        self.make_action_image(
            model=model,
            item=item,
            name=name,
            tooltip=tooltip,
            identifier="submit_asset_modifier_job_widget_image",
            mouse_released_fn=lambda _x, _y, button, _modifiers: self._on_icon_clicked(button, model, item),
        )

    def _on_icon_clicked(self, button: int, model: _StageManagerTreeModel, item: _StageManagerTreeItem) -> None:
        """Submit the selection with the clicked row, or open Asset Modifiers when the row cannot run."""
        if button != 0:
            return
        if AssetModifiersCore(self._context_name).get_selection_block_reason(item.data or Usd.Prim()) is not None:
            AssetModifierSubmitter.show_window(WindowNames.ASSET_MODIFIERS.value)
            return
        selected_paths = self._get_action_paths(model, item)
        self._item_clicked(button, True, model, item)
        AssetModifierSubmitter.submit(self._context_name, selected_paths)

    @classmethod
    def _get_menu_items(cls):
        """Return the Asset Modifiers submenu, which follows the AI Tools submenu."""
        icon = _get_icons("vector-square-edit")
        submenu = [
            {
                "name": _MenuItem.ASSET_MODIFIERS_SUBMIT.value,
                "glyph": icon,
                "onclick_fn": cls._on_submit_menu_clicked,
                "enabled_fn": cls._is_menu_item_enabled,
            },
            {
                "name": _MenuItem.ASSET_MODIFIERS_OPEN.value,
                "glyph": icon,
                "onclick_fn": lambda _payload: AssetModifierSubmitter.show_window(WindowNames.ASSET_MODIFIERS.value),
            },
        ]
        return [
            (
                {
                    "name": {_MenuItem.ASSET_MODIFIERS.value: submenu},
                    "glyph": icon,
                    "appear_after": _MenuItem.AI_TOOLS.value,
                },
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            ),
        ]

    @classmethod
    def _is_menu_item_enabled(cls, payload: dict) -> bool:
        """Return whether the right-clicked prim can run the active modifier."""
        item = payload.get("right_clicked_item")
        if not item:
            return False
        return AssetModifiersCore(payload["context_name"]).get_selection_block_reason(item.data or Usd.Prim()) is None

    @classmethod
    def _on_submit_menu_clicked(cls, payload: dict) -> None:
        """Submit the selected prims from the context menu."""
        if cls._is_menu_item_enabled(payload):
            AssetModifierSubmitter.submit(payload["context_name"], list(payload.get("selected_paths") or ()))
