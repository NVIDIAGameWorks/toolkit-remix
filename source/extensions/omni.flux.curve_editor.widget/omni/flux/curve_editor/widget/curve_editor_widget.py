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
Storage is handled via GroupedKeysModel.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack, nullcontext
from dataclasses import replace
from functools import partial

from carb.input import (
    KEYBOARD_MODIFIER_FLAG_ALT,
    KEYBOARD_MODIFIER_FLAG_CONTROL,
    KEYBOARD_MODIFIER_FLAG_SHIFT,
    KEYBOARD_MODIFIER_FLAG_SUPER,
    DeviceType,
    KeyboardInput,
    MouseInput,
    acquire_input_interface,
)
from omni import ui
from omni.appwindow import get_default_app_window
from omni.flux.fcurve.widget import (
    CurveBounds,
    FCurve,
    FCurveKey,
    FCurveWidget,
    KeyReference,
    SelectionInfo,
)
from omni.flux.utils.widget import GroupedKeysModel
from omni.kit.app import get_app
from omni.kit.undo import get_undo_stack, undo

from .canvas import CurveEditorCanvas, FrameType
from .layout import CurveEditorLayout
from .panels import CurveTreePanel
from .style import build_default_style
from .toolbar import CurveEditorToolbar, _delete_selected_keys, _selected_editable_keys

__all__ = ["CurveEditorWidget"]

_POSITION_FIELD_WIDTH = ui.Pixel(90)
_POSITION_FIELD_HEIGHT = ui.Pixel(20)
_POSITION_FIELD_SPACING = ui.Pixel(6)
_POSITION_FIELD_PRECISION = 5
_POSITION_DRAG_STEP_FRACTION = 0.01


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
        layout: Optional curve tree layout and display metadata.
        time_range: Initial X-axis range (time_min, time_max).
        value_range: Initial Y-axis range (value_min, value_max).
        per_curve_bounds: Optional hard time/value bounds keyed by curve id.
        show_toolbar: Whether to show the toolbar.
        toolbar_height: Toolbar height in pixels.
        curve_panel_width: Width of the optional curve hierarchy panel.
        ruler_size: Ruler width/height in pixels.
        zoom_factor_base: Scroll-wheel zoom factor base.
        grid_time_divisions: Target number of time-axis grid divisions.
        grid_value_divisions: Target number of value-axis grid divisions.
        grid_margin: Grid pixel margin.
        grid_min_viewport_size: Minimum viewport dimension before grid is hidden.
        on_change: Optional callback when curves are modified.
        on_create_curve: Optional callback for add-curve actions.
        on_delete_curve: Optional callback for delete-curve actions.
        edit_context_factory: Create a context for each grouped edit action.
        finalization_context_factory: Group completed gestures; defaults to the edit context factory.
    """

    def __init__(
        self,
        model: GroupedKeysModel,
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
        edit_context_factory: Callable[[], AbstractContextManager] = nullcontext,
        finalization_context_factory: Callable[[], AbstractContextManager] | None = None,
    ) -> None:
        """Create the curve editor widget.

        Args:
            model: Grouped-key storage backend for curve payloads.
            layout: Optional curve tree layout and display metadata.
            time_range: Initial X-axis range.
            value_range: Initial Y-axis range.
            per_curve_bounds: Optional hard time/value bounds keyed by curve id.
            show_toolbar: Whether to show the toolbar.
            toolbar_height: Toolbar height in pixels.
            curve_panel_width: Width of the optional curve hierarchy panel.
            ruler_size: Ruler width/height in pixels.
            zoom_factor_base: Scroll-wheel zoom factor base.
            grid_time_divisions: Target number of time-axis grid divisions.
            grid_value_divisions: Target number of value-axis grid divisions.
            grid_margin: Grid pixel margin.
            grid_min_viewport_size: Minimum viewport dimension before grid is hidden.
            on_change: Optional callback when any curve changes.
            on_create_curve: Optional callback for add-curve actions.
            on_delete_curve: Optional callback for delete-curve actions.
            edit_context_factory: Create a fresh context for each grouped edit action.
            finalization_context_factory: Group completed gestures; defaults to the edit context factory.
        """
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
        self._edit_context_factory = edit_context_factory
        self._finalization_context_factory = (
            edit_context_factory if finalization_context_factory is None else finalization_context_factory
        )

        self._frame: ui.Frame | None = None
        self._canvas: CurveEditorCanvas | None = None
        self._toolbar: CurveEditorToolbar | None = None
        self._toolbar_frame: ui.Frame | None = None
        self._curve_tree: CurveTreePanel | None = None

        self._position_fields: dict[str, ui.FloatDrag] = {}
        self._position_offset_labels: dict[str, ui.Label] = {}
        self._position_subscriptions = []
        self._position_baseline: dict[str, list[FCurveKey]] = {}
        self._position_curves: dict[str, FCurve] = {}
        self._position_key_objects: dict[str, tuple[FCurveKey, ...]] = {}
        self._position_keys: tuple[KeyReference, ...] = ()
        self._position_axis: str | None = None
        self._position_pointer_edit = False
        self._position_last_value = 0.0
        self._position_edit_stack: ExitStack | None = None
        self._updating_position_fields = False
        self._position_edit_invalidated = False
        self._deferred_reload_sub = None
        self._destroyed = False

        self._build_ui()

    @property
    def fcurve_widget(self) -> FCurveWidget | None:
        """
        Access the underlying FCurveWidget.

        Its curves contain the displayed subset; model.group_ids is the full inventory.
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
    def model(self) -> GroupedKeysModel:
        """Access the curve storage model."""
        return self._model

    def delete_selected_keys(self) -> None:
        """Delete eligible selected keys in one action unless an ordinary drag is active."""
        if not self._canvas:
            return
        fcurve_widget = self._canvas.fcurve_widget
        if fcurve_widget is None or (self._canvas.is_dragging and not fcurve_widget.is_inserting_key):
            return
        _delete_selected_keys(fcurve_widget, self._edit_context_factory)

    def destroy(self) -> None:
        """Finish numeric editing and release the composed editor's resources."""
        if self._destroyed:
            return
        self._deferred_reload_sub = None
        try:
            self._finish_position_edit()
        finally:
            self._destroyed = True
            self._position_subscriptions.clear()
            for field in self._position_fields.values():
                field.set_key_pressed_fn(None)
            self._position_fields.clear()
            self._position_offset_labels.clear()
            with ExitStack() as cleanup:
                for child in (self._frame, self._curve_tree, self._canvas):
                    if child:
                        cleanup.callback(child.destroy)
                self._canvas = None
                self._curve_tree = None
                self._frame = None
                self._toolbar = None
                self._toolbar_frame = None

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
                                        on_curves_selected=self._on_curves_selected,
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
                                on_model_changed=self._on_model_changed,
                                edit_context_factory=self._finalization_context_factory,
                            )

                    with ui.VStack(height=0):
                        ui.Spacer(height=_POSITION_FIELD_SPACING)
                        with ui.HStack(height=_POSITION_FIELD_HEIGHT, spacing=_POSITION_FIELD_SPACING):
                            ui.Spacer()
                            for axis in ("time", "value"):
                                with ui.HStack(width=0):
                                    ui.Label(axis.title(), width=0)
                                    self._position_offset_labels[axis] = ui.Label(" Offset", width=0, visible=False)
                                field = ui.FloatDrag(
                                    model=ui.SimpleFloatModel(),
                                    identifier=f"CurveEditor{axis.title()}Drag",
                                    width=_POSITION_FIELD_WIDTH,
                                    precision=_POSITION_FIELD_PRECISION,
                                    enabled=False,
                                )
                                self._position_fields[axis] = field
                                field.set_key_pressed_fn(self._on_position_key_pressed)
                                self._position_subscriptions.extend(
                                    (
                                        field.model.subscribe_begin_edit_fn(
                                            partial(self._on_position_edit_begin, axis)
                                        ),
                                        field.model.subscribe_value_changed_fn(
                                            partial(self._on_position_value_changed, axis)
                                        ),
                                        field.model.subscribe_end_edit_fn(partial(self._on_position_edit_end, axis)),
                                    )
                                )
                            ui.Spacer(width=_POSITION_FIELD_SPACING)
                        ui.Spacer(height=_POSITION_FIELD_SPACING)

        if self._layout:
            colors = self._extract_curve_colors(self._layout)
            self._canvas.set_curve_colors(colors)
            self._canvas.set_selected_curve_ids(set(colors))
        self._canvas.set_time_range(*self._time_range)
        self._canvas.set_value_range(*self._value_range)

        if self._toolbar_frame and self._canvas.fcurve_widget:
            with self._toolbar_frame:
                self._toolbar = CurveEditorToolbar(
                    self._canvas.fcurve_widget,
                    self._edit_context_factory,
                    on_frame_time=partial(self._canvas.fit_to_data, frame_type=FrameType.TIME),
                    on_frame_value=partial(self._canvas.fit_to_data, frame_type=FrameType.VALUE),
                )
            self._refresh_toolbar_state()

        self._refresh_position_fields()

    # ─────────────────────────────────────────────────────────────────────────
    # Event Handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _on_selection_changed(self, selection: SelectionInfo) -> None:
        """Handle selection change from FCurveWidget."""
        if not self._position_edit_invalidated:
            self._finish_position_edit()
        self._refresh_toolbar_state()
        self._refresh_position_fields()

    def _on_curve_changed(self, curve_id: str) -> None:
        """Handle curve change from FCurveWidget."""
        self._refresh_toolbar_state()
        self._refresh_position_fields()

        if self._on_change:
            self._on_change()

    def _on_model_changed(self, curve_id: str) -> None:
        """Handle storage change (undo, external edit)."""
        if self._destroyed:
            return
        if self._position_axis is not None:
            self._position_edit_invalidated = True
            if self._deferred_reload_sub is None:
                self._deferred_reload_sub = (
                    get_app().get_update_event_stream().create_subscription_to_pop(self._finish_external_reload)
                )
            self._refresh_position_fields()
            return
        self._reload_canvas()
        self._refresh_toolbar_state()
        self._refresh_position_fields()

    def _finish_external_reload(self, _event) -> None:
        """Close the interrupted edit outside the storage notice before reloading."""
        self._deferred_reload_sub = None
        try:
            self._finish_position_edit()
        finally:
            if not self._destroyed:
                self._reload_canvas()
                self._refresh_toolbar_state()
                self._refresh_position_fields()

    def _on_curves_selected(self, curve_ids: set[str]) -> None:
        """Apply channel selection once the canvas exists and refresh toolbar availability."""
        self._finish_position_edit()
        if self._canvas:
            self._canvas.set_selected_curve_ids(curve_ids)
            self._refresh_toolbar_state()
            self._refresh_position_fields()

    def _handle_create_curve(self, curve_id: str) -> None:
        """Handle curve creation from tree panel — forward to external callback, then reload."""
        self._finish_position_edit()
        if self._on_create_curve:
            self._on_create_curve(curve_id)
        self._reload_canvas()
        self.fit_all()

    def _handle_delete_curve(self, curve_id: str) -> None:
        """Handle curve deletion from tree panel — forward to external callback, then reload."""
        self._finish_position_edit()
        if self._on_delete_curve:
            self._on_delete_curve(curve_id)
        self._reload_canvas()

    def _reload_canvas(self) -> None:
        """Reload curves from storage into the canvas and refresh tree icons."""
        if self._canvas:
            self._canvas.reload_from_storage()
        if self._curve_tree:
            self._curve_tree.refresh()

    def _refresh_position_fields(self) -> None:
        """Show absolute coordinates or gesture offsets without writing curve data."""
        if not self._position_fields or self._updating_position_fields:
            return
        widget = self.fcurve_widget
        references = widget.editable_selected_keys if widget else ()
        multiple = len(references) > 1
        self._updating_position_fields = True
        try:
            for axis, field in self._position_fields.items():
                field.enabled = bool(references) and not self._position_edit_invalidated
                self._position_offset_labels[axis].visible = multiple
                field.tooltip = (
                    f"Offset the {axis} of selected keys on visible, unlocked curves."
                    if multiple
                    else f"Edit the selected keyframe's {axis}."
                )
                if self._position_axis is not None:
                    continue
                value = 0.0
                if len(references) == 1:
                    reference = references[0]
                    key = widget.curves[reference.curve_id].keys[reference.key_index]
                    value = key.time if axis == "time" else key.value
                if field.model.as_float != value:
                    field.model.set_value(value)
        finally:
            self._updating_position_fields = False

    def _on_position_edit_begin(self, axis: str, model: ui.AbstractValueModel) -> None:
        """Capture a gesture baseline without opening an undo group."""
        if self._destroyed or self._updating_position_fields or self._position_edit_invalidated:
            return
        self._finish_position_edit()
        widget = self.fcurve_widget
        references = widget.editable_selected_keys if widget else ()
        if not references:
            return
        curves = widget.curves
        self._position_keys = references
        self._position_curves = {reference.curve_id: curves[reference.curve_id] for reference in references}
        self._position_key_objects = {curve_id: tuple(curve.keys) for curve_id, curve in self._position_curves.items()}
        self._position_baseline = {
            curve_id: [replace(key) for key in curve.keys] for curve_id, curve in self._position_curves.items()
        }
        self._position_axis = axis
        self._position_pointer_edit = not (
            acquire_input_interface().get_modifier_flags(device_types=[DeviceType.KEYBOARD])
            & KEYBOARD_MODIFIER_FLAG_CONTROL
        )
        self._position_last_value = model.as_float
        axis_range = widget.time_range if axis == "time" else widget.value_range
        self._position_fields[axis].step = _POSITION_DRAG_STEP_FRACTION * (axis_range[1] - axis_range[0])

    def _position_sources_unchanged(self) -> bool:
        """Check that the frozen references still identify the same editable key objects."""
        widget = self.fcurve_widget
        if not widget or widget.editable_selected_keys != self._position_keys:
            return False
        curves = widget.curves
        return all(
            curves.get(curve_id) is curve
            and len(curve.keys) == len(self._position_key_objects[curve_id])
            and all(key is original for key, original in zip(curve.keys, self._position_key_objects[curve_id]))
            for curve_id, curve in self._position_curves.items()
        )

    def _on_position_value_changed(self, axis: str, model: ui.AbstractValueModel) -> None:
        """Apply a numeric input immediately inside one lazily opened model edit."""
        if self._updating_position_fields or self._position_edit_invalidated or axis != self._position_axis:
            return
        if not self._position_sources_unchanged():
            self._position_edit_invalidated = True
            self._finish_position_edit()
            return
        if model.as_float == self._position_last_value:
            return
        reference = self._position_keys[0]
        original = self._position_baseline[reference.curve_id][reference.key_index]
        offset = model.as_float
        if len(self._position_keys) == 1:
            offset -= original.time if axis == "time" else original.value
        widget = self.fcurve_widget
        self._updating_position_fields = True
        try:
            positions = widget.prepare_key_offset(
                self._position_baseline,
                self._position_keys,
                time_offset=offset if axis == "time" else 0.0,
                value_offset=offset if axis == "value" else 0.0,
            )
            changed = any(
                (
                    self._position_curves[key.curve_id].keys[key.key_index].time,
                    self._position_curves[key.curve_id].keys[key.key_index].value,
                )
                != position
                for key, position in positions.items()
            )
            if changed:
                if self._position_edit_stack is None:
                    self._position_edit_stack = ExitStack()
                    mouse = get_default_app_window().get_mouse()
                    self._position_pointer_edit = self._position_pointer_edit and (
                        acquire_input_interface().get_mouse_value(mouse, MouseInput.LEFT_BUTTON) > 0
                    )
                    self._position_edit_stack.enter_context(self._canvas.edit_curves(self._position_curves))
                widget.set_key_positions(positions, baseline=self._position_baseline)
            position = positions[reference]
            applied = position[0] if axis == "time" else position[1]
            if len(self._position_keys) > 1:
                applied -= original.time if axis == "time" else original.value
            if model.as_float != applied:
                model.set_value(applied)
            self._position_last_value = model.as_float
        except Exception:
            self._position_edit_invalidated = True
            try:
                self._finish_position_edit()
            finally:
                self._reload_canvas()
            raise
        finally:
            self._updating_position_fields = False
            if self._position_axis is None:
                self._refresh_position_fields()

    def _on_position_edit_end(self, axis: str, model: ui.AbstractValueModel) -> None:
        """Apply the final native field value before closing its gesture."""
        if axis == self._position_axis and not self._position_edit_invalidated:
            self._finish_position_edit()

    def _on_position_key_pressed(self, key: int, modifiers: int, pressed: bool) -> None:
        """Cancel a held pointer edit while preserving native text history."""
        modifier_mask = (
            KEYBOARD_MODIFIER_FLAG_CONTROL
            | KEYBOARD_MODIFIER_FLAG_SHIFT
            | KEYBOARD_MODIFIER_FLAG_ALT
            | KEYBOARD_MODIFIER_FLAG_SUPER
        )
        if (
            not pressed
            or key != int(KeyboardInput.Z)
            or (modifiers & modifier_mask) != KEYBOARD_MODIFIER_FLAG_CONTROL
            or self._position_edit_stack is None
            or self._position_edit_invalidated
            or not self._position_pointer_edit
        ):
            return

        mouse = get_default_app_window().get_mouse()
        if acquire_input_interface().get_mouse_value(mouse, MouseInput.LEFT_BUTTON) <= 0:
            return

        stack = get_undo_stack()
        previous_top = stack[-1] if stack else None
        self._finish_position_edit()
        stack = get_undo_stack()
        if stack and stack[-1] is not previous_top:
            undo()

    def _finish_position_edit(self) -> None:
        """Finalize a live gesture and reset offset controls, including failure paths."""
        if self._position_axis is None:
            return
        try:
            if not self._position_edit_invalidated and not self._updating_position_fields:
                axis = self._position_axis
                self._on_position_value_changed(axis, self._position_fields[axis].model)
        finally:
            edits = self._position_edit_stack
            self._position_edit_stack = None
            self._position_axis = None
            self._position_pointer_edit = False
            self._position_keys = ()
            self._position_baseline.clear()
            self._position_curves.clear()
            self._position_key_objects.clear()
            try:
                if edits is not None:
                    with edits, self._finalization_context_factory():
                        edits.close()
            except Exception:
                self._reload_canvas()
                raise
            finally:
                self._position_edit_invalidated = False
                self._refresh_position_fields()

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
        """Refresh toolbar consensus from selected keys on editable displayed curves."""
        if not self._toolbar or not self.fcurve_widget:
            return

        selected_keys = _selected_editable_keys(self.fcurve_widget)
        unique_in_types = {key.in_tangent_type for _, key in selected_keys}
        unique_out_types = {key.out_tangent_type for _, key in selected_keys}
        unique_broken_states = {key.tangent_broken for _, key in selected_keys}

        self._toolbar.update_selection_state(
            has_selection=bool(selected_keys),
            in_tangent_type=unique_in_types.pop() if len(unique_in_types) == 1 else None,
            out_tangent_type=unique_out_types.pop() if len(unique_out_types) == 1 else None,
            tangents_broken=unique_broken_states.pop() if len(unique_broken_states) == 1 else None,
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
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────
