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

from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager, ExitStack, contextmanager, nullcontext
from enum import Enum

import carb.input
import omni.appwindow
import omni.kit.app
from omni import ui
from omni.flux.fcurve.widget import CurveBounds, FCurve, FCurveWidget, SelectionInfo
from omni.flux.utils.widget import GroupedKeysModel

from .grid import GridRenderer
from .rulers import TimelineRuler, ValueRuler
from .ticks import compute_nice_interval, format_value
from .viewport import ViewportState
from ..payload import curve_to_payload, payload_to_curve

__all__ = ["CurveEditorCanvas", "FrameType"]


class FrameType(Enum):
    """Axes to frame around visible curve keys."""

    ALL = "all"
    TIME = "time"
    VALUE = "value"


class CurveEditorCanvas:
    """
    Canvas container for FCurveWidget with pan/zoom and grid.

    Responsibilities:
    - Hosts FCurveWidget for curve rendering
    - Handles pan/zoom gestures (mouse wheel, RMB drag)
    - Renders grid
    - Wires FCurveWidget events to GroupedKeysModel

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
        on_model_changed: Optional owner of external storage reloads.
        edit_context_factory: Create a context grouping completed drag edits.
    """

    _FRAME_PADDING_RATIO = 0.1
    _FRAME_ZERO_SPAN_PADDING = 0.1

    def __init__(
        self,
        model: GroupedKeysModel,
        per_curve_bounds: dict[str, CurveBounds] | None = None,
        ruler_size: int = 24,
        zoom_factor_base: float = 1.1,
        grid_time_divisions: int = 15,
        grid_value_divisions: int = 10,
        grid_margin: int = 2,
        grid_min_viewport_size: int = 10,
        on_selection_changed: Callable[[SelectionInfo], None] | None = None,
        on_curve_changed: Callable[[str], None] | None = None,
        on_model_changed: Callable[[str], None] | None = None,
        edit_context_factory: Callable[[], AbstractContextManager] = nullcontext,
    ) -> None:
        """Create the curve editor canvas.

        Args:
            model: Grouped-key model used to read/write curve payloads.
            per_curve_bounds: Optional per-curve viewport bounds.
            ruler_size: Ruler width/height in pixels.
            zoom_factor_base: Scroll-wheel zoom factor base.
            grid_time_divisions: Target number of time-axis grid divisions.
            grid_value_divisions: Target number of value-axis grid divisions.
            grid_margin: Grid pixel margin.
            grid_min_viewport_size: Minimum viewport dimension before grid is hidden.
            on_selection_changed: Optional callback for selection changes.
            on_curve_changed: Optional callback after a curve payload is committed.
            on_model_changed: Optional callback owning external storage reloads.
            edit_context_factory: Create a context grouping completed drag edits.
        """
        self._model = model
        self._per_curve_bounds = per_curve_bounds or {}
        self._ruler_size = ruler_size
        self._zoom_factor_base = zoom_factor_base
        self._grid_time_divisions = grid_time_divisions
        self._grid_value_divisions = grid_value_divisions
        self._on_selection_changed = on_selection_changed
        self._on_curve_changed_callback = on_curve_changed
        self._on_model_changed_callback = on_model_changed
        self._edit_context_factory = edit_context_factory

        self._viewport = ViewportState()

        self._panning = False
        self._pan_start_x = 0.0
        self._pan_start_y = 0.0

        self._dragging_curve_ids: set[str] = set()
        self._drag_has_changes = False

        self._hovered_curve_id: str | None = None
        self._mouse_model_pos: tuple[float, float] | None = None
        self._status_label: ui.Label | None = None
        self._mouse_tracking_sub = None
        self._mouse_over_canvas = False

        self._input_iface = carb.input.acquire_input_interface()
        self._app_window = omni.appwindow.get_default_app_window()
        self._app_mouse = self._app_window.get_mouse()

        self._curve_changed_sub = None
        self._selection_sub = None
        self._model_sub = None
        self._curve_colors: dict[str, int] = {}
        self._selected_curve_ids: set[str] | None = None

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
                        identifier="CurveEditorCanvas",
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
                        with ui.ZStack(separate_window=True, content_clipping=True, send_mouse_events_to_back=True):
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
                            # Keep this last so curve and handle presses claim their gesture before deselection.
                            ui.Spacer(
                                identifier="CurveEditorCanvasBackground",
                                mouse_pressed_fn=self._handle_background_mouse_pressed,
                            )

    @property
    def fcurve_widget(self) -> FCurveWidget | None:
        """Access FCurveWidget for toolbar actions."""
        return self._fcurve_widget

    @property
    def is_dragging(self) -> bool:
        """Whether a curve edit gesture is active."""
        return bool(self._dragging_curve_ids)

    @contextmanager
    def edit_curves(self, curve_ids: Iterable[str]) -> Iterator[None]:
        """Bracket each distinct curve edit and finalize every successful start."""
        with ExitStack() as edits:
            for curve_id in dict.fromkeys(curve_ids):
                self._model.begin_edit(curve_id)
                edits.callback(self._model.end_edit, curve_id)
            yield

    def destroy(self) -> None:
        """Release subscriptions and canvas widgets after the owner finishes its edits."""
        self._mouse_tracking_sub = None
        self._curve_changed_sub = None
        self._selection_sub = None
        self._model_sub = None
        self._on_selection_changed = None
        self._on_curve_changed_callback = None
        self._on_model_changed_callback = None
        with ExitStack() as cleanup:
            for child in (self._frame, self._fcurve_widget):
                if child:
                    cleanup.callback(child.destroy)
            cleanup.callback(self._finish_drag_edits)
            self._fcurve_widget = None
            self._frame = None
            self._canvas_frame = None
            self._status_label = None
            self._grid_renderer = None
            self._timeline_ruler = None
            self._value_ruler = None

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

    def _handle_background_mouse_pressed(self, _x: float, _y: float, button: int, modifier: int) -> None:
        """Clear selection after interactive children have claimed their gestures."""
        modifiers = (
            carb.input.KEYBOARD_MODIFIER_FLAG_SHIFT
            | carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL
            | carb.input.KEYBOARD_MODIFIER_FLAG_ALT
            | carb.input.KEYBOARD_MODIFIER_FLAG_SUPER
        )
        if button == 0 and not modifier & modifiers and not self.is_dragging and not self._panning:
            self._fcurve_widget.clear_selection()

    def _handle_mouse_released(self, x: float, y: float, button: int, modifier: int) -> None:
        """Handle mouse release - end panning."""
        if button in {1, 2}:
            self._panning = False

    def _on_canvas_hovered(self, hovered: bool) -> None:
        """Track hover without interrupting a held insertion outside the canvas.

        Uses a per-frame poll via carb.input because inner widgets (handles,
        placers) consume mouse events before they reach this frame's
        mouse_moved_fn.
        """
        self._mouse_over_canvas = hovered
        if hovered:
            if self._mouse_tracking_sub is None:
                self._mouse_tracking_sub = (
                    omni.kit.app.get_app()
                    .get_update_event_stream()
                    .create_subscription_to_pop(self._poll_mouse_position)
                )
        else:
            if not self._fcurve_widget or not self._fcurve_widget.is_inserting_key:
                self._mouse_tracking_sub = None
            self._mouse_model_pos = None
            if self._status_label:
                self._status_label.text = ""

    def _poll_mouse_position(self, _event) -> None:
        """Track hover and finish held insertions on release or focus loss."""
        if not self._canvas_frame:
            return
        local_x, local_y = self._read_mouse_local()
        if self._fcurve_widget and self._fcurve_widget.is_inserting_key:
            focus_lost = self._app_window.get_window() is not None and not self._app_window.is_focused()
            if not focus_lost:
                self._fcurve_widget.update_insertion((local_x, local_y))
            else:
                carb.log_info("Key insertion finished at its last position because the application lost focus.")
            if focus_lost or not self._input_iface.get_mouse_value(self._app_mouse, carb.input.MouseInput.LEFT_BUTTON):
                self._fcurve_widget.update_insertion(None)
        if self._mouse_over_canvas:
            self._mouse_model_pos = self._viewport.pixel_to_model(local_x, local_y)
            self._update_status_label()
        elif not self._fcurve_widget or not self._fcurve_widget.is_inserting_key:
            self._mouse_tracking_sub = None

    def _handle_mouse_moved(self, x: float, y: float, modifier: int, pressed: bool = False) -> None:
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

    def _commit_to_storage(self, curve_id: str, curve: FCurve) -> None:
        """
        Synchronous commit callback for FCurveWidget.

        Called by FCurveWidget BEFORE it fires curve_changed event.
        This ensures storage is always up-to-date when subscribers react.

        Args:
            curve_id: Curve id being committed.
            curve: FCurve-like object supplied by ``FCurveWidget``.
        """
        if curve_id in self._dragging_curve_ids:
            self._drag_has_changes = True
        self._model.commit_payload(curve_id, curve_to_payload(curve))

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
        self._on_canvas_hovered(True)

    def _on_drag_ended(self, curve_id: str) -> None:
        """Finalize all participating curves together when the drag ends."""
        if curve_id not in self._dragging_curve_ids:
            return
        self._finish_drag_edits()

    def _finish_drag_edits(self) -> None:
        """Close every model edit in one undo action without holding a group across frames."""
        dragging, self._dragging_curve_ids = self._dragging_curve_ids, set()
        has_changes, self._drag_has_changes = self._drag_has_changes, False
        if not dragging:
            return
        with ExitStack() as edits:
            for curve_id in sorted(dragging):
                edits.callback(self._model.end_edit, curve_id)
            # Even an empty Kit undo group clears Redo; one curve already creates one command.
            with self._edit_context_factory() if len(dragging) > 1 and has_changes else nullcontext():
                edits.close()

    def _on_model_changed(self, curve_id: str) -> None:
        """Forward external storage changes or reload a standalone canvas."""
        if curve_id in self._dragging_curve_ids:
            return
        if self._on_model_changed_callback:
            self._on_model_changed_callback(curve_id)
        else:
            self.reload_from_storage()

    # ─────────────────────────────────────────────────────────────────────────
    # Data Loading
    # ─────────────────────────────────────────────────────────────────────────

    def set_curve_colors(self, colors: dict[str, int]) -> None:
        """Set display colors for curves (curve_id -> 0xAABBGGRR)."""
        self._curve_colors = dict(colors)

    def set_selected_curve_ids(self, curve_ids: set[str] | None) -> None:
        """Filter displayed curves and retain key selection on remaining curves.

        Args:
            curve_ids: Curve ids to display, or ``None`` to display all curves.
        """
        self._selected_curve_ids = None if curve_ids is None else set(curve_ids)
        if not self._fcurve_widget:
            return

        selected_keys = list(self._fcurve_widget.selection.keys)
        self.reload_from_storage()
        loaded_curves = self._fcurve_widget.curves
        self._fcurve_widget.select_keys(
            [
                ref
                for ref in selected_keys
                if ref.curve_id in loaded_curves and 0 <= ref.key_index < len(loaded_curves[ref.curve_id].keys)
            ]
        )

    def reload_from_storage(self) -> None:
        """Load curves from storage into FCurveWidget."""
        if not self._fcurve_widget:
            return

        curves = {}
        for curve_id in self._model.group_ids:
            if self._selected_curve_ids is not None and curve_id not in self._selected_curve_ids:
                continue
            curve = payload_to_curve(curve_id, self._model.get_payload(curve_id))
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

    def fit_to_data(self, frame_type: FrameType = FrameType.ALL) -> None:
        """Frame visible-key bounds and synchronize the curves, grid, and rulers.

        Pad requested axes by 10% of their span on each side, or 0.1 for a zero
        span. Preserve unrequested ranges and leave the viewport unchanged when
        no visible keys are loaded.

        Args:
            frame_type: Axes to fit; defaults to both time and value.
        """
        if not self._fcurve_widget:
            return
        times, values = [], []
        for curve in self._fcurve_widget.curves.values():
            if not curve.visible:
                continue
            for key in curve.keys:
                times.append(key.time)
                values.append(key.value)
        if not times:
            return
        time_padding = (max(times) - min(times)) * self._FRAME_PADDING_RATIO or self._FRAME_ZERO_SPAN_PADDING
        value_padding = (max(values) - min(values)) * self._FRAME_PADDING_RATIO or self._FRAME_ZERO_SPAN_PADDING
        if frame_type in (FrameType.ALL, FrameType.TIME):
            self._viewport.set_time_range(min(times) - time_padding, max(times) + time_padding)
        if frame_type in (FrameType.ALL, FrameType.VALUE):
            self._viewport.set_value_range(min(values) - value_padding, max(values) + value_padding)
        self._on_viewport_changed()
