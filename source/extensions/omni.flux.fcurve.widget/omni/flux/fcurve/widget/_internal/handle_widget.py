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

Draggable handle with dual placers: drag placer (user interaction) + model placer (connections).
Constructor = build: call inside a parent ``with`` context (ZStack inside CanvasFrame).

Visual appearance is inherited from the parent's name-based style via the
``handle_name`` parameter (e.g. ``"FCurveKey"`` or ``"FCurveTangent"``).
Per-curve ``color`` is applied as an inline override on the drag rectangle.

Each instance wraps its widgets in its own ZStack so destroy() can clear() it.
"""

from __future__ import annotations

from collections.abc import Callable

from omni import ui

__all__ = ["HandleWidget"]

_DEFAULT_SIZE = 8
_DEFAULT_PLACER_SIZE = 20
_GHOST_THRESHOLD_SQ = 4.0

_FALLBACK_SELECTED_COLOR = 0xFFFFAA00
_FALLBACK_HOVERED_COLOR = 0xFFCCCCCC


class HandleWidget:
    def __init__(
        self,
        x: float,
        y: float,
        color: int,
        handle_name: str = "FCurveKey",
        handle_size: int = _DEFAULT_SIZE,
        placer_size: float = _DEFAULT_PLACER_SIZE,
        visible: bool = True,
        on_moved: Callable[[HandleWidget], None] | None = None,
        on_released: Callable[[HandleWidget, int], None] | None = None,
        on_pressed: Callable[[HandleWidget, int], None] | None = None,
        on_selection_changed: Callable[[HandleWidget, int], None] | None = None,
    ):
        self._on_moved_cb = on_moved
        self._on_released_cb = on_released
        self._on_pressed_cb = on_pressed
        self._on_selection_changed_cb = on_selection_changed
        self._suppress: bool = False
        self._selected: bool = False
        self._hovered: bool = False
        self.is_dragging: bool = False
        self.raw_px: tuple[float, float] = (x, y)

        self._color = color
        self._handle_name = handle_name
        self._handle_size = handle_size
        self._size_ratio = placer_size / _DEFAULT_PLACER_SIZE
        rect_size = handle_size * self._size_ratio
        half_size = rect_size / 2.0

        self._placer_size = placer_size
        self._rect_size = rect_size

        self._container: ui.ZStack | None = ui.ZStack()
        with self._container:
            self._model_placer: ui.Placer | None = ui.Placer(
                offset_x=x,
                offset_y=y,
                draggable=False,
                stable_size=True,
                visible=visible,
            )
            with self._model_placer:
                with ui.Frame():
                    self._model_rect: ui.Rectangle | None = ui.Rectangle(
                        visible=False,
                        width=0,
                        height=0,
                    )

            with ui.Placer(
                offset_x=-half_size,
                offset_y=-half_size,
                draggable=False,
                stable_size=True,
            ):
                self._drag_placer: ui.Placer | None = ui.Placer(
                    offset_x=x,
                    offset_y=y,
                    draggable=True,
                    stable_size=True,
                    visible=visible,
                    offset_x_changed_fn=self._handle_drag,
                    offset_y_changed_fn=self._handle_drag,
                )
                with self._drag_placer:
                    with ui.Frame():
                        self._drag_rect: ui.Rectangle | None = ui.Rectangle(
                            name=handle_name,
                            width=rect_size,
                            height=rect_size,
                            style={"background_color": color},
                            mouse_pressed_fn=self._handle_press,
                            mouse_released_fn=self._handle_release,
                            mouse_hovered_fn=self._handle_hover,
                        )

            self._ghost_stack: ui.ZStack | None = ui.ZStack()
        self._ghost_line: ui.FreeLine | None = None

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def selected(self) -> bool:
        return self._selected

    @selected.setter
    def selected(self, value: bool) -> None:
        if self._selected != value:
            self._selected = value
            self._apply_style()

    @property
    def position(self) -> tuple[float, float]:
        if self._model_placer:
            return float(self._model_placer.offset_x), float(self._model_placer.offset_y)
        return self.raw_px

    @property
    def screen_center(self) -> tuple[float, float]:
        """Screen-space center of the visible drag handle."""
        r = self._drag_rect
        if r:
            return (
                r.screen_position_x + r.computed_width / 2,
                r.screen_position_y + r.computed_height / 2,
            )
        return (0.0, 0.0)

    @property
    def rect(self) -> ui.Rectangle | None:
        return self._model_rect

    def set_position(self, x: float, y: float) -> None:
        if not self._model_placer or not self._drag_placer:
            return
        self._model_placer.offset_x, self._model_placer.offset_y = x, y
        if not self.is_dragging:
            self._suppress = True
            self.raw_px = (x, y)
            self._drag_placer.offset_x, self._drag_placer.offset_y = x, y
            self._suppress = False
            self._clear_ghost()
        else:
            dx, dy = self.raw_px[0] - x, self.raw_px[1] - y
            if dx * dx + dy * dy > _GHOST_THRESHOLD_SQ:
                self._show_ghost()
            else:
                self._clear_ghost()

    def set_size(self, placer_size: float) -> None:
        self._size_ratio = placer_size / _DEFAULT_PLACER_SIZE
        self._rect_size = self._handle_size * self._size_ratio
        self._placer_size = placer_size
        if self._drag_rect:
            self._drag_rect.width = ui.Pixel(self._rect_size)
            self._drag_rect.height = ui.Pixel(self._rect_size)
            self._apply_style()

    def set_visible(self, v: bool) -> None:
        if self._model_placer:
            self._model_placer.visible = v
        if self._drag_placer:
            self._drag_placer.visible = v

    def destroy(self) -> None:
        self._on_moved_cb = self._on_released_cb = self._on_pressed_cb = self._on_selection_changed_cb = None
        self._ghost_line = None
        self._ghost_stack = None
        if self._container:
            self._container.clear()
        self._model_placer = self._model_rect = None
        self._drag_placer = self._drag_rect = None

    # ── Style (internal) ────────────────────────────────────────────────────

    def _resolve_color(self) -> int:
        """Resolve the current background color based on selection/hover state.

        Reads ``FCurveKeySelected`` / ``FCurveKeyHovered`` from the inherited
        style if the drag rect is available; falls back to the per-curve color.
        """
        if self._selected and self._drag_rect:
            resolved = self._drag_rect.style.get(f"Rectangle::{self._handle_name}Selected", {})
            if "background_color" in resolved:
                return int(resolved["background_color"])
            return _FALLBACK_SELECTED_COLOR
        if self._hovered and self._drag_rect:
            resolved = self._drag_rect.style.get(f"Rectangle::{self._handle_name}Hovered", {})
            if "background_color" in resolved:
                return int(resolved["background_color"])
            return _FALLBACK_HOVERED_COLOR
        return self._color

    def _apply_style(self) -> None:
        if self._drag_rect:
            self._drag_rect.set_style({"background_color": self._resolve_color()})

    # ── Ghost line (internal) ────────────────────────────────────────────────

    def _show_ghost(self) -> None:
        if self._ghost_line or not self._ghost_stack or not self._drag_rect or not self._model_rect:
            return
        with self._ghost_stack:
            self._ghost_line = ui.FreeLine(
                self._drag_rect,
                self._model_rect,
                name="FCurveKeyGhost",
                alignment=ui.Alignment.UNDEFINED,
            )

    def _clear_ghost(self) -> None:
        if self._ghost_line and self._ghost_stack:
            self._ghost_stack.clear()
            self._ghost_line = None

    # ── Events (internal) ───────────────────────────────────────────────────

    def _handle_drag(self, _: ui.Length) -> None:
        if self._suppress or not self._drag_placer:
            return
        self.is_dragging = True
        self.raw_px = (float(self._drag_placer.offset_x), float(self._drag_placer.offset_y))
        if self._on_moved_cb:
            self._on_moved_cb(self)

    def _handle_press(self, _x: float, _y: float, btn: int, mod: int) -> None:
        if btn == 0 and self._on_pressed_cb:
            self._on_pressed_cb(self, mod)

    def _handle_release(self, _x: float, _y: float, btn: int, mod: int) -> None:
        if btn != 0:
            return
        was_dragging = self.is_dragging
        self.is_dragging = False
        self._clear_ghost()
        if self._model_placer and self._drag_placer:
            self._suppress = True
            x, y = float(self._model_placer.offset_x), float(self._model_placer.offset_y)
            self.raw_px = (x, y)
            self._drag_placer.offset_x, self._drag_placer.offset_y = x, y
            self._suppress = False
        if was_dragging:
            if self._on_moved_cb:
                self._on_moved_cb(self)
        else:
            self.selected = not self.selected
            if self._on_selection_changed_cb:
                self._on_selection_changed_cb(self, mod)
        if self._on_released_cb:
            self._on_released_cb(self, mod)

    def _handle_hover(self, hovered: bool) -> None:
        if self._hovered != hovered:
            self._hovered = hovered
            self._apply_style()
