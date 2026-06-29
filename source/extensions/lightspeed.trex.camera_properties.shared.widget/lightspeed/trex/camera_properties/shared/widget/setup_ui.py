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

import omni.ui as ui
import omni.usd
from lightspeed.trex.project_settings.core import (
    CAMERA_CLIPPING_OVERRIDE_PATH as _CAMERA_CLIPPING_OVERRIDE_PATH,
)
from lightspeed.trex.project_settings.core import (
    CameraClippingOverride as _CameraClippingOverride,
)
from lightspeed.trex.project_settings.core import (
    get_camera_clipping_override as _get_camera_clipping_override,
)
from lightspeed.trex.project_settings.core import (
    set_camera_clipping_override as _set_camera_clipping_override,
)
from omni.flux.properties_pane.properties.usd.widget import PropertyWidget as _PropertyWidget
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.collapsable_frame import PropertyCollapsableFrame as _PropertyCollapsableFrame
from pxr import Sdf, Tf, Usd, UsdGeom

# Pre-constructed once at module load. The widget's settings-prim listener
# fires on every Usd.Notice.ObjectsChanged on the stage, so re-allocating
# an Sdf.Path here on every notice would be wasted work.
_OVERRIDE_SDF_PATH = Sdf.Path(_CAMERA_CLIPPING_OVERRIDE_PATH)

_OVERRIDE_TOGGLE_TOOLTIP = (
    "When enabled, applies the Near / Far clipping range\n"
    "below to every camera in the project.\n"
    "\n"
    "Persists across project saves."
)
_OVERRIDE_RANGE_LABEL_TOOLTIP = (
    "Project-wide clipping range applied to every\n"
    "camera in the project. See the Near and Far\n"
    "field tooltips for details."
)
_OVERRIDE_NEAR_TOOLTIP = (
    "Near clipping plane distance for all cameras.\n"
    "\n"
    "Geometry closer than this is not rendered.\n"
    "\n"
    "Must be greater than 0.0001."
)
_OVERRIDE_FAR_TOOLTIP = (
    "Far clipping plane distance for all cameras.\n"
    "\n"
    "Note: the path-traced renderer (HdRemix) does\n"
    "not visibly enforce the far plane. This value is\n"
    "stored for schema correctness and forward\n"
    "compatibility with renderers that do."
)

# Display-name overrides for UsdGeomCamera attributes. UsdGeomCamera's schema
# ships without displayName metadata, so the property widget falls back to the
# raw token (e.g., "clippingRange"). Curating a lookup_table matches the
# convention used in the mesh properties pane and gives the panel proper
# title-case labels.
_CAMERA_LOOKUP_TABLE = {
    "clippingRange": {"name": "Clipping Range"},
    "clippingPlanes": {"name": "Clipping Planes"},
    "exposure": {"name": "Exposure"},
    "focalLength": {"name": "Focal Length"},
    "focusDistance": {"name": "Focus Distance"},
    "fStop": {"name": "F-Stop"},
    "horizontalAperture": {"name": "Horizontal Aperture"},
    "horizontalApertureOffset": {"name": "Horizontal Aperture Offset"},
    "verticalAperture": {"name": "Vertical Aperture"},
    "verticalApertureOffset": {"name": "Vertical Aperture Offset"},
    "projection": {"name": "Projection"},
    "purpose": {"name": "Purpose"},
    "shutter:close": {"name": "Shutter Close"},
    "shutter:open": {"name": "Shutter Open"},
    "stereoRole": {"name": "Stereo Role"},
    "proxyPrim": {"name": "Proxy Prim"},
    "visibility": {"name": "Visibility"},
    "xformOpOrder": {"name": "Transform Op Order"},
    "omni:kit:centerOfInterest": {"name": "Center of Interest"},
}


class SetupUI:
    def __init__(self, context_name: str):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {
            "_frame_none": None,
            "_frame_mesh_prim": None,
            "_properties_frames": None,
            "_property_widget": None,
            "_override_enabled_checkbox": None,
            "_override_near_field": None,
            "_override_far_field": None,
            "_override_active_indicator": None,
            "_clip_range_row_bg": None,
            "_override_enabled_sub": None,
            "_override_near_sub": None,
            "_override_far_sub": None,
            "_updating_override_ui": False,
            "_current_camera_path": None,
            "_settings_notice_listener": None,
            "_settings_listener_stage": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        self._properties_frames = {}
        self.__create_ui()

    def __create_ui(self):
        with ui.ZStack():
            self._frame_none = ui.Frame(visible=True)
            self._properties_frames[None] = self._frame_none
            with self._frame_none:
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                        ui.Spacer(height=0)
                        with ui.VStack(width=0):
                            ui.Spacer()
                            ui.Label("None", name="PropertiesWidgetLabel")
                            ui.Spacer()
                        ui.Spacer(height=0)
            self._frame_mesh_prim = ui.Frame(visible=False)
            self._properties_frames[UsdGeom.Camera] = self._frame_mesh_prim
            with self._frame_mesh_prim:
                with ui.VStack(spacing=8):
                    self.__build_project_override_section()
                    self.__build_attributes_section()

    def __build_project_override_section(self) -> None:
        """Inline UI for the project-wide camera clipping override.

        The toggle and numeric fields edit `/ProjectSettings/Viewport/CameraClippingOverride`
        via `lightspeed.trex.project_settings.core`. The
        `lightspeed.event.camera_clip_range_override` event observes those
        changes and re-applies the override to all cameras on the session layer.
        """
        with _PropertyCollapsableFrame("PROJECT OVERRIDE", collapsed=False):
            with ui.VStack(spacing=4):
                ui.Spacer(height=ui.Pixel(4))
                # Toggle row. Wrapping each child in VStack-with-spacers
                # forces a uniform V-center: CheckBox, Circle, and Label
                # have different default vertical alignments that don't
                # agree otherwise.
                with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(4)):
                    ui.Spacer(width=ui.Pixel(4), height=0)
                    with ui.VStack(width=ui.Pixel(20)):
                        ui.Spacer()
                        self._override_enabled_checkbox = ui.CheckBox(
                            width=ui.Pixel(16),
                            height=ui.Pixel(16),
                            tooltip=_OVERRIDE_TOGGLE_TOOLTIP,
                        )
                        ui.Spacer()
                    # Gold dot visible only when the project override is on.
                    # Distinct from the property tree's blue OverrideIndicator,
                    # which marks per-attribute authoring. 12 px matches the
                    # property-tree indicator dot diameter.
                    with ui.VStack(width=ui.Pixel(16)):
                        ui.Spacer()
                        self._override_active_indicator = ui.Circle(
                            width=ui.Pixel(12),
                            height=ui.Pixel(12),
                            style_type_name_override="ProjectOverrideActiveIndicator",
                            visible=False,
                            tooltip="Project clipping override is active for all cameras.",
                        )
                        ui.Spacer()
                    ui.Spacer(width=ui.Pixel(4), height=0)
                    with ui.VStack():
                        ui.Spacer()
                        ui.Label(
                            "Override across project (applies to all cameras)",
                            name="PropertiesWidgetLabel",
                            height=ui.Pixel(16),
                            tooltip=_OVERRIDE_TOGGLE_TOOLTIP,
                        )
                        ui.Spacer()
                # Clipping Range row mirrors the property tree's row directly
                # below: same column fractions, same right-aligned label,
                # ui.FloatDrag values for matching styling. The outer
                # ui.Frame anchors the ZStack to the parent's width so the
                # hover Rectangle spans the full row (a bare ZStack sizes
                # itself to its content instead).
                with ui.Frame(height=ui.Pixel(24)):
                    with ui.ZStack(mouse_hovered_fn=self.__on_clip_range_row_hovered):
                        self._clip_range_row_bg = ui.Rectangle(
                            style_type_name_override="OverrideBackground",
                            visible=False,
                        )
                        with ui.HStack(spacing=ui.Pixel(8)):
                            ui.Label(
                                "Clipping Range",
                                width=ui.Fraction(0.4),
                                alignment=ui.Alignment.LEFT_CENTER,
                                name="PropertiesWidgetLabel",
                                tooltip=_OVERRIDE_RANGE_LABEL_TOOLTIP,
                            )
                            with ui.HStack(width=ui.Fraction(0.6), spacing=ui.Pixel(8)):
                                # 2 px VStack spacers around each FloatDrag
                                # match the property tree's drag-widget
                                # layout, leaving room above/below the field
                                # for the row hover background to fill so the
                                # field blends with the band.
                                with ui.VStack():
                                    ui.Spacer(height=ui.Pixel(2))
                                    # min=0.0001 is a UI hint; the
                                    # authoritative clamp lives in
                                    # CameraClippingOverride.__post_init__.
                                    # No min on far because the real
                                    # constraint is far > near, enforced in
                                    # the dataclass.
                                    self._override_near_field = ui.FloatDrag(
                                        min=0.0001,
                                        style_type_name_override="ProjectOverrideValueField",
                                        tooltip=_OVERRIDE_NEAR_TOOLTIP,
                                    )
                                    ui.Spacer(height=ui.Pixel(2))
                                with ui.VStack():
                                    ui.Spacer(height=ui.Pixel(2))
                                    self._override_far_field = ui.FloatDrag(
                                        style_type_name_override="ProjectOverrideValueField",
                                        tooltip=_OVERRIDE_FAR_TOOLTIP,
                                    )
                                    ui.Spacer(height=ui.Pixel(2))
                ui.Spacer(height=ui.Pixel(4))

        self._override_enabled_sub = self._override_enabled_checkbox.model.subscribe_value_changed_fn(
            self.__on_override_enabled_changed
        )
        self._override_near_sub = self._override_near_field.model.subscribe_value_changed_fn(
            self.__on_override_value_changed
        )
        self._override_far_sub = self._override_far_field.model.subscribe_value_changed_fn(
            self.__on_override_value_changed
        )
        self.__refresh_override_ui()

    def __build_attributes_section(self) -> None:
        """Themed wrapper around the generic USD property widget.

        Puts the camera's USD attributes in a sibling collapsible section
        so the PROJECT OVERRIDE section reads as a distinct subsection of
        the parent CAMERA PROPERTIES pane.
        """
        with _PropertyCollapsableFrame("ATTRIBUTES", collapsed=False):
            self._property_widget = _PropertyWidget(
                self._context_name,
                lookup_table=_CAMERA_LOOKUP_TABLE,
                tree_column_widths=[ui.Fraction(0.4), ui.Fraction(0.6)],
                right_aligned_labels=False,
            )

    def __on_clip_range_row_hovered(self, hovered: bool):
        # Mirror the property-tree hover treatment: toggle between
        # OverrideBackground (idle) and OverrideBackgroundHovered styles,
        # and only show the background while hovering so the idle row
        # blends with the panel.
        if self._clip_range_row_bg is None:
            return
        self._clip_range_row_bg.visible = hovered
        self._clip_range_row_bg.style_type_name_override = (
            "OverrideBackgroundHovered" if hovered else "OverrideBackground"
        )

    def __refresh_override_ui(self):
        stage = self._context.get_stage()
        if not stage or self._override_enabled_checkbox is None:
            return
        override = _get_camera_clipping_override(stage)
        self._updating_override_ui = True
        try:
            self._override_enabled_checkbox.model.set_value(override.enabled)
            self._override_near_field.model.set_value(override.near_clip)
            self._override_far_field.model.set_value(override.far_clip)
            if self._override_active_indicator is not None:
                self._override_active_indicator.visible = override.enabled
        finally:
            self._updating_override_ui = False

    def __on_override_enabled_changed(self, model):
        """Toggle changed: always refresh the camera property widget because
        the enabled-state transition changes which layer wins compositionally.
        """
        if self._updating_override_ui:
            return
        self.__write_override()
        if self._override_active_indicator is not None:
            self._override_active_indicator.visible = model.get_value_as_bool()
        if self._current_camera_path and self._property_widget:
            self._property_widget.refresh([self._current_camera_path])

    def __on_override_value_changed(self, model):
        """Near/Far field changed: only refresh the camera property widget
        if the override is currently enabled. When disabled, changing the
        override's near/far values just updates the Settings prim's stored
        values for future use — it must not affect any camera's effective
        clippingRange display.
        """
        if self._updating_override_ui:
            return
        self.__write_override()
        if not self._override_enabled_checkbox.model.get_value_as_bool():
            return
        if self._current_camera_path and self._property_widget:
            self._property_widget.refresh([self._current_camera_path])

    def __write_override(self):
        stage = self._context.get_stage()
        if not stage:
            return
        override = _CameraClippingOverride(
            enabled=bool(self._override_enabled_checkbox.model.get_value_as_bool()),
            near_clip=float(self._override_near_field.model.get_value_as_float()),
            far_clip=float(self._override_far_field.model.get_value_as_float()),
        )
        # Raise the guard before authoring: _set_camera_clipping_override
        # synchronously fires Usd.Notice.ObjectsChanged, which lands in
        # __on_external_settings_changed inside this call stack. Without
        # the guard, the notice handler would round-trip stage->UI on every
        # keystroke. The same flag also short-circuits the model-change
        # callbacks during the clamp-back below.
        self._updating_override_ui = True
        try:
            _set_camera_clipping_override(stage, override)
            # CameraClippingOverride.__post_init__ may have clamped near/far to
            # enforce near >= _MIN_NEAR_CLIP and far > near. Push the corrected
            # values back into the UI fields so the user sees what was actually
            # written. Only set values that actually changed so we don't fight
            # the user mid-edit when no clamping happened.
            if abs(override.near_clip - self._override_near_field.model.get_value_as_float()) > 1e-7:
                self._override_near_field.model.set_value(override.near_clip)
            if abs(override.far_clip - self._override_far_field.model.get_value_as_float()) > 1e-7:
                self._override_far_field.model.set_value(override.far_clip)
        finally:
            self._updating_override_ui = False

    def refresh(self, path: str):
        stage = self._context.get_stage()
        if not stage:
            return
        # Track the camera path so we can re-refresh the embedded PropertyWidget
        # when the override toggle is changed (see __on_override_value_changed).
        self._current_camera_path = path
        # Refresh the override UI on every refresh so it reflects the project's latest values
        # (e.g., if the user is editing the Settings prim externally or via the Stage Manager).
        self.__refresh_override_ui()
        # Keep the override UI in sync with external Settings-prim edits
        # (Python console, Stage Manager, future REST endpoints) by listening
        # for ObjectsChanged notices on whichever stage we're showing.
        self.__ensure_settings_listener(stage)
        found = False
        prim = stage.GetPrimAtPath(path)
        if not prim.IsValid():
            return
        for item_type, frame in self._properties_frames.items():
            if item_type is None:
                self._properties_frames[None].visible = False
                continue
            value = prim.IsA(item_type)
            frame.visible = value
            if value:
                found = True
        if not found:
            self._properties_frames[None].visible = True
        else:
            self._property_widget.show(True)

            self._property_widget.refresh([path])

    def show(self, value):
        self._property_widget.show(value)

    def __ensure_settings_listener(self, stage: Usd.Stage) -> None:
        """Register a Usd.Notice.ObjectsChanged listener bound to the given
        stage so external edits to the Settings prim (Python console,
        Stage Manager, etc.) propagate back into the override UI fields.
        Re-registers if the stage has changed since the last call.
        """
        if self._settings_listener_stage is stage and self._settings_notice_listener is not None:
            return
        self.__teardown_settings_listener()
        self._settings_notice_listener = Tf.Notice.Register(
            Usd.Notice.ObjectsChanged,
            self.__on_external_settings_changed,
            stage,
        )
        self._settings_listener_stage = stage

    def __teardown_settings_listener(self) -> None:
        if self._settings_notice_listener is not None:
            self._settings_notice_listener.Revoke()
            self._settings_notice_listener = None
        self._settings_listener_stage = None

    def __on_external_settings_changed(self, notice, stage):
        # Skip notices fired by our own __write_override: the UI fields are
        # already the source of truth, and the clamp-back step below will
        # push any post-init corrections back in. Without this guard, every
        # keystroke triggers a redundant stage-read round-trip.
        if self._updating_override_ui:
            return
        if stage is not self._settings_listener_stage:
            return
        for path_list_getter in (notice.GetChangedInfoOnlyPaths, notice.GetResyncedPaths):
            for path in path_list_getter():
                if path.HasPrefix(_OVERRIDE_SDF_PATH):
                    self.__refresh_override_ui()
                    return

    def destroy(self):
        self.__teardown_settings_listener()
        _reset_default_attrs(self)
