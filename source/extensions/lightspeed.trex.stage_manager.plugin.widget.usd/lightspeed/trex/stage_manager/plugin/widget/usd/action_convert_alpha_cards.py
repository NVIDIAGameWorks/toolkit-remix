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

__all__ = ["ConvertAlphaCardsActionWidgetPlugin"]

import omni.usd
from lightspeed.common.constants import GlobalEventNames
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.trex.alpha_cutout.core import resolve_conversion_target, resolve_conversion_targets
from omni import ui
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel
from omni.flux.stage_manager.plugin.widget.usd.base import StageManagerStateWidgetPlugin
from omni.flux.utils.common.menus import MenuGroup, MenuItem
from omni.flux.utils.widget.resources import get_icons


class ConvertAlphaCardsActionWidgetPlugin(StageManagerStateWidgetPlugin, StageManagerMenuMixin):
    """Experimental context menu action that opens the alpha cutout conversion window."""

    def build_icon_ui(
        self,
        model: StageManagerTreeModel,
        item: StageManagerTreeItem,
        level: int,
        expanded: bool,
    ) -> None:
        # The action lives in the context menu only, so the column cell stays empty.
        ui.Spacer(height=0, width=0)

    @classmethod
    def _is_convertible(cls, payload: dict) -> bool:
        """Return whether the right-clicked prim resolves to a capture mesh or a replacement mesh.

        Args:
            payload: Stage Manager menu payload.

        Returns:
            ``True`` when the clicked prim has a conversion target.
        """
        item = payload.get("right_clicked_item")
        prim = item.data if item else None
        if not prim or not prim.IsValid():
            return False
        return resolve_conversion_target(prim.GetStage(), str(prim.GetPath())) is not None

    @classmethod
    def _request_conversion(cls, payload: dict) -> None:
        """Ask the alpha cutout window to open with the selected meshes.

        Args:
            payload: Stage Manager menu payload with the context, clicked item and selected paths.

        Raises:
            KeyError: If the payload does not contain a context name.
        """
        context_name = payload["context_name"]
        stage = omni.usd.get_context(context_name).get_stage()
        if not stage:
            return
        prim_paths = list(payload.get("selected_paths") or ())
        item = payload.get("right_clicked_item")
        if item and item.data:
            clicked = str(item.data.GetPath())
            if clicked not in prim_paths:
                prim_paths.append(clicked)
        roots = [target.prim_path for target in resolve_conversion_targets(stage, prim_paths)]
        if not roots:
            return
        _get_event_manager_instance().call_global_custom_event(
            GlobalEventNames.ALPHA_CUTOUT_CONVERT_REQUEST.value, roots, context_name
        )

    @classmethod
    def _get_menu_items(cls) -> list[tuple[dict, str, str]]:
        """Return the Experimental submenu with the conversion entry.

        Returns:
            Menu descriptors for the selected-prims menu group.
        """
        icon = get_icons("hexagon-outline")
        convert_button = {
            "name": MenuItem.CONVERT_ALPHA_CARDS.value,
            "glyph": icon,
            "onclick_fn": cls._request_conversion,
            "show_fn": cls._is_convertible,
        }
        return [
            (
                {
                    "name": {MenuItem.EXPERIMENTAL.value: [convert_button]},
                    "glyph": icon,
                    "appear_after": MenuItem.AI_TOOLS.value,
                    "show_fn": cls._is_convertible,
                },
                MenuGroup.SELECTED_PRIMS.value,
                "",
            )
        ]
