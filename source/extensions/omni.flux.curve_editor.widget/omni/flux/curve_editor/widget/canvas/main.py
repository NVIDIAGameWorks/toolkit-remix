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

CurveEditorCanvas - Main canvas for hosting FCurveWidget.

This is the primary display area for curve editing. It:
- Hosts FCurveWidget for curve rendering/interaction
- Handles zoom/pan gestures
- Renders grid and value ruler
- Wires FCurveWidget events to storage
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from collections.abc import Callable

import carb.input
import omni.appwindow
import omni.kit.app
from omni import ui
from omni.flux.fcurve.widget import CurveBounds, FCurveWidget, SelectionInfo

from .grid import GridRenderer
from .rulers import TimelineRuler, ValueRuler
from .ticks import compute_nice_interval, format_value
from .viewport import ViewportState

if TYPE_CHECKING:
    from ..model import CurveModel

__all__ = ["CurveEditorCanvas"]


class CurveEditorCanvas:
    """
    Canvas container for FCurveWidget with pan/zoom and grid.

    Responsibilities:
    - Hosts FCurveWidget for curve rendering
    - Handles pan/zoom gestures (mouse wheel, RMB drag)
    - Renders grid
    - Wires FCurveWidget events to CurveModel

    Visual appearance cascades from the parent's name-based style.

    Args:
        model: The curve storage model.
        ruler_size: Ruler width/height in pixels.
        zoom_factor_base: Scroll-wheel zoom factor base.
        grid_time_divisions: Target number of time-axis grid divisions.
        grid_value_divisions: Target number of value-axis grid divisions.
        grid_margin: Grid pixel margin.
        grid_min_viewport_size: Minimum viewport dimension before grid is hidden.
        on_selection_changed: Callback for selection changes (for toolbar updates).
        on_curve_changed: Callback for curve changes (called AFTER model is updated).
    """

    def __init__(
        self,
        model: CurveModel,
        per_curve_bounds: dict[str, CurveBounds] | None = None,
        ruler_size: int = 24,
        zoom_factor_base: float = 1.1,
        grid_time_divisions: int = 15,
        grid_value_divisions: int = 10,
        grid_margin: int = 2,
        grid_min_viewport_size: int = 10,
        on_selection_changed: Callable[[SelectionInfo], None] | None = None,
        on_curve_changed: Callable[[str], None] | None = None,
    ):
        self._model = model
        self._per_curve_bounds = per_curve_bounds or {}
        self._ruler_size = ruler_size
        self._zoom_factor_base = zoom_factor_base
        self._grid_time_divisions = grid_time_divisions
        self._grid_value_divisions = grid_value_divisions
        self._on_selection_changed = on_selection_changed
        self._on_curve_changed_callback = on_curve_changed

        self._viewport = ViewportState()

        self._panning = False
        self._pan_start_x = 0.0
        self._pan_start_y = 0.0

        self._dragging_curve_ids: set[str] = set()

        self._hovered_curve_id: str | None = None
        self._mouse_model_pos: tuple[float, float] | None = None
        self._status_label: ui.Label | None = None
        self._mouse_tracking_sub = None

        self._input_iface = carb.input.acquire_input_interface()
        self._app_mouse = omni.appwindow.get_default_app_window().get_mouse()

        self._curve_changed_sub = None
        self._selection_sub = None
        self._model_sub = None
        self._curve_colors: dict[str, int] = {}

        self._build_ui()

        # Wire events (one-shot setup, no separate method needed)
        self._curve_changed_sub = self._fcurve_widget.subscribe_curve_changed(self._on_curve_changed)
        self._selection_sub = self._fcurve_widget.subscribe_selection_changed(self._on_selection_changed_internal)
        self._model_sub = self._model.subscribe(self._on_model_changed)

        self.reload_from_storage()
        self._on_viewport_changed()

    def _build_ui(self) -> None:
        """Build all visual components into the current omni.ui context."""
        ruler_size = self._ruler_size

        # +----------------------+
        # | [corner] | Timeline  |
        # +----------+-----------+
        # | Value    |  Canvas   |
        # | Ruler    |  Area     |
        # +----------+-----------+
        self._frame = ui.Frame(horizontal_clipping=True, vertical_clipping=True)
        with self._frame:
            with ui.VStack(spacing=0):
                with ui.HStack(height=ui.Pixel(ruler_size), spacing=0):
                    ui.Rectangle(
                        name="CurveEditorCorner",
                        width=ui.Pixel(ruler_size),
                    )
                    self._timeline_ruler = TimelineRuler(
                        viewport=self._viewport,
                        ruler_size=ruler_size,
                        time_divisions=self._grid_time_divisions,
                        value_divisions=self._grid_value_divisions,
                    )

                with ui.HStack(spacing=0):
                    self._value_ruler = ValueRuler(
                        viewport=self._viewport,
                        ruler_size=ruler_size,
                        time_divisions=self._grid_time_divisions,
                        value_divisions=self._grid_value_divisions,
                    )

                    self._canvas_frame = ui.Frame(
                        horizontal_clipping=True,
                        vertical_clipping=True,
                        mouse_pressed_fn=self._handle_mouse_pressed,
                        mouse_released_fn=self._handle_mouse_released,
                        mouse_moved_fn=self._handle_mouse_moved,
                        mouse_wheel_fn=self._handle_mouse_wheel,
                        mouse_hovered_fn=self._on_canvas_hovered,
                        computed_content_size_changed_fn=self._handle_size_changed,
                    )
                    with self._canvas_frame:
                        with ui.ZStack(separate_window=True, content_clipping=True):
                            self._fcurve_widget = FCurveWidget(
                                time_range=(self._viewport.time_min, self._viewport.time_max),
                                value_range=(self._viewport.value_min, self._viewport.value_max),
                                per_curve_bounds=self._per_curve_bounds,
                                on_commit=self._commit_to_storage,
                                on_drag_started=self._on_drag_started,
                                on_drag_ended=self._on_drag_ended,
                                on_hover_changed=self._on_hover_changed,
                            )

                            self._grid_renderer = GridRenderer(
                                viewport=self._viewport,
                                time_divisions=self._grid_time_divisions,
                                value_divisions=self._grid_value_divisions,
                            )

                            self._status_label = ui.Label(
                                "",
                                name="CurveEditorStatus",
                                alignment=ui.Alignment.RIGHT_BOTTOM,
                            )

    @property
    def fcurve_widget(self) -> FCurveWidget | None:
        """Access FCurveWidget for toolbar actions."""
        return self._fcurve_widget

    # ─────────────────────────────────────────────────────────────────────────
    # Pan/Zoom Handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _screen_to_local(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        """Convert screen coordinates to canvas-local coordinates."""
        if self._canvas_frame:
            return (
                screen_x - self._canvas_frame.screen_position_x,
                screen_y - self._canvas_frame.screen_position_y,
            )
        return screen_x, screen_y

    def _read_mouse_local(self) -> tuple[float, float]:
        """Read current mouse position from carb.input as canvas-local coords."""
        mouse_x, mouse_y = self._input_iface.get_mouse_coords_pixel(self._app_mouse)
        dpi_scale = ui.Workspace.get_dpi_scale()
        return self._screen_to_local(mouse_x / dpi_scale, mouse_y / dpi_scale)

    def _handle_mouse_pressed(self, x: float, y: float, button: int, modifier: int) -> None:
        """Handle mouse press - start panning on middle or right button."""
        if button in {1, 2}:
            self._panning = True
            self._pan_start_x = x
            self._pan_start_y = y

    def _handle_mouse_released(self, x: float, y: float, button: int, modifier: int) -> None:
        """Handle mouse release - end panning."""
        if button in {1, 2}:
            self._panning = False

    def _on_canvas_hovered(self, hovered: bool) -> None:
        """Start/stop mouse position tracking when mouse enters/leaves canvas.

        Uses a per-frame poll via carb.input because inner widgets (handles,
        placers) consume mouse events before they reach this frame's
        mouse_moved_fn.
        """
        if hovered:
            if self._mouse_tracking_sub is None:
                self._mouse_tracking_sub = (
                    omni.kit.app.get_app()
                    .get_update_event_stream()
                    .create_subscription_to_pop(self._poll_mouse_position)
                )
        else:
            self._mouse_tracking_sub = None
            self._mouse_model_pos = None
            if self._status_label:
                self._status_label.text = ""

    def _poll_mouse_position(self, _event) -> None:
        """Read mouse position from carb.input each frame while hovered."""
        if not self._canvas_frame:
            return
        local_x, local_y = self._read_mouse_local()
        self._mouse_model_pos = self._viewport.pixel_to_model(local_x, local_y)
        self._update_status_label()

    def _handle_mouse_moved(self, x: float, y: float, modifier: int, pressed: bool) -> None:
        """Handle mouse movement - pan if dragging."""
        if self._panning:
            dx = x - self._pan_start_x
            dy = y - self._pan_start_y

            dt = -dx / self._viewport.time_scale
            dv = dy / self._viewport.value_scale

            self._viewport.pan(dt, dv)
            self._on_viewport_changed()

            self._pan_start_x = x
            self._pan_start_y = y

    def _handle_mouse_wheel(self, scroll_x: float, scroll_y: float, modifier: int) -> None:
        """Handle mouse wheel for zooming.

        No modifier: zoom both axes.
        Shift: zoom X (time) axis only.
        Alt: zoom Y (value) axis only.
        """
        zoom_factor = pow(self._zoom_factor_base, scroll_y)
        center_x, center_y = self._read_mouse_local()

        shift = bool(modifier & carb.input.KEYBOARD_MODIFIER_FLAG_SHIFT)
        alt = bool(modifier & carb.input.KEYBOARD_MODIFIER_FLAG_ALT)

        if shift:
            self._viewport.zoom_x(zoom_factor, center_x)
        elif alt:
            self._viewport.zoom_y(zoom_factor, center_y)
        else:
            self._viewport.zoom(zoom_factor, zoom_factor, center_x, center_y)

        self._on_viewport_changed()

    def _handle_size_changed(self) -> None:
        """Handle canvas size change."""
        if self._canvas_frame:
            width = self._canvas_frame.computed_content_width
            height = self._canvas_frame.computed_content_height
            if width > 0 and height > 0:
                self._viewport.set_size(width, height)
                if self._fcurve_widget:
                    self._fcurve_widget.set_viewport_size(width, height)
                self._on_viewport_changed()

    def _on_viewport_changed(self) -> None:
        """
        Single entry point for all viewport changes.

        Call this whenever the viewport state changes (pan, zoom, resize).
        Updates all dependent components:
        - FCurveWidget time/value ranges
        - Grid lines
        - Timeline ruler
        - Value ruler
        """
        if self._fcurve_widget:
            self._fcurve_widget.time_range = (self._viewport.time_min, self._viewport.time_max)
            self._fcurve_widget.value_range = (self._viewport.value_min, self._viewport.value_max)

        if self._grid_renderer:
            self._grid_renderer.rebuild()
        if self._timeline_ruler:
            self._timeline_ruler.rebuild()
        if self._value_ruler:
            self._value_ruler.rebuild()

    # ─────────────────────────────────────────────────────────────────────────
    # Event Handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _commit_to_storage(self, curve_id: str, curve) -> None:
        """
        Synchronous commit callback for FCurveWidget.

        Called by FCurveWidget BEFORE it fires curve_changed event.
        This ensures storage is always up-to-date when subscribers react.
        """
        self._model.commit_curve(curve_id, curve)

    def _on_curve_changed(self, curve_id: str) -> None:
        """
        FCurveWidget curve_changed event handler.

        Storage is already up-to-date (via on_commit callback).
        Just forward to parent for any additional handling.
        """
        if self._on_curve_changed_callback:
            self._on_curve_changed_callback(curve_id)

    def _on_selection_changed_internal(self, event) -> None:
        """Selection changed -> forward to parent."""
        if self._on_selection_changed and self._fcurve_widget:
            self._on_selection_changed(self._fcurve_widget.selection)

    def _on_hover_changed(self, curve_id: str | None) -> None:
        """FCurveWidget hover changed -> update status label."""
        self._hovered_curve_id = curve_id
        self._update_status_label()

    def _update_status_label(self) -> None:
        """Update the floating status label text."""
        if not self._status_label or self._mouse_model_pos is None:
            return

        time_val, value_val = self._mouse_model_pos

        time_divisions = self._grid_time_divisions
        value_divisions = self._grid_value_divisions
        time_config = compute_nice_interval(self._viewport.time_range, target_divisions=time_divisions)
        value_config = compute_nice_interval(self._viewport.value_range, target_divisions=value_divisions)

        time_str = format_value(time_val, time_config.label_precision + 1)
        value_str = format_value(value_val, value_config.label_precision + 1)

        if self._hovered_curve_id:
            display_name = self._model.get_display_name(self._hovered_curve_id)
            self._status_label.text = f"{display_name}  ({time_str}, {value_str})"
        else:
            self._status_label.text = f"({time_str}, {value_str})"

    def _on_drag_started(self, curve_id: str) -> None:
        """Drag started -> snapshot for undo and suppress reloads."""
        self._dragging_curve_ids.add(curve_id)
        self._model.begin_edit(curve_id)

    def _on_drag_ended(self, curve_id: str) -> None:
        """Drag ended -> finalize undo entry and resume reloads."""
        self._model.end_edit(curve_id)
        self._dragging_curve_ids.discard(curve_id)

    def _on_model_changed(self, curve_id: str) -> None:
        """Storage changed (undo, external) -> reload FCurveWidget."""
        if curve_id in self._dragging_curve_ids:
            return
        self.reload_from_storage()

    # ─────────────────────────────────────────────────────────────────────────
    # Data Loading
    # ─────────────────────────────────────────────────────────────────────────

    def set_curve_colors(self, colors: dict[str, int]) -> None:
        """Set display colors for curves (curve_id -> 0xAABBGGRR)."""
        self._curve_colors = dict(colors)

    def reload_from_storage(self) -> None:
        """Load curves from storage into FCurveWidget."""
        if not self._fcurve_widget:
            return

        curves = {}
        for curve_id in self._model.get_curve_ids():
            curve = self._model.get_curve(curve_id)
            if curve:
                if curve_id in self._curve_colors:
                    curve.color = self._curve_colors[curve_id]
                curves[curve_id] = curve

        self._fcurve_widget.set_curves(curves)

    # ─────────────────────────────────────────────────────────────────────────
    # Viewport Control
    # ─────────────────────────────────────────────────────────────────────────

    def set_time_range(self, time_min: float, time_max: float) -> None:
        """
        Set the X-axis (time) range.

        Call this to sync with external timeline.
        """
        self._viewport.set_time_range(time_min, time_max)
        self._on_viewport_changed()

    def set_value_range(self, value_min: float, value_max: float) -> None:
        """Set the Y-axis (value) range."""
        self._viewport.set_value_range(value_min, value_max)
        self._on_viewport_changed()

    def fit_to_data(self) -> None:
        """Adjust viewport to fit all visible curve data."""
        if not self._fcurve_widget:
            return
        self._fcurve_widget.fit_to_data()
        t_min, t_max = self._fcurve_widget.time_range
        v_min, v_max = self._fcurve_widget.value_range
        self._viewport.set_time_range(t_min, t_max)
        self._viewport.set_value_range(v_min, v_max)
        self._on_viewport_changed()
