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

import asyncio
from collections.abc import Callable
from typing import Any

import omni.kit.app
import omni.ui as ui

__all__ = ["SectionedComboBox", "SectionedComboItem"]


class SectionedComboItem:
    """A single item in a SectionedComboBox.

    Args:
        label: Display text for the item.
        section: Section/group name. Items with the same section are grouped
            under a shared header in the dropdown.
        data: Arbitrary payload returned to the selection callback.
    """

    def __init__(self, label: str, section: str = "", data: Any = None):
        self.label = label
        self.section = section
        self.data = data


class _DisplayModel(ui.AbstractItemModel):
    """Minimal model that shows a single selected label in the ComboBox trigger."""

    def __init__(self):
        super().__init__()
        self._display_item = _DisplayItem("")
        self._index = ui.SimpleIntModel(0)

    def set_text(self, text: str) -> None:
        self._display_item.model.as_string = text
        self._item_changed(None)

    def get_item_children(self, item=None):
        return [self._display_item]

    def get_item_value_model(self, item=None, column_id=-1):
        if item is None:
            return self._index
        return item.model

    def get_item_value_model_count(self, item=None):
        return 1


class _DisplayItem(ui.AbstractItem):
    def __init__(self, text: str):
        super().__init__()
        self.model = ui.SimpleStringModel(text)


class SectionedComboBox(ui.ComboBox):
    """A ComboBox that displays items in a sectioned popup.

    Uses ``ui.ComboBox`` for the trigger. Clicking opens a popup window positioned
    directly below the trigger, matching its width, with items grouped by section.

    Args:
        items: The list of items to display.
        selected_index: The index of the initially selected item.
        on_selection_changed_fn: Callback receiving ``(index, item)`` when the selection changes.
        **kwargs: Forwarded to ``ui.ComboBox`` (e.g. ``width``, ``tooltip``, ``enabled``).
    """

    _ITEM_HEIGHT = ui.Pixel(22)
    _SECTION_HEADER_HEIGHT = ui.Pixel(28)
    _ITEM_PADDING = ui.Pixel(6)

    _POPUP_FLAGS: int = (
        ui.WINDOW_FLAGS_POPUP
        | ui.WINDOW_FLAGS_NO_TITLE_BAR
        | ui.WINDOW_FLAGS_NO_RESIZE
        | ui.WINDOW_FLAGS_NO_MOVE
        | ui.WINDOW_FLAGS_NO_SCROLLBAR
    )

    def __init__(
        self,
        items: list[SectionedComboItem] | None = None,
        selected_index: int = 0,
        on_selection_changed_fn: Callable[[int, SectionedComboItem], None] | None = None,
        **kwargs,
    ):
        self._items: list[SectionedComboItem] = list(items) if items else []
        self._selected_index: int = self._clamp_selected_index(selected_index)
        self._on_selection_changed_fn = on_selection_changed_fn
        self._popup_window: ui.Window | None = None

        self._display_model = _DisplayModel()
        super().__init__(self._display_model, **kwargs)

        self.set_mouse_pressed_fn(self._on_clicked)
        self._update_display()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def selected_index(self) -> int:
        return self._selected_index

    @selected_index.setter
    def selected_index(self, value: int) -> None:
        if not self._items:
            return
        self._selected_index = self._clamp_selected_index(value)
        self._update_display()

    @property
    def selected_item(self) -> SectionedComboItem | None:
        if not self._items or self._selected_index >= len(self._items):
            return None
        return self._items[self._selected_index]

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def set_items(self, items: list[SectionedComboItem], selected_index: int = 0) -> None:
        """Replace all items and update the display."""
        self._items = list(items) if items else []
        self._selected_index = self._clamp_selected_index(selected_index)
        self._close_popup()
        self._update_display()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _update_display(self) -> None:
        item = self.selected_item
        self._display_model.set_text(item.label if item else "")

    def _clamp_selected_index(self, value: int) -> int:
        if not self._items:
            return 0
        return max(0, min(value, len(self._items) - 1))

    def _on_clicked(self, x: float, y: float, button: int, modifier: int) -> None:
        if button != 0 or not self.enabled:
            return
        self._show_popup()

    def _show_popup(self) -> None:
        self._close_popup()
        if not self._items:
            return

        trigger_x = self.screen_position_x
        trigger_y = self.screen_position_y
        trigger_width = self.computed_width
        trigger_height = self.computed_height

        popup_height = self._calculate_popup_height()

        self._popup_window = ui.Window(
            "SectionedComboPopup",
            name="SectionedComboPopup",
            width=trigger_width,
            height=popup_height,
            flags=self._POPUP_FLAGS,
            padding_x=0,
            padding_y=0,
            margin=0,
            position_x=trigger_x,
            position_y=trigger_y + trigger_height,
        )

        with self._popup_window.frame:
            with ui.VStack(spacing=0):
                show_sections = self._has_multiple_sections()
                current_section = None
                for index, item in enumerate(self._items):
                    if show_sections and item.section and item.section != current_section:
                        self._build_section_header(item.section)
                        current_section = item.section
                    self._build_item_row(index, item)

    def _build_section_header(self, title: str) -> None:
        """Build a non-interactive section header label, vertically centered."""
        with ui.ZStack(height=self._SECTION_HEADER_HEIGHT):
            ui.Rectangle(name="SectionedComboSectionHeader")
            with ui.HStack():
                ui.Spacer(width=self._ITEM_PADDING)
                ui.Label(title, name="SectionedComboHeader", alignment=ui.Alignment.LEFT_CENTER)

    def _build_item_row(self, index: int, item: SectionedComboItem) -> None:
        """Build a selectable item row."""
        is_selected = index == self._selected_index

        with ui.ZStack(
            height=self._ITEM_HEIGHT,
            mouse_pressed_fn=lambda x, y, button, modifier, idx=index: self._on_item_clicked(idx, button),
        ):
            ui.Rectangle(
                name="SectionedComboItem",
                selected=is_selected,
            )
            with ui.HStack():
                ui.Spacer(width=self._ITEM_PADDING)
                ui.Label(item.label, name="SectionedComboItemLabel")
                ui.Spacer(width=self._ITEM_PADDING)

    def _has_multiple_sections(self) -> bool:
        """Return True if items span more than one unique section."""
        sections = {item.section for item in self._items if item.section}
        return len(sections) > 1

    def _calculate_popup_height(self) -> float:
        """Calculate the popup height based on items and section headers."""
        height = 0.0
        show_sections = self._has_multiple_sections()
        current_section = None
        for item in self._items:
            if show_sections and item.section and item.section != current_section:
                height += self._SECTION_HEADER_HEIGHT.value
                current_section = item.section
            height += self._ITEM_HEIGHT.value
        return height

    def _on_item_clicked(self, index: int, button: int) -> None:
        if button != 0:
            return
        previous = self._selected_index
        self._selected_index = index
        self._update_display()
        # Defer popup close to avoid destroying widgets during the click event
        asyncio.ensure_future(self._close_popup_deferred())
        if self._on_selection_changed_fn is not None and index != previous:
            self._on_selection_changed_fn(index, self._items[index])

    async def _close_popup_deferred(self) -> None:
        """Close popup on the next frame to avoid destroy-during-event errors."""
        await omni.kit.app.get_app().next_update_async()
        self._close_popup()

    def _close_popup(self) -> None:
        if self._popup_window is not None:
            self._popup_window.visible = False
            self._popup_window = None

    def destroy(self) -> None:
        self._close_popup()
        self._items = []
        self._on_selection_changed_fn = None
        self._display_model = None
        super().destroy()
