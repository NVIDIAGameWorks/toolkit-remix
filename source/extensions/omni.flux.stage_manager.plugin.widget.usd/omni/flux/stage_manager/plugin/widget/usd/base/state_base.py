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

__all__ = ["StageManagerStateWidgetPlugin"]

import abc
from collections.abc import Callable
from typing import TYPE_CHECKING

from omni import ui
from pydantic import Field

from .usd_base import StageManagerUSDWidgetPlugin as _StageManagerUSDWidgetPlugin

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel


class StageManagerStateWidgetPlugin(_StageManagerUSDWidgetPlugin, abc.ABC):
    display_name: str = Field(default="", exclude=True)
    tooltip: str = Field(default="", exclude=True)  # The tooltip will be dynamically built on the state icon

    @property
    def _icon_size(self) -> ui.Length:
        return ui.Pixel(20)

    def make_action_image(
        self,
        *,
        model: "_StageManagerTreeModel",
        item: "_StageManagerTreeItem",
        name: str,
        tooltip: str,
        mouse_released_fn: Callable[[float, float, int, int], None] | None = None,
        enabled: bool = True,
        identifier: str = "",
        height: ui.Length | None = None,
    ) -> ui.Image:
        """Create an action image with shared row-selection gesture handling.

        An enabled image with a release callback owns mouse events and forwards every press through the existing row
        interaction. Left and right presses validate the row selection, and the tree delegate opens its context menu
        for right presses. Other buttons are forwarded without selection validation. The release callback is forwarded
        unchanged.

        Args:
            model: Stage Manager model used for press-time selection validation.
            item: Tree item associated with the action image's row.
            name: Image style name.
            tooltip: Tooltip shown for the image.
            mouse_released_fn: Optional callback forwarded to the image unchanged.
            enabled: Whether the image can own and execute its action.
            identifier: Optional stable identifier for UI automation.
            height: Optional image height; defaults to the standard icon size.

        Returns:
            The constructed action image.
        """
        actionable = bool(enabled) and mouse_released_fn is not None
        return ui.Image(
            "",
            width=self._icon_size,
            height=self._icon_size if height is None else height,
            name=name,
            tooltip=tooltip,
            enabled=bool(enabled),
            identifier=identifier,
            opaque_for_mouse_events=actionable,
            mouse_pressed_fn=(
                (lambda _x, _y, button, _modifiers: self._item_clicked(button, button in (0, 1), model, item))
                if actionable
                else None
            ),
            mouse_released_fn=mouse_released_fn,
        )

    @abc.abstractmethod
    def build_icon_ui(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool):
        pass

    def build_ui(self, model: "_StageManagerTreeModel", item: "_StageManagerTreeItem", level: int, expanded: bool):
        with ui.VStack(width=0):
            ui.Spacer(width=0)
            self.build_icon_ui(model, item, level, expanded)
            ui.Spacer(width=0)
