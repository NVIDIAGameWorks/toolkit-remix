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

CurveListPanel - Pure CDM-based curve list panel.

This panel displays curves from a CurveModel with NO USD dependencies.
All display names come from model.get_display_name().

Visual appearance cascades from the parent's name-based style via widget
name ``CurveEditorListEmpty``.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

import omni.ui as ui

from ..model import CurveModel

__all__ = ["CurveListPanel"]

_ITEM_HEIGHT = 24
_ITEM_SPACING = 2
_CHECKBOX_WIDTH = 20
_MARGIN_LEFT = 4
_LIST_SPACING = 2


@dataclass
class _CurveItemData:
    """Data for a curve item in the list."""

    curve_id: str
    display_name: str
    visible: bool = True
    selected: bool = False


class CurveListPanel(ui.Frame):
    """
    Pure CDM-based curve list panel.

    Displays curves from a CurveModel with NO USD dependencies.
    All display names come from model.get_display_name().

    Usage:
        panel = CurveListPanel()
        panel.populate(my_curve_model)
        panel.on_selection_changed = my_callback
        panel.on_visibility_changed = my_visibility_callback
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._curves: list[_CurveItemData] = []
        self._item_frames: dict[str, ui.Frame] = {}

        self.on_selection_changed: Callable[[list[str]], None] | None = None
        self.on_visibility_changed: Callable[[str, bool], None] | None = None

        self._scroll_frame: ui.ScrollingFrame | None = None
        self._list_container: ui.VStack | None = None
        self._empty_label: ui.Label | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        with self:
            with ui.ZStack():
                with ui.VStack():
                    ui.Spacer()
                    self._empty_label = ui.Label(
                        "No curves",
                        name="CurveEditorListEmpty",
                        alignment=ui.Alignment.CENTER,
                    )
                    ui.Spacer()

                self._scroll_frame = ui.ScrollingFrame(
                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                )
                with self._scroll_frame:
                    self._list_container = ui.VStack(spacing=_LIST_SPACING)

        self._update_empty_state()

    def _update_empty_state(self) -> None:
        has_curves = len(self._curves) > 0
        if self._empty_label:
            self._empty_label.visible = not has_curves
        if self._scroll_frame:
            self._scroll_frame.visible = has_curves

    def _rebuild_list(self) -> None:
        if not self._list_container:
            return

        self._list_container.clear()
        self._item_frames.clear()

        with self._list_container:
            for curve_data in self._curves:
                self._build_curve_item(curve_data)

        self._update_empty_state()

    def _build_curve_item(self, curve_data: _CurveItemData) -> None:
        frame = ui.Frame(height=ui.Pixel(_ITEM_HEIGHT))
        self._item_frames[curve_data.curve_id] = frame

        with frame:
            with ui.HStack(spacing=_ITEM_SPACING):
                checkbox = ui.CheckBox(width=ui.Pixel(_CHECKBOX_WIDTH))
                checkbox.model.set_value(curve_data.visible)
                checkbox.model.add_value_changed_fn(partial(self._on_item_visibility_changed, curve_data.curve_id))

                label_frame = ui.Frame()
                with label_frame:
                    ui.Label(
                        curve_data.display_name,
                        width=ui.Fraction(1),
                        style={"margin_left": _MARGIN_LEFT},
                    )
                label_frame.set_mouse_pressed_fn(partial(self._on_item_clicked, curve_data.curve_id))

    def _on_item_visibility_changed(self, curve_id: str, model: ui.AbstractValueModel) -> None:
        visible = model.get_value_as_bool()
        for c in self._curves:
            if c.curve_id == curve_id:
                c.visible = visible
                break
        if self.on_visibility_changed:
            self.on_visibility_changed(curve_id, visible)

    def _on_item_clicked(self, curve_id: str, _x: float, _y: float, btn: int, _mod):
        if btn == 0:
            self._select_curve(curve_id)

    def _select_curve(self, curve_id: str):
        for c in self._curves:
            c.selected = c.curve_id == curve_id

        if self.on_selection_changed:
            self.on_selection_changed([curve_id])

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def populate(self, model: CurveModel):
        """
        Populate the panel from a CurveModel.

        Args:
            model: The CurveModel to display curves from.
        """
        self._curves.clear()

        if model is not None:
            curve_ids = model.get_curve_ids()
            for curve_id in curve_ids:
                display_name = model.get_display_name(curve_id)
                self._curves.append(_CurveItemData(curve_id, display_name))

        self._rebuild_list()

    def get_visible_curve_ids(self) -> list[str]:
        """Get list of visible curve IDs."""
        return [c.curve_id for c in self._curves if c.visible]
