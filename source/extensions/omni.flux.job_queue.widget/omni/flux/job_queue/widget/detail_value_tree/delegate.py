"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

from __future__ import annotations

from collections.abc import Callable

from omni import ui

from ..constants import MONOSPACE_FONT_PATH, PADDING_MEDIUM, ROW_HEIGHT
from .item import DetailValueItem
from .model import DetailValueModel

__all__ = ("DetailValueDelegate",)


class DetailValueDelegate(ui.AbstractItemDelegate):
    """Render a read-only two-column typed-value tree with native disclosure controls."""

    def __init__(self, identifier: str, expansion_changed: Callable[[DetailValueItem, bool], None]) -> None:
        """Initialize stable identifiers and expansion routing.

        Args:
            identifier: Stable prefix used by E2E queries.
            expansion_changed: Callback that updates native expansion and tree height.
        """
        super().__init__()
        self._identifier = identifier
        self._expansion_changed = expansion_changed

    def build_branch(
        self,
        model: DetailValueModel,
        item: DetailValueItem,
        column_id: int,
        level: int,
        expanded: bool,
    ) -> None:
        """Build the native expansion glyph for a container item.

        Args:
            model: Typed-value tree model.
            item: Item represented by the branch.
            column_id: Visible column index.
            level: Zero-based nesting level.
            expanded: Whether nested values are currently visible.
        """
        if column_id != 0:
            return
        with ui.HStack(
            width=ui.Pixel(16 * (level + 1)),
            height=ROW_HEIGHT,
            identifier=f"{self._identifier}_branch_space",
        ):
            ui.Spacer()
            if model.can_item_have_children(item):
                with ui.VStack(
                    width=ui.Pixel(16),
                    height=ROW_HEIGHT,
                    mouse_released_fn=lambda _x, _y, button, _modifiers: self._toggle_expansion(
                        button, item, not expanded
                    ),
                ):
                    ui.Spacer()
                    ui.Image(
                        "",
                        width=ui.Pixel(10),
                        height=ui.Pixel(10),
                        style_type_name_override="TreeView.Item.Minus" if expanded else "TreeView.Item.Plus",
                        identifier=f"{self._identifier}_branch",
                    )
                    ui.Spacer()

    @staticmethod
    def build_header(_column_id: int) -> None:
        """Build no header because the owning section supplies its title.

        Args:
            _column_id: Unused native column index.
        """

    def build_widget(
        self,
        model: DetailValueModel,
        item: DetailValueItem | None,
        column_id: int,
        _level: int,
        _expanded: bool,
    ) -> None:
        """Build one ellipsized monospace key or value cell.

        Args:
            model: Typed-value tree model.
            item: Item represented by the cell.
            column_id: Zero-based key or value column index.
            _level: Unused native nesting level.
            _expanded: Unused native expansion state.
        """
        value_model = model.get_item_value_model(item, column_id)
        if item is None or value_model is None:
            return
        text = value_model.as_string
        with ui.HStack(height=ROW_HEIGHT, spacing=0):
            if column_id == 1:
                ui.Spacer(width=PADDING_MEDIUM)
            if column_id == 0:
                self._build_key(item)
            else:
                ui.Label(
                    text,
                    name="QueueDetailValue",
                    identifier=f"{self._identifier}_value",
                    alignment=ui.Alignment.LEFT_CENTER,
                    height=ROW_HEIGHT,
                    elided_text=True,
                    tooltip=item.value_tooltip,
                    style={"font": MONOSPACE_FONT_PATH},
                )
            if column_id == 0:
                ui.Spacer(width=PADDING_MEDIUM)

    def _build_key(self, item: DetailValueItem) -> None:
        """Build one complete key path with native responsive middle elision.

        Args:
            item: Tree item containing the complete compact key path.
        """
        full_text = item.key_model.as_string
        ui.Label(
            full_text,
            name="QueueDetailKey",
            identifier=f"{self._identifier}_key",
            alignment=ui.Alignment.LEFT_CENTER,
            height=ROW_HEIGHT,
            elided_text=True,
            tooltip=full_text,
            style={"font": MONOSPACE_FONT_PATH},
        )

    def _toggle_expansion(self, button: int, item: DetailValueItem, expanded: bool) -> None:
        """Route primary-button branch clicks to the owning tree.

        Args:
            button: Native mouse button index.
            item: Container item whose visibility changes.
            expanded: Requested expansion state.
        """
        if button == 0:
            self._expansion_changed(item, expanded)
