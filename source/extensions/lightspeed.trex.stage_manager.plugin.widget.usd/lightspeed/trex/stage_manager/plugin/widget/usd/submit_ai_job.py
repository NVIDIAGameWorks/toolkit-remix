"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["SubmitAIJobActionWidgetPlugin"]

from typing import TYPE_CHECKING

from lightspeed.common.constants import LayoutFiles
from lightspeed.trex.ai_tools.widget import (
    get_comfy_interface,
    iter_texture_path,
    submit_selected_prims_to_comfy,
)
from lightspeed.trex.utils.widget.quicklayout import load_layout
from pxr import Usd
from omni import ui
from omni.flux.utils.widget.resources import get_quicklayout_config
from omni.kit.notification_manager import NotificationButtonInfo, NotificationStatus, post_notification
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin as _StageManagerMenuMixin
from omni.flux.stage_manager.plugin.widget.usd.base import (
    StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin,
)
from omni.flux.utils.common.menus import MenuGroup as _MenuGroup
from omni.flux.utils.common.menus import MenuItem as _MenuItem
from omni.flux.utils.widget.resources import get_icons as _get_icons

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class SubmitAIJobActionWidgetPlugin(_StageManagerStateWidgetPlugin, _StageManagerMenuMixin):
    def build_icon_ui(
        self,
        model: _StageManagerTreeModel,
        item: _StageManagerTreeItem,
        level: int,
        expanded: bool,
    ):
        comfy = get_comfy_interface()
        workflow = comfy.workflow
        comfy_ready = workflow is not None
        prim_valid = self._is_prim_valid(item.data)

        enabled = comfy_ready and prim_valid

        if not comfy_ready:
            icon = "AIToolsDisabled"
            tooltip = "ComfyUI is not connected or no workflow is selected. Click to open the AI Tools layout."
        elif not prim_valid:
            icon = "AIToolsDisabled"
            tooltip = "AI Tools workflows require mesh or material prims with at least one texture."
        else:
            icon = "AITools"
            tooltip = f"Submit the selection to the '{workflow.name}' workflow with the current AI Tools setup."

        ui.Image(
            "",
            width=self._icon_size,
            height=self._icon_size,
            name=icon,
            tooltip=tooltip,
            identifier="submit_ai_job_widget_image",
            mouse_released_fn=lambda x, y, b, m: self._on_icon_clicked(b, enabled, comfy_ready, model, item),
        )

    def _on_icon_clicked(
        self,
        button: int,
        enabled: bool,
        comfy_ready: bool,
        model: _StageManagerTreeModel,
        item: _StageManagerTreeItem,
    ):
        if button != 0:
            return

        if not comfy_ready:
            self._open_ai_tools_layout()
            return

        if not enabled:
            return

        # TODO StageManager: Ideally don't change selection after action
        self._item_clicked(button, True, model, item)
        self._on_submit_ai_job({})

    @classmethod
    def _get_menu_items(cls):
        submenu_icon = _get_icons("ai-tools-icon")

        submit_btn = {
            "name": _MenuItem.AI_TOOLS_SUBMIT.value,
            "glyph": submenu_icon,
            "onclick_fn": cls._on_submit_ai_job,
            "enabled_fn": cls._is_menu_item_enabled,
        }

        open_layout_btn = {
            "name": _MenuItem.AI_TOOLS_OPEN_LAYOUT.value,
            "glyph": submenu_icon,
            "onclick_fn": cls._open_ai_tools_layout,
        }

        btn_list = [submit_btn, open_layout_btn]
        menu_item_dict = {_MenuItem.AI_TOOLS.value: btn_list}

        return [
            (
                {
                    "name": menu_item_dict,
                    "glyph": submenu_icon,
                    "appear_after": _MenuItem.LOGIC_GRAPH.value,
                },
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            ),
        ]

    @classmethod
    def _is_menu_item_enabled(cls, payload: dict) -> bool:
        if not cls._is_comfy_ready():
            return False
        item = payload.get("right_clicked_item")
        return bool(item) and cls._is_prim_valid(item.data)

    @classmethod
    def _on_submit_ai_job(cls, _: dict):
        try:
            submit_selected_prims_to_comfy()
        except ValueError as exc:
            post_notification(str(exc), status=NotificationStatus.WARNING)
            return
        post_notification(
            "The selection was added to the AI Tools job queue. Open the AI Tools layout to view the job queue.",
            button_infos=[NotificationButtonInfo("Open AI Tools layout", on_complete=cls._open_ai_tools_layout)],
        )

    @classmethod
    def _open_ai_tools_layout(cls, _=None):
        """Open the AI Tools layout."""
        layout = get_quicklayout_config(LayoutFiles.AI_TOOLS)
        if layout:
            load_layout(layout)

    @classmethod
    def _is_prim_valid(cls, prim: Usd.Prim | None) -> bool:
        """Check if a prim is valid for AI tools (has at least one texture path)."""
        if not prim:
            return False
        return next(iter_texture_path(prim), None) is not None

    @classmethod
    def _is_comfy_ready(cls) -> bool:
        """Check if ComfyUI is connected and a workflow is selected."""
        return get_comfy_interface().workflow is not None
