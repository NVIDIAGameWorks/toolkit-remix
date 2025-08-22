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

from typing import TYPE_CHECKING

import carb
from lightspeed.common import constants
from lightspeed.trex.viewports.shared.widget import get_active_viewport as _get_active_viewport
from omni import ui, usd
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin as _StageManagerMenuMixin
from omni.flux.stage_manager.plugin.widget.usd.base import (
    StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin,
)
from omni.flux.utils.common.menus import MenuGroup as _MenuGroup
from omni.flux.utils.common.menus import MenuItem as _MenuItem
from omni.flux.utils.widget.resources import get_icons as _get_icons
from pxr import UsdGeom

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class FocusInViewportActionWidgetPlugin(_StageManagerStateWidgetPlugin, _StageManagerMenuMixin):
    def build_icon_ui(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool):
        # Build the icon
        enabled = item.data and UsdGeom.Imageable(item.data)

        if enabled:
            icon = "Frame"
            tooltip = constants.FOCUS_IN_VIEWPORT_TOOLTIP_ENABLED
        else:
            icon = "FrameDisabled"
            tooltip = constants.FOCUS_IN_VIEWPORT_TOOLTIP_DISABLED

        ui.Image(
            "",
            width=self._icon_size,
            height=self._icon_size,
            name=icon,
            tooltip=tooltip,
            enabled=enabled,
            identifier="focus_in_viewport_widget_image",
            mouse_released_fn=lambda x, y, b, m: self._on_icon_clicked(b, enabled, model, item),
        )

    def build_overview_ui(self, model: "_StageManagerTreeModel"):
        pass

    def _on_icon_clicked(
        self, button: int, enabled: bool, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem"
    ):
        if button != 0 or not enabled:
            return

        # TODO StageManager: We change the selection after the selection.
        #  Ideally we don't change the selection after the action is performed to keep multi-selections.

        self._item_clicked(button, True, model, item)
        self._on_frame_on_the_viewport({"context_name": self._context_name})

    @classmethod
    def _get_menu_items(cls):
        frame_icon = _get_icons("frame")
        return [
            (
                {
                    "name": _MenuItem.FOCUS_IN_VIEWPORT.value,
                    "glyph": frame_icon,
                    "appear_after": _MenuItem.COPY_PRIM_PATH.value,
                    "onclick_fn": cls._on_frame_on_the_viewport,
                    "enabled_fn": cls._on_frame_on_the_viewport_enabled_fn,
                },
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            ),
            (
                {
                    "name": _MenuItem.DYNAMIC_SPLITTER.value,
                },
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            ),
        ]

    @classmethod
    def _on_frame_on_the_viewport(cls, payload: dict):
        context = usd.get_context(payload.get("context_name", ""))
        if not context:
            carb.log_error(f"Context not found: {payload.get('context_name', '')}")
            return

        _get_active_viewport().frame_viewport_selection(context.get_selection().get_selected_prim_paths())

    @classmethod
    def _on_frame_on_the_viewport_enabled_fn(cls, payload: dict):
        item = payload.get("right_clicked_item")
        return item and item.data and UsdGeom.Imageable(item.data)
