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

__all__ = ["AlphaCutoutPane"]

import asyncio
import dataclasses
import functools
import math
import re
import threading
from collections.abc import Callable

import carb
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import REGEX_VALID_PATH
from lightspeed.trex.alpha_cutout.core import (
    AlphaCutoutStageEditor,
    ConversionTarget,
    MeshCutoutResult,
    StageEditOutcome,
    convert_meshes,
    read_mesh_sources,
    resolve_conversion_targets,
    write_cutout_mesh,
    write_cutout_replacement,
)
from lightspeed.trex.utils.widget import TrexMessageDialog, WorkspaceWidget
from omni.flux.utils.common.progress import run_worker_with_latest_progress
from omni.flux.utils.dialog import ProgressPopup
from omni.flux.utils.widget.collapsable_frame import PropertyCollapsableFrameWithInfoPopup
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker

from .settings import ALPHA_THRESHOLD_RANGE, DEFAULT_DISABLE_ALPHA_TEST, TRACE_RESOLUTION_RANGE, AlphaCutoutSettings

_NO_SELECTION_MESSAGE = "Nothing convertible is selected. Select a capture or replacement mesh in the Stage Manager."
_NO_ALPHA_MESHES_MESSAGE = "The replacement file has no mesh with a diffuse texture."
_REPLACEMENT_OUTPUT_TOOLTIP = "Replacements are written next to their original file, which is never overwritten."
_FIELD_STYLE = "Field"
_DRAG_STYLE = "DragField"
_FIELD_ERROR_STYLE = "FieldError"
_INDICATOR_STYLE = "OverrideIndicator"
_INDICATOR_DEFAULT_STYLE = "OverrideIndicatorForceDisabled"
_THICKEN_TITLE_ON = "THICKEN (ON)"
_THICKEN_TITLE_OFF = "THICKEN (OFF)"
_DEFAULTS = AlphaCutoutSettings.defaults()


@dataclasses.dataclass
class _SettingRow:
    """A parameter row with its reset indicator."""

    widget: ui.AbstractField | ui.CheckBox
    default: object
    indicator: ui.Circle
    section: str
    persist: Callable[[ui.AbstractValueModel], None] | None

    def is_default(self) -> bool:
        """Return whether the widget shows the default value.

        Returns:
            ``True`` when the value equals the default.
        """
        model = self.widget.model
        if isinstance(self.default, bool):
            return model.get_value_as_bool() == self.default
        if isinstance(self.default, int):
            return model.get_value_as_int() == self.default
        return math.isclose(model.get_value_as_float(), float(self.default), abs_tol=1e-6)


class AlphaCutoutPane(WorkspaceWidget):
    """Form that converts the selected capture or replacement meshes into alpha cutouts."""

    _SPACING_XS = ui.Pixel(4)
    _SPACING_SM = ui.Pixel(8)
    _SPACING_LG = ui.Pixel(16)
    _ROW_HEIGHT = ui.Pixel(24)
    _FIELD_HEIGHT = ui.Pixel(18)
    _ICON_SIZE = ui.Pixel(20)
    _LABEL_WIDTH = ui.Pixel(170)
    _RESULTS_HEIGHT = ui.Pixel(160)
    _MAX_MESH_ROWS = 5
    _INDICATOR_SIZE = ui.Pixel(12)
    _BUTTON_HEIGHT = ui.Pixel(32)
    _FLOAT_STEP = 0.1

    def __init__(self, context_name: str = ""):
        """Build the pane for a USD context.

        Args:
            context_name: USD context that holds the project.
        """
        super().__init__()
        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        self._settings = AlphaCutoutSettings()
        self._editor = AlphaCutoutStageEditor(context_name)
        self._target: ConversionTarget | None = None
        self._mesh_toggles: dict[str, ui.CheckBox] = {}
        self._mesh_subscriptions: list = []
        self._output_locked = False
        self._setting_rows: list[_SettingRow] = []
        self._thicken_frame: PropertyCollapsableFrameWithInfoPopup | None = None
        self._current_section = ""
        self._result_lines: list[str] = []
        self._job_running = False
        self._output_valid = False
        self._convert_task: asyncio.Task | None = None
        self._field_subscriptions: list = []
        self._selection_subscription = None

        self.root_widget: ui.Frame | None = None
        self._mesh_list_frame: ui.Frame | None = None
        self._output_field: ui.StringField | None = None
        self._browse_button: ui.Image | None = None
        self._alpha_threshold_field: ui.IntSlider | None = None
        self._trace_resolution_field: ui.IntSlider | None = None
        self._simplify_tolerance_field: ui.FloatDrag | None = None
        self._edge_margin_field: ui.FloatDrag | None = None
        self._min_island_area_field: ui.FloatDrag | None = None
        self._disable_alpha_test_checkbox: ui.CheckBox | None = None
        self._minimal_outline_checkbox: ui.CheckBox | None = None
        self._thicken_checkbox: ui.CheckBox | None = None
        self._thickness_field: ui.FloatDrag | None = None
        self._thicken_back_face_checkbox: ui.CheckBox | None = None
        self._thicken_anti_stretch_checkbox: ui.CheckBox | None = None
        self._smooth_normals_checkbox: ui.CheckBox | None = None
        self._smoothing_field: ui.FloatSlider | None = None
        self._up_normals_checkbox: ui.CheckBox | None = None
        self._up_amount_field: ui.FloatSlider | None = None
        self._convert_button: ui.Button | None = None
        self._results_frame: ui.Frame | None = None

        self.__create_ui()

    @property
    def target(self) -> ConversionTarget | None:
        """Return what is up for conversion.

        Returns:
            The capture or replacement target, or ``None``.
        """
        return self._target

    @property
    def selected_mesh_paths(self) -> list[str]:
        """Return the meshes of the target that are ticked for conversion.

        Returns:
            Stage paths in the order the target lists them.
        """
        if not self._target:
            return []
        return [
            path
            for path in self._target.meshes
            if self._mesh_toggles.get(path) is None or self._mesh_toggles[path].model.get_value_as_bool()
        ]

    @property
    def output_folder(self) -> str:
        """Return the output folder currently entered in the form.

        Returns:
            Folder path, possibly empty.
        """
        return self._output_field.model.get_value_as_string().strip() if self._output_field else ""

    @property
    def job_running(self) -> bool:
        """Return whether a conversion is in progress.

        Returns:
            ``True`` while the worker runs or the results are applied.
        """
        return self._job_running

    def set_target(self, target: ConversionTarget | None) -> None:
        """Set what is up for conversion.

        Args:
            target: Resolved target, or ``None`` when nothing convertible is selected.
        """
        self._target = target
        self._rebuild_mesh_list()
        self._apply_output_mode()
        self._update_convert_button()

    def set_from_prim_paths(self, prim_paths: list[str]) -> None:
        """Resolve prim paths to a target and set the first one.

        Args:
            prim_paths: Selected prim paths.
        """
        stage = self._context.get_stage() if self._context else None
        targets = resolve_conversion_targets(stage, list(prim_paths)) if stage else []
        self.set_target(targets[0] if targets else None)

    def _on_selection_changed(self, _event) -> None:
        """Follow the USD selection while the window is open.

        The first selected convertible prim is up for conversion; a selection without one clears it. A running
        conversion keeps its target.

        Args:
            _event: Stage event; unused.
        """
        if self._job_running or not self._context:
            return
        stage = self._context.get_stage()
        if not stage:
            return
        targets = resolve_conversion_targets(stage, self._context.get_selection().get_selected_prim_paths())
        selected = targets[0] if targets else None
        if selected != self._target:
            self.set_target(selected)

    def show(self, visible: bool) -> None:
        """Refresh the output folder default when the window is shown.

        Args:
            visible: Whether the containing window is visible.
        """
        super().show(visible)
        if visible:
            self._refresh_output_folder()
            self._selection_subscription = self._context.get_stage_event_stream().create_subscription_to_pop_by_type(
                int(omni.usd.StageEventType.SELECTION_CHANGED),
                self._on_selection_changed,
                name="Alpha cutout selection",
            )
        else:
            self._selection_subscription = None

    def destroy(self) -> None:
        """Cancel a pending conversion and release every resource."""
        if self._convert_task and not self._convert_task.done():
            self._convert_task.cancel()
        self._convert_task = None
        self._field_subscriptions = []
        self._selection_subscription = None
        if self._editor:
            self._editor.destroy()
        self._editor = None
        self._settings = None
        self._context = None
        self._mesh_subscriptions = []
        self._mesh_toggles = {}
        self._mesh_list_frame = None
        self._setting_rows = []
        self._thicken_frame = None
        self._output_field = None
        self._browse_button = None
        self._alpha_threshold_field = None
        self._trace_resolution_field = None
        self._simplify_tolerance_field = None
        self._edge_margin_field = None
        self._min_island_area_field = None
        self._disable_alpha_test_checkbox = None
        self._convert_button = None
        self._results_frame = None
        self.root_widget = None
        self._mark_destroyed()

    def __create_ui(self):
        self.root_widget = ui.Frame()
        with self.root_widget:
            with ui.ScrollingFrame(
                name="Background_GREY_50",
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            ):
                with ui.HStack():
                    ui.Spacer(width=self._SPACING_SM)
                    with ui.VStack(spacing=self._SPACING_LG):
                        ui.Spacer(height=0)
                        self._build_meshes_section()
                        self._build_output_section()
                        self._build_parameters_section()
                        self._build_thicken_section()
                        self._build_normals_section()
                        self._convert_button = ui.Button(
                            "Convert",
                            height=self._BUTTON_HEIGHT,
                            clicked_fn=self._on_convert_pressed,
                            identifier="alpha_cutout_convert_button",
                        )
                        self._build_results_section()
                        ui.Spacer(height=0)
                    ui.Spacer(width=self._SPACING_SM)
        self._load_settings_into_fields()
        self.set_target(self._target)
        self._rebuild_results()
        self._update_convert_button()

    def _build_meshes_section(self):
        frame = PropertyCollapsableFrameWithInfoPopup(
            "SELECTED MESH",
            info_text=(
                "The meshes up for conversion. A capture shows its prototype; a replacement lists every mesh of "
                "its file that has a diffuse texture, ticked for conversion. The section follows the selection."
            ),
            collapsed=False,
        )
        with frame:
            self._mesh_list_frame = ui.Frame()

    def _rebuild_mesh_list(self):
        if not self._mesh_list_frame:
            return
        self._mesh_subscriptions = []
        self._mesh_toggles = {}
        self._mesh_list_frame.clear()
        target = self._target
        with self._mesh_list_frame:
            if target is None or not target.meshes:
                message = _NO_ALPHA_MESHES_MESSAGE if target else _NO_SELECTION_MESSAGE
                with ui.HStack(height=self._ROW_HEIGHT):
                    ui.Label(message, elided_text=True, identifier="alpha_cutout_mesh_path")
                return
            rows = min(len(target.meshes), self._MAX_MESH_ROWS)
            with ui.ScrollingFrame(
                height=ui.Pixel(rows * self._ROW_HEIGHT.value),
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            ):
                with ui.VStack(height=0):
                    for path in target.meshes:
                        with ui.HStack(height=self._ROW_HEIGHT, spacing=self._SPACING_SM):
                            toggle = ui.CheckBox(width=0, identifier="alpha_cutout_mesh_toggle")
                            toggle.model.set_value(True)
                            self._mesh_subscriptions.append(
                                toggle.model.subscribe_value_changed_fn(lambda _model: self._update_convert_button())
                            )
                            self._mesh_toggles[path] = toggle
                            ui.Label(
                                self._mesh_label_text(target, path),
                                elided_text=True,
                                tooltip=path,
                                identifier="alpha_cutout_mesh_path",
                            )

    @staticmethod
    def _mesh_label_text(target: ConversionTarget, path: str) -> str:
        """Return the row text of a mesh: the path relative to the reference prim for replacements.

        Args:
            target: Target the mesh belongs to.
            path: Stage path of the mesh.

        Returns:
            Display text.
        """
        if target.is_replacement and path.startswith(target.root_path):
            return path[len(target.root_path) :].strip("/") or path
        return path

    def _apply_output_mode(self):
        """Lock the output field to the cutout path of a replacement, or restore the folder for captures."""
        if not self._output_field:
            return
        locked = bool(self._target and self._target.is_replacement)
        if locked == self._output_locked and not locked:
            return
        self._output_locked = locked
        self._output_field.enabled = not locked
        if self._browse_button:
            self._browse_button.enabled = not locked
        if locked:
            self._output_field.model.set_value(self._target.output_file or "")
        else:
            self._output_field.model.set_value(self._settings.output_folder)
            self._refresh_output_folder()
        self._update_output_valid()

    def _build_output_section(self):
        frame = PropertyCollapsableFrameWithInfoPopup(
            "OUTPUT FOLDER",
            info_text=(
                "Folder the generated replacement files are written to. Converting a mesh again overwrites its "
                "file in this folder."
            ),
            collapsed=False,
        )
        with frame:
            with ui.VStack(height=0, spacing=self._SPACING_SM):
                ui.Spacer(height=0)
                with ui.HStack(height=self._ROW_HEIGHT, spacing=self._SPACING_SM):
                    with ui.VStack():
                        ui.Spacer()
                        self._output_field = ui.StringField(
                            height=self._FIELD_HEIGHT,
                            style_type_name_override=_FIELD_STYLE,
                            identifier="alpha_cutout_output_field",
                        )
                        ui.Spacer()
                    self._field_subscriptions.append(
                        self._output_field.model.subscribe_value_changed_fn(self._on_output_changed)
                    )
                    self._field_subscriptions.append(
                        self._output_field.model.subscribe_end_edit_fn(self._on_output_end_edit)
                    )
                    with ui.VStack(width=self._ICON_SIZE):
                        ui.Spacer()
                        self._browse_button = ui.Image(
                            "",
                            name="OpenFolder",
                            width=self._ICON_SIZE,
                            height=self._ICON_SIZE,
                            mouse_pressed_fn=lambda x, y, button, modifier: self._on_browse_pressed(button),
                            identifier="alpha_cutout_browse_button",
                        )
                        ui.Spacer()
                ui.Spacer(height=0)

    def _build_parameters_section(self):
        self._current_section = "PARAMETERS"
        frame = PropertyCollapsableFrameWithInfoPopup(
            "PARAMETERS",
            info_text=(
                "Settings of the alpha trace. Distances are in texels of the traced mask, so a trace "
                "resolution of 256 means one texel is 1/256 of the texture."
            ),
            collapsed=False,
        )
        with frame:
            with ui.VStack(height=0, spacing=self._SPACING_SM):
                ui.Spacer(height=0)
                self._alpha_threshold_field = self._build_row(
                    "Alpha threshold",
                    "Alpha value from 0 to 255 at or above which a texel counts as opaque.",
                    lambda: ui.IntSlider(
                        min=ALPHA_THRESHOLD_RANGE[0],
                        max=ALPHA_THRESHOLD_RANGE[1],
                        style_type_name_override=_DRAG_STYLE,
                        identifier="alpha_cutout_alpha_threshold",
                    ),
                    lambda model: self._settings.set_alpha_threshold(model.get_value_as_int()),
                    _DEFAULTS.alpha_threshold,
                )
                self._trace_resolution_field = self._build_row(
                    "Trace resolution",
                    "Longest side of the traced mask in texels. Larger values follow the texture more closely and "
                    "produce more triangles.",
                    lambda: ui.IntSlider(
                        min=TRACE_RESOLUTION_RANGE[0],
                        max=TRACE_RESOLUTION_RANGE[1],
                        style_type_name_override=_DRAG_STYLE,
                        identifier="alpha_cutout_trace_resolution",
                    ),
                    lambda model: self._settings.set_trace_resolution(model.get_value_as_int()),
                    _DEFAULTS.trace_resolution,
                )
                self._simplify_tolerance_field = self._build_row(
                    "Simplify tolerance",
                    "Largest deviation from the traced outline in texels. Larger values produce fewer triangles.",
                    lambda: ui.FloatDrag(
                        min=0.0,
                        step=self._FLOAT_STEP,
                        style_type_name_override=_DRAG_STYLE,
                        identifier="alpha_cutout_simplify_tolerance",
                    ),
                    lambda model: self._settings.set_simplify_tolerance(model.get_value_as_float()),
                    _DEFAULTS.simplify_tolerance,
                )
                self._edge_margin_field = self._build_row(
                    "Edge margin",
                    "Distance in texels the outline grows beyond the opaque area. Negative values shrink it. "
                    "Use zero when alpha testing is disabled and the cut edge is the visible silhouette.",
                    lambda: ui.FloatDrag(
                        step=self._FLOAT_STEP,
                        style_type_name_override=_DRAG_STYLE,
                        identifier="alpha_cutout_edge_margin",
                    ),
                    lambda model: self._settings.set_edge_margin(model.get_value_as_float()),
                    _DEFAULTS.edge_margin,
                )
                self._min_island_area_field = self._build_row(
                    "Minimum island area",
                    "Opaque islands smaller than this many texels are dropped.",
                    lambda: ui.FloatDrag(
                        min=0.0,
                        step=self._FLOAT_STEP,
                        style_type_name_override=_DRAG_STYLE,
                        identifier="alpha_cutout_min_island_area",
                    ),
                    lambda model: self._settings.set_min_island_area(model.get_value_as_float()),
                    _DEFAULTS.min_island_area,
                )
                self._minimal_outline_checkbox = self._build_checkbox_row(
                    "Minimal vertex outline",
                    "Connect the traced cutoff with the fewest points that stay within the simplify tolerance "
                    "instead of the greedy pass. Slightly slower and yields fewer triangles for the same accuracy.",
                    "alpha_cutout_minimal_outline",
                    self._settings.set_minimal_outline,
                    _DEFAULTS.minimal_outline,
                )
                self._disable_alpha_test_checkbox = self._build_checkbox_row(
                    "Disable alpha test on the generated material",
                    "Author the opaque alpha state on the copied material so the runtime skips alpha "
                    "testing for the cut mesh. The material property panel labels the alpha test type "
                    "with the shader enum, which lists the runtime value as Greater Or Equal.",
                    "alpha_cutout_disable_alpha_test",
                    self._settings.set_disable_alpha_test,
                    DEFAULT_DISABLE_ALPHA_TEST,
                )
                ui.Spacer(height=0)

    def _build_thicken_section(self):
        self._current_section = "THICKEN"
        self._thicken_frame = frame = PropertyCollapsableFrameWithInfoPopup(
            "THICKEN",
            info_text="Extrude the cut mesh backwards to give the card a visible thickness.",
            collapsed=True,
        )
        with frame:
            with ui.VStack(height=0, spacing=self._SPACING_SM):
                ui.Spacer(height=0)
                self._thicken_checkbox = self._build_checkbox_row(
                    "Thicken mesh",
                    "Extrude the cut mesh backwards, against the surface normal, by the thickness. Adds two "
                    "triangles per outline edge.",
                    "alpha_cutout_thicken",
                    self._on_thicken_changed,
                    _DEFAULTS.thicken,
                )
                self._thickness_field = self._build_row(
                    "Thickness",
                    "Extrusion distance in mesh units, before the mesh transform.",
                    lambda: ui.FloatDrag(
                        min=0.0,
                        step=self._FLOAT_STEP,
                        style_type_name_override=_DRAG_STYLE,
                        identifier="alpha_cutout_thickness",
                    ),
                    lambda model: self._settings.set_thickness(model.get_value_as_float()),
                    _DEFAULTS.thickness,
                )
                self._thicken_back_face_checkbox = self._build_checkbox_row(
                    "Back face",
                    "Close the extrusion with a reversed copy of the front face. Turn it off to keep only the "
                    "sides; a double-sided capture still shows its front face from behind.",
                    "alpha_cutout_thicken_back_face",
                    self._settings.set_thicken_back_face,
                    _DEFAULTS.thicken_back_face,
                )
                self._thicken_anti_stretch_checkbox = self._build_checkbox_row(
                    "UV anti-stretch",
                    "Texture the extruded sides with the band of the texture just inside the outline instead of "
                    "smearing the edge texel across the thickness.",
                    "alpha_cutout_thicken_anti_stretch",
                    self._settings.set_thicken_anti_stretch,
                    _DEFAULTS.thicken_anti_stretch,
                )
                ui.Spacer(height=0)

    def _build_normals_section(self):
        self._current_section = "NORMALS"
        frame = PropertyCollapsableFrameWithInfoPopup(
            "NORMALS",
            info_text="Shading adjustments applied to the vertex normals of the converted mesh.",
            collapsed=True,
        )
        with frame:
            with ui.VStack(height=0, spacing=self._SPACING_SM):
                ui.Spacer(height=0)
                self._smooth_normals_checkbox = self._build_checkbox_row(
                    "Smooth normals",
                    "Blend the normals of the thickened mesh towards the average around each position so the rim "
                    "shades rounded instead of creased.",
                    "alpha_cutout_smooth_normals",
                    self._on_smooth_normals_changed,
                    _DEFAULTS.smooth_normals,
                )
                self._smoothing_field = self._build_row(
                    "Smoothing",
                    "Strength of the normal smoothing: 0 keeps the flat rim, 1 averages fully.",
                    lambda: ui.FloatSlider(
                        min=0.0,
                        max=1.0,
                        style_type_name_override=_DRAG_STYLE,
                        identifier="alpha_cutout_smoothing",
                    ),
                    lambda model: self._settings.set_smoothing(model.get_value_as_float()),
                    _DEFAULTS.smoothing,
                )
                self._up_normals_checkbox = self._build_checkbox_row(
                    "Up-facing normals",
                    "Blend every vertex normal towards the stage up axis so a canopy of cards shades like one lit "
                    "volume instead of a pile of differently tilted planes.",
                    "alpha_cutout_up_normals",
                    self._on_up_normals_changed,
                    _DEFAULTS.up_normals,
                )
                self._up_amount_field = self._build_row(
                    "Up amount",
                    "Blend weight of the up direction: 0 keeps the original normals, 1 points them straight up.",
                    lambda: ui.FloatSlider(
                        min=0.0,
                        max=1.0,
                        style_type_name_override=_DRAG_STYLE,
                        identifier="alpha_cutout_up_amount",
                    ),
                    lambda model: self._settings.set_up_amount(model.get_value_as_float()),
                    _DEFAULTS.up_amount,
                )
                ui.Spacer(height=0)

    def _build_checkbox_row(
        self, label: str, tooltip: str, identifier: str, on_changed: Callable[[bool], None], default: bool
    ) -> ui.CheckBox:
        """Build one checkbox row with a reset indicator.

        Args:
            label: Text shown right of the checkbox.
            tooltip: Explanation shown on the label.
            identifier: Widget identifier of the checkbox.
            on_changed: Receives the new value whenever it changes.
            default: Value the indicator resets to.

        Returns:
            The checkbox.
        """
        with ui.HStack(height=self._ROW_HEIGHT, spacing=self._SPACING_SM):
            indicator = self._build_indicator(f"{identifier}_reset", default)
            checkbox = ui.CheckBox(width=0, identifier=identifier)
            ui.Label(label, tooltip=tooltip)
        row = _SettingRow(checkbox, default, indicator, self._current_section, None)
        indicator.set_mouse_released_fn(lambda x, y, button, modifier: self._on_reset_pressed(button, row))
        self._setting_rows.append(row)

        def changed(model: ui.AbstractValueModel) -> None:
            on_changed(model.get_value_as_bool())
            self._refresh_indicators()

        self._field_subscriptions.append(checkbox.model.subscribe_value_changed_fn(changed))
        return checkbox

    def _build_indicator(self, identifier: str, default: object) -> ui.Circle:
        """Build the dot that shows a value differs from its default and resets it on click.

        Args:
            identifier: Widget identifier of the dot.
            default: Value shown in the tooltip.

        Returns:
            The circle.
        """
        with ui.VStack(width=self._INDICATOR_SIZE):
            ui.Spacer()
            indicator = ui.Circle(
                width=self._INDICATOR_SIZE,
                height=self._INDICATOR_SIZE,
                style_type_name_override=_INDICATOR_DEFAULT_STYLE,
                tooltip=f"When highlighted, the value differs from its default. Click to reset it to {default}.",
                identifier=identifier,
            )
            ui.Spacer()
        return indicator

    def _refresh_indicators(self) -> None:
        for row in self._setting_rows:
            row.indicator.style_type_name_override = _INDICATOR_DEFAULT_STYLE if row.is_default() else _INDICATOR_STYLE

    def _on_reset_pressed(self, button: int, row: _SettingRow) -> None:
        if button != 0 or row.is_default():
            return
        row.widget.model.set_value(row.default)
        if row.persist:
            row.persist(row.widget.model)
        self._refresh_indicators()

    def _on_thicken_changed(self, value: bool) -> None:
        self._settings.set_thicken(value)
        self._update_thicken_fields()

    def _on_smooth_normals_changed(self, value: bool) -> None:
        self._settings.set_smooth_normals(value)
        self._update_thicken_fields()

    def _on_up_normals_changed(self, value: bool) -> None:
        self._settings.set_up_normals(value)
        self._update_up_fields()

    def _update_thicken_fields(self) -> None:
        enabled = bool(self._thicken_checkbox and self._thicken_checkbox.model.get_value_as_bool())
        if self._thicken_frame:
            self._thicken_frame.root.title = _THICKEN_TITLE_ON if enabled else _THICKEN_TITLE_OFF
        smoothing = enabled and bool(
            self._smooth_normals_checkbox and self._smooth_normals_checkbox.model.get_value_as_bool()
        )
        for widget in (
            self._thickness_field,
            self._thicken_back_face_checkbox,
            self._thicken_anti_stretch_checkbox,
            self._smooth_normals_checkbox,
        ):
            if widget:
                widget.enabled = enabled
        if self._smoothing_field:
            self._smoothing_field.enabled = smoothing

    def _update_up_fields(self) -> None:
        if self._up_amount_field:
            self._up_amount_field.enabled = bool(
                self._up_normals_checkbox and self._up_normals_checkbox.model.get_value_as_bool()
            )

    def _build_row(
        self,
        label: str,
        tooltip: str,
        build_field: Callable[[], ui.AbstractField],
        on_end_edit: Callable[[ui.AbstractValueModel], None],
        default: object,
    ) -> ui.AbstractField:
        """Build one labelled parameter row with a reset indicator.

        Args:
            label: Text shown left of the field.
            tooltip: Explanation shown on the label and the field.
            build_field: Builds the field widget inside the row.
            on_end_edit: Persists the value when editing ends.
            default: Value the indicator resets to.

        Returns:
            The field widget.
        """
        with ui.HStack(height=self._ROW_HEIGHT, spacing=self._SPACING_SM):
            indicator = self._build_indicator("", default)
            ui.Label(label, width=self._LABEL_WIDTH, tooltip=tooltip)
            with ui.VStack():
                ui.Spacer()
                field = build_field()
                field.height = self._FIELD_HEIGHT
                field.tooltip = tooltip
                ui.Spacer()
        indicator.identifier = f"{field.identifier}_reset"
        row = _SettingRow(field, default, indicator, self._current_section, on_end_edit)
        indicator.set_mouse_released_fn(lambda x, y, button, modifier: self._on_reset_pressed(button, row))
        self._setting_rows.append(row)

        def end_edit(model: ui.AbstractValueModel) -> None:
            on_end_edit(model)
            self._refresh_indicators()

        self._field_subscriptions.append(field.model.subscribe_end_edit_fn(end_edit))
        return field

    def _build_results_section(self):
        frame = PropertyCollapsableFrameWithInfoPopup(
            "RESULTS",
            info_text="Outcome of the last conversion.",
            collapsed=False,
        )
        with frame:
            with ui.ScrollingFrame(
                height=self._RESULTS_HEIGHT, horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF
            ):
                self._results_frame = ui.Frame()

    def _load_settings_into_fields(self):
        self._alpha_threshold_field.model.set_value(self._settings.alpha_threshold)
        self._trace_resolution_field.model.set_value(self._settings.trace_resolution)
        self._simplify_tolerance_field.model.set_value(self._settings.simplify_tolerance)
        self._edge_margin_field.model.set_value(self._settings.edge_margin)
        self._min_island_area_field.model.set_value(self._settings.min_island_area)
        self._disable_alpha_test_checkbox.model.set_value(self._settings.disable_alpha_test)
        self._minimal_outline_checkbox.model.set_value(self._settings.minimal_outline)
        self._thicken_checkbox.model.set_value(self._settings.thicken)
        self._thickness_field.model.set_value(self._settings.thickness)
        self._thicken_back_face_checkbox.model.set_value(self._settings.thicken_back_face)
        self._thicken_anti_stretch_checkbox.model.set_value(self._settings.thicken_anti_stretch)
        self._smooth_normals_checkbox.model.set_value(self._settings.smooth_normals)
        self._smoothing_field.model.set_value(self._settings.smoothing)
        self._up_normals_checkbox.model.set_value(self._settings.up_normals)
        self._up_amount_field.model.set_value(self._settings.up_amount)
        self._update_thicken_fields()
        self._update_up_fields()
        self._refresh_indicators()
        self._output_field.model.set_value(self._settings.output_folder)
        self._refresh_output_folder()

    def _refresh_output_folder(self):
        if not self._output_field or self._output_locked:
            return
        if not self.output_folder:
            self._output_field.model.set_value(AlphaCutoutSettings.default_output_folder(self._context_name))
        self._update_output_valid()

    def _rebuild_results(self):
        if not self._results_frame:
            return
        self._results_frame.clear()
        with self._results_frame:
            with ui.VStack(height=0, spacing=self._SPACING_XS):
                for line in self._result_lines:
                    ui.Label(line, word_wrap=True, identifier="alpha_cutout_result_row")

    def _on_output_changed(self, _model):
        self._update_output_valid()

    def _on_output_end_edit(self, model):
        if not self._output_locked and self._update_output_valid():
            self._settings.set_output_folder(model.get_value_as_string().strip())

    def _on_browse_pressed(self, button: int):
        if button != 0 or self._job_running or self._output_locked:
            return
        open_file_picker(
            "Select the cutout output folder",
            self._on_folder_selected,
            lambda *_: None,
            current_file=self.output_folder or None,
            select_directory=True,
        )

    def _on_folder_selected(self, folder: str):
        if not self._output_field:
            return
        self._output_field.model.set_value(folder)
        if self._update_output_valid():
            self._settings.set_output_folder(folder.strip())

    def _validate_output_folder(self, value: str) -> tuple[bool, str]:
        """Validate an output folder path.

        Args:
            value: Folder path entered by the user.

        Returns:
            Whether the path is usable and a message explaining a rejection.
        """
        if not value.strip():
            return False, "The output folder must be set."
        if not re.search(REGEX_VALID_PATH, value):
            return False, "The output folder is not a valid path."
        return True, ""

    def _update_output_valid(self) -> bool:
        if not self._output_field:
            return False
        if self._output_locked:
            is_valid, message = True, _REPLACEMENT_OUTPUT_TOOLTIP
        else:
            is_valid, message = self._validate_output_folder(self.output_folder)
        self._output_field.style_type_name_override = _FIELD_STYLE if is_valid else _FIELD_ERROR_STYLE
        self._output_field.tooltip = message
        self._output_valid = is_valid
        self._update_convert_button()
        return is_valid

    def _update_convert_button(self):
        if not self._convert_button:
            return
        if self._job_running:
            enabled, tooltip = False, "A conversion is in progress."
        elif not self._target:
            enabled, tooltip = False, "Select a capture or replacement mesh first."
        elif not self.selected_mesh_paths:
            enabled, tooltip = False, "Tick at least one mesh."
        elif not self._output_valid:
            enabled, tooltip = False, "Set a valid output folder first."
        else:
            enabled, tooltip = True, "Convert the ticked meshes and reference the cutout on the edit target layer."
        self._convert_button.enabled = enabled
        self._convert_button.tooltip = tooltip

    def _on_convert_pressed(self):
        if self._job_running or not self._target or not self.selected_mesh_paths or not self._output_valid:
            return
        self._convert_task = asyncio.ensure_future(self._convert_async())
        self._convert_task.set_name("AlphaCutoutConvert")

    async def _convert_async(self):
        problem = self._editor.get_edit_layer_problem()
        if problem:
            TrexMessageDialog(problem, "Invalid Edit Target", disable_cancel_button=True)
            return
        self._job_running = True
        self._update_convert_button()
        try:
            stage = self._context.get_stage()
            target = self._target
            sources = read_mesh_sources(stage, self.selected_mesh_paths, target)
            results = await self._run_conversion(sources)
            if results is None:
                self._result_lines = ["The conversion was cancelled."]
                self._rebuild_results()
                return
            written = self._write_results(results, stage, target)
            outcomes = self._editor.apply(written)
            self._show_results(written, outcomes)
        finally:
            self._job_running = False
            self._update_convert_button()

    async def _run_conversion(self, sources) -> list[MeshCutoutResult] | None:
        """Run the worker behind a cancellable progress popup.

        Args:
            sources: Meshes read on the main thread.

        Returns:
            The results, or ``None`` when the user cancelled.
        """
        cancel_event = threading.Event()
        popup = ProgressPopup(title="Converting Alpha Cards", status_text="Preparing...")
        popup.set_cancel_fn(cancel_event.set)
        popup.show()
        try:
            return await run_worker_with_latest_progress(
                functools.partial(convert_meshes, sources, self._settings.parameters, is_cancelled=cancel_event.is_set),
                progress_callback=functools.partial(self._update_progress, popup),
                is_cancelled=cancel_event.is_set,
                cancelled_result=None,
            )
        finally:
            popup.hide()
            popup.destroy()

    @staticmethod
    def _update_progress(popup: ProgressPopup, current: int, total: int, status: object) -> None:
        if status:
            popup.set_status_text(str(status))
        if total and total > 0:
            popup.set_progress(max(0.0, min(1.0, current / total)))

    def _write_results(
        self, results: list[MeshCutoutResult], stage, target: ConversionTarget
    ) -> list[MeshCutoutResult]:
        """Write the geometry of every converted mesh.

        Captures get one file per mesh; a replacement gets one copy of its file holding every converted mesh.

        Args:
            results: Worker results.
            stage: Project stage, used for the stage metadata and the material to copy.
            target: Target the results belong to.

        Returns:
            Results with their output path set, or a skip reason when the file could not be written.
        """
        if target.is_replacement:
            return self._write_replacement(results, target)
        written = []
        output_folder = self.output_folder
        for result in results:
            if result.cut_mesh is None:
                written.append(result)
                continue
            try:
                path = write_cutout_mesh(
                    output_folder, result.source, result.cut_mesh, stage, self._settings.disable_alpha_test
                )
            except (OSError, RuntimeError, ValueError) as error:
                carb.log_warn(f"[lightspeed.trex.alpha_cutout.widget] {result.source.prim_path}: {error}")
                written.append(result.with_skip_reason(f"The file could not be written: {error}"))
                continue
            written.append(result.with_output_path(path))
        return written

    def _write_replacement(self, results: list[MeshCutoutResult], target: ConversionTarget) -> list[MeshCutoutResult]:
        converted = [
            (result.source.file_prim_path, result.cut_mesh)
            for result in results
            if result.cut_mesh is not None and result.source.file_prim_path
        ]
        if not converted:
            return results
        try:
            path = write_cutout_replacement(
                target.original_file, target.output_file, converted, self._settings.disable_alpha_test
            )
        except (OSError, RuntimeError, ValueError) as error:
            carb.log_warn(f"[lightspeed.trex.alpha_cutout.widget] {target.original_file}: {error}")
            return [
                result.with_skip_reason(f"The file could not be written: {error}")
                if result.cut_mesh is not None
                else result
                for result in results
            ]
        return [result.with_output_path(path) if result.cut_mesh is not None else result for result in results]

    def _show_results(self, results: list[MeshCutoutResult], outcomes: list[StageEditOutcome]):
        outcome_by_path = {outcome.prim_path: outcome for outcome in outcomes}
        lines = []
        converted = 0
        target = self._target
        for result in results:
            name = (
                self._mesh_label_text(target, result.source.prim_path)
                if target and target.is_replacement
                else result.source.prim_path.rsplit("/", 1)[-1]
            )
            outcome = outcome_by_path.get(result.source.prim_path)
            if result.skip_reason:
                lines.append(f"{name}: skipped. {result.skip_reason}")
                continue
            if outcome and outcome.skip_reason:
                lines.append(f"{name}: written but not referenced. {outcome.skip_reason}")
                continue
            converted += 1
            line = (
                f"{name}: {result.input_triangle_count} to {result.output_triangle_count} triangles, "
                f"{result.removed_uv_area_percent:.1f}% of the texture area removed."
            )
            if result.source.time_sampled:
                line += " Converted from the first time sample."
            if outcome and not outcome.reference_added:
                line += " The existing cutout file was overwritten."
            elif outcome and result.source.ref_prim_path:
                line += " The reference now points at the cutout file."
            lines.append(line)
        self._result_lines = lines
        self._rebuild_results()
        if converted < len(results):
            TrexMessageDialog(
                f"{converted} of {len(results)} meshes were converted. See the results for details.",
                "Alpha Cards Converted",
                disable_cancel_button=True,
            )
