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

CurveEditorWidget - Main public API for the curve editor.

This is the primary entry point for embedding a curve editor in other UIs.
It combines:
- CurveEditorCanvas: Hosts FCurveWidget with grid, rulers, and pan/zoom
- CurveEditorToolbar: Action buttons for tangent types, key ops, view controls

All curve rendering and interaction is delegated to FCurveWidget.
Storage is handled via CurveModel.
"""

from __future__ import annotations

from collections.abc import Callable

from omni import ui
from omni.flux.fcurve.widget import CurveBounds, FCurve, FCurveWidget, SelectionInfo, TangentType

from .canvas import CurveEditorCanvas
from .layout import CurveEditorLayout
from .model import CurveModel
from .panels import CurveTreePanel
from .style import build_default_style
from .toolbar import CurveEditorToolbar

__all__ = ["CurveEditorWidget"]


class CurveEditorWidget:
    """
    General-purpose curve editor widget.

    This is the main entry point for embedding a curve editor. It combines:
    - CurveEditorCanvas: FCurveWidget with grid, rulers, pan/zoom
    - CurveEditorToolbar: Tangent types, key operations, view controls

    Follows the omni.ui "constructor = build" pattern.  Visual appearance is
    controlled via omni.ui name-based style selectors (see ``build_default_style``).
    Override by wrapping in a parent frame::

        with ui.Frame(style={"Rectangle::CurveEditorGrid": {"background_color": 0xFF0000FF}}):
            widget = CurveEditorWidget(model=model)

    Args:
        model: Storage backend for curve data.
        time_range: Initial X-axis range (time_min, time_max).
        value_range: Initial Y-axis range (value_min, value_max).
        show_toolbar: Whether to show the toolbar.
        toolbar_height: Toolbar height in pixels.
        ruler_size: Ruler width/height in pixels.
        zoom_factor_base: Scroll-wheel zoom factor base.
        grid_time_divisions: Target number of time-axis grid divisions.
        grid_value_divisions: Target number of value-axis grid divisions.
        grid_margin: Grid pixel margin.
        grid_min_viewport_size: Minimum viewport dimension before grid is hidden.
        on_change: Optional callback when curves are modified.
    """

    def __init__(
        self,
        model: CurveModel,
        layout: CurveEditorLayout | None = None,
        time_range: tuple[float, float] = (0.0, 1.0),
        value_range: tuple[float, float] = (0.0, 1.0),
        per_curve_bounds: dict[str, CurveBounds] | None = None,
        show_toolbar: bool = True,
        toolbar_height: int = 58,
        curve_panel_width: int = 200,
        ruler_size: int = 24,
        zoom_factor_base: float = 1.1,
        grid_time_divisions: int = 15,
        grid_value_divisions: int = 10,
        grid_margin: int = 2,
        grid_min_viewport_size: int = 10,
        on_change: Callable[[], None] | None = None,
        on_create_curve: Callable[[str], None] | None = None,
        on_delete_curve: Callable[[str], None] | None = None,
    ):
        self._model = model
        self._layout = layout
        self._time_range = time_range
        self._value_range = value_range
        self._per_curve_bounds = per_curve_bounds or {}
        self._show_toolbar = show_toolbar
        self._toolbar_height = toolbar_height
        self._curve_panel_width = curve_panel_width
        self._ruler_size = ruler_size
        self._zoom_factor_base = zoom_factor_base
        self._grid_time_divisions = grid_time_divisions
        self._grid_value_divisions = grid_value_divisions
        self._grid_margin = grid_margin
        self._grid_min_viewport_size = grid_min_viewport_size
        self._on_change = on_change
        self._on_create_curve = on_create_curve
        self._on_delete_curve = on_delete_curve

        self._frame: ui.Frame | None = None
        self._canvas: CurveEditorCanvas | None = None
        self._toolbar: CurveEditorToolbar | None = None
        self._toolbar_frame: ui.Frame | None = None
        self._curve_tree: CurveTreePanel | None = None

        self._selection_sub = None
        self._model_sub = None

        self._build_ui()

    @property
    def fcurve_widget(self) -> FCurveWidget | None:
        """
        Access the underlying FCurveWidget.

        Use this for direct manipulation when needed.
        """
        if self._canvas:
            return self._canvas.fcurve_widget
        return None

    @property
    def selection(self) -> SelectionInfo | None:
        """Get current selection state."""
        if self.fcurve_widget:
            return self.fcurve_widget.selection
        return None

    @property
    def model(self) -> CurveModel:
        """Access the curve storage model."""
        return self._model

    # ─────────────────────────────────────────────────────────────────────────
    # Build UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Build the curve editor UI into the current omni.ui context."""
        self._frame = ui.Frame(style=build_default_style())

        with self._frame:
            with ui.ZStack():
                ui.Rectangle(name="CurveEditorMainBg")
                with ui.VStack(spacing=0):
                    if self._show_toolbar:
                        with ui.ZStack(height=ui.Pixel(self._toolbar_height)):
                            ui.Rectangle(name="CurveEditorToolbarBg")
                            self._toolbar_frame = ui.Frame()

                    with ui.HStack(spacing=0):
                        if self._layout:
                            with ui.ZStack(width=ui.Pixel(self._curve_panel_width)):
                                ui.Rectangle(name="CurveEditorTreePanelBg")
                                with ui.Frame():
                                    self._curve_tree = CurveTreePanel(
                                        layout=self._layout,
                                        curve_model=self._model,
                                        on_visibility_changed=self._on_curve_visibility_changed,
                                        on_create_curve=self._handle_create_curve,
                                        on_delete_curve=self._handle_delete_curve,
                                    )

                        with ui.Frame():
                            self._canvas = CurveEditorCanvas(
                                model=self._model,
                                per_curve_bounds=self._per_curve_bounds,
                                ruler_size=self._ruler_size,
                                zoom_factor_base=self._zoom_factor_base,
                                grid_time_divisions=self._grid_time_divisions,
                                grid_value_divisions=self._grid_value_divisions,
                                grid_margin=self._grid_margin,
                                grid_min_viewport_size=self._grid_min_viewport_size,
                                on_selection_changed=self._on_selection_changed,
                                on_curve_changed=self._on_curve_changed,
                            )

        if self._layout:
            self._canvas.set_curve_colors(self._extract_curve_colors(self._layout))
            self._canvas.reload_from_storage()
        self._canvas.set_time_range(*self._time_range)
        self._canvas.set_value_range(*self._value_range)

        if self._toolbar_frame and self._canvas.fcurve_widget:
            with self._toolbar_frame:
                self._toolbar = CurveEditorToolbar(self._canvas.fcurve_widget)

        if self._canvas:
            self._model_sub = self._model.subscribe(self._on_model_changed)

    # ─────────────────────────────────────────────────────────────────────────
    # Event Handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _on_selection_changed(self, selection: SelectionInfo) -> None:
        """Handle selection change from FCurveWidget."""
        self._refresh_toolbar_state()

    def _on_curve_changed(self, curve_id: str) -> None:
        """Handle curve change from FCurveWidget."""
        self._refresh_toolbar_state()

        if self._on_change:
            self._on_change()

    def _on_model_changed(self, curve_id: str) -> None:
        """Handle storage change (undo, external edit)."""
        self._refresh_toolbar_state()
        if self._curve_tree:
            self._curve_tree.refresh()

    def _on_curve_visibility_changed(self, curve_id: str, visible: bool) -> None:
        """Handle curve visibility toggle from the tree panel."""
        if self.fcurve_widget:
            self.fcurve_widget.set_curve_visible(curve_id, visible)

    def _handle_create_curve(self, curve_id: str) -> None:
        """Handle curve creation from tree panel — forward to external callback, then reload."""
        if self._on_create_curve:
            self._on_create_curve(curve_id)
        self._reload_canvas()
        self.fit_all()

    def _handle_delete_curve(self, curve_id: str) -> None:
        """Handle curve deletion from tree panel — forward to external callback, then reload."""
        if self._on_delete_curve:
            self._on_delete_curve(curve_id)
        self._reload_canvas()

    def _reload_canvas(self) -> None:
        """Reload curves from storage into the canvas and refresh tree icons."""
        if self._canvas:
            self._canvas.reload_from_storage()
        if self._curve_tree:
            self._curve_tree.refresh()

    @staticmethod
    def _extract_curve_colors(
        layout: CurveEditorLayout,
        inherited_color: int = 0xFFAAAAAA,
    ) -> dict[str, int]:
        """Walk the layout tree and collect {curve_id: display_color}."""
        colors: dict[str, int] = {}
        color = layout.get("display_color", inherited_color)
        for child in layout.get("children", {}).values():
            colors.update(CurveEditorWidget._extract_curve_colors(child, color))
        for curve in layout.get("curves", []):
            colors[curve["id"]] = curve.get("display_color", color)
        return colors

    def _refresh_toolbar_state(self) -> None:
        """Refresh toolbar button highlights to reflect the current selection.

        Reads tangent types and broken state from the FCurveWidget's in-memory
        model (the single source of truth for the UI), not the storage backend.

        When all selected keys agree on a property the toolbar shows that value
        as active (e.g. highlights the "LINEAR" button).  When keys disagree
        the toolbar shows an indeterminate state (no button highlighted).
        """
        if not self._toolbar or not self.fcurve_widget:
            return

        selection = self.fcurve_widget.selection
        has_selection = len(selection.keys) > 0

        # None means "indeterminate / mixed" — toolbar won't highlight any button.
        consensus_in_type: TangentType | None = None
        consensus_out_type: TangentType | None = None
        consensus_broken: bool | None = None

        if has_selection:
            curves = self.fcurve_widget.curves

            # Collect the distinct values across every selected key.
            unique_in_types: set[TangentType] = set()
            unique_out_types: set[TangentType] = set()
            unique_broken_states: set[bool] = set()

            for key_ref in selection.keys:
                curve = curves.get(key_ref.curve_id)
                if curve and 0 <= key_ref.key_index < len(curve.keys):
                    key = curve.keys[key_ref.key_index]
                    unique_in_types.add(key.in_tangent_type)
                    unique_out_types.add(key.out_tangent_type)
                    unique_broken_states.add(key.tangent_broken)

            # Consensus: if the set has exactly one entry all keys agree.
            if len(unique_in_types) == 1:
                consensus_in_type = unique_in_types.pop()
            if len(unique_out_types) == 1:
                consensus_out_type = unique_out_types.pop()
            if len(unique_broken_states) == 1:
                consensus_broken = unique_broken_states.pop()

        self._toolbar.update_selection_state(
            has_selection=has_selection,
            in_tangent_type=consensus_in_type,
            out_tangent_type=consensus_out_type,
            tangents_broken=consensus_broken,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Viewport Control
    # ─────────────────────────────────────────────────────────────────────────

    def set_time_range(self, time_min: float, time_max: float) -> None:
        """
        Set the X-axis (time) range.

        Args:
            time_min: Minimum time value.
            time_max: Maximum time value.
        """
        if self._canvas:
            self._canvas.set_time_range(time_min, time_max)

    def set_value_range(self, value_min: float, value_max: float) -> None:
        """
        Set the Y-axis (value) range.

        Args:
            value_min: Minimum value.
            value_max: Maximum value.
        """
        if self._canvas:
            self._canvas.set_value_range(value_min, value_max)

    def fit_all(self) -> None:
        """Adjust viewport to fit all curve data."""
        if self._canvas:
            self._canvas.fit_to_data()

    # ─────────────────────────────────────────────────────────────────────────
    # Curve Operations
    # ─────────────────────────────────────────────────────────────────────────

    def add_curve(self, curve: FCurve) -> None:
        """
        Add a curve to the editor.

        Args:
            curve: The FCurve to add.
        """
        self._model.commit_curve(curve.id, curve)

    def remove_curve(self, curve_id: str) -> None:
        """
        Remove a curve from the editor.

        Args:
            curve_id: ID of the curve to remove.
        """
        empty_curve = FCurve(id=curve_id, keys=[])
        self._model.commit_curve(curve_id, empty_curve)

    def get_curve(self, curve_id: str) -> FCurve | None:
        """
        Get a curve by ID.

        Args:
            curve_id: The curve ID.

        Returns:
            The FCurve, or None if not found.
        """
        return self._model.get_curve(curve_id)

    def get_curve_ids(self) -> list[str]:
        """
        Get all curve IDs.

        Returns:
            List of curve IDs.
        """
        return self._model.get_curve_ids()

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────
