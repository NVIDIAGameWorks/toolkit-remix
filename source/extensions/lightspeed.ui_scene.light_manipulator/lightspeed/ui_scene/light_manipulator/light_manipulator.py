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

from __future__ import annotations

__all__ = [
    "AbstractLightManipulator",
    "CylinderLightManipulator",
    "DiskLightManipulator",
    "DistantLightManipulator",
    "RectLightManipulator",
    "SphereLightManipulator",
    "compute_luminance",
    "compute_threshold_distance",
]

import abc
import math
from contextlib import suppress
from typing import TYPE_CHECKING

import carb.input
import omni.appwindow
import omni.kit
import omni.kit.commands
from omni.flux.utils.common.interactive_usd_notices import is_any_interaction_active as _is_any_interaction_active
from omni.flux.utils.common.interactive_usd_notices import (
    register_interaction_end_listener as _register_interaction_end_listener,
)
from omni.ui import color as cl
from omni.ui import scene as sc
from pxr import Usd, UsdGeom, UsdLux

from .constants import (
    ARROW_P,
    ARROW_TIP,
    ARROW_VC,
    ARROW_VI,
    CLEAR_COLOR,
    COLOR,
    CONE_INNER_COLOR_DEFAULT,
    CONE_LENGTH_MAX,
    CONE_LENGTH_MIN,
    CONE_OUTER_COLOR_DEFAULT,
    CONE_SIDES_DEFAULT,
    CONE_SIDES_MIN_INPUT,
    CONE_THRESHOLD_DEFAULT,
    CONE_THRESHOLD_MIN,
    CYLINDER_LIGHT_INTENSITY,
    DEFAULT_ARC_STYLE,
    DEFAULT_SHAPE_STYLE,
    DISK_LIGHT_INTENSITY,
    DISTANT_LIGHT_INTENSITY,
    HOVER_COLOR,
    HOVER_THICKNESS,
    INTENSITY_MIN,
    INTENSITY_SCALE,
    RECT_LIGHT_INTENSITY,
    SPHERE_LIGHT_INTENSITY,
    SQUARE_CENTER_TO_EDGE,
    THICKNESS,
)
from .gesture import LightDragGesture
from .light_model import (
    AbstractLightModel,
    CylinderLightModel,
    DiskLightModel,
    DistantLightModel,
    RectLightModel,
    SphereLightModel,
    UsdLuxLight,
)

if TYPE_CHECKING:
    from lightspeed.trex.viewports.shared.widget.layers import ViewportLayers

ConcreteLightManipulatorCls: (
    RectLightManipulator
    | DiskLightManipulator
    | DistantLightManipulator
    | SphereLightManipulator
    | CylinderLightManipulator
) = None

_manipulator_classes: dict[UsdLuxLight, ConcreteLightManipulatorCls] | None = None


def is_mouse_button_down(button=carb.input.MouseInput.LEFT_BUTTON) -> bool:
    iinput = carb.input.acquire_input_interface()
    app_window = omni.appwindow.get_default_app_window()
    mouse = app_window.get_mouse()
    return iinput.get_mouse_value(mouse, button)


def set_thickness(shapes: list[sc.AbstractShape], thickness: float):
    for shape in shapes:
        if isinstance(shape, sc.PolygonMesh):
            shape.thicknesses = [thickness] * len(shape.positions)
        else:
            # line, rectangle, etc.
            shape.thickness = thickness


def set_visible(shapes: list[sc.AbstractShape], visible: bool):
    for shape in shapes:
        shape.visible = visible


def set_color(shapes: list[sc.AbstractShape], color: cl):
    for shape in shapes:
        if isinstance(shape, sc.PolygonMesh):
            shape.colors = [color] * len(shape.vertex_indices)
        else:
            shape.color = color


def make_arrow_point(translate: tuple[float, float, float], color, reverse=True):
    vert_count = len(ARROW_VI)
    y_rotation = -180 if reverse else 0
    with sc.Transform(
        transform=sc.Matrix44.get_translation_matrix(translate[0], translate[1], translate[2])
        * sc.Matrix44.get_rotation_matrix(0, y_rotation, 0, True)
    ):
        return sc.PolygonMesh(ARROW_P, [color] * vert_count, ARROW_VC, ARROW_VI, visible=False)


def make_square(translate, width=0.06):
    with sc.Transform(transform=sc.Matrix44.get_translation_matrix(translate[0], translate[1], translate[2])):
        # XXX: in order to get hover event, rect needs to be "visible" even if alpha is 0
        return sc.Rectangle(width, width, color=CLEAR_COLOR, visible=True)


# Rec.709 / sRGB linear-to-luminance projection coefficients (CIE / ITU-R BT.709).
_REC709_R, _REC709_G, _REC709_B = 0.2126, 0.7152, 0.0722


def _read_float_attr(attr: Usd.Attribute | None, time: Usd.TimeCode, default: float) -> float:
    if not attr:
        return default
    try:
        value = attr.Get(time)
    except Exception:  # noqa: BLE001 - USD attribute reads can fail on stale/invalid prims.
        return default
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_bool_attr(attr: Usd.Attribute | None, time: Usd.TimeCode, default: bool) -> bool:
    if not attr:
        return default
    try:
        value = attr.Get(time)
    except Exception:  # noqa: BLE001 - USD attribute reads can fail on stale/invalid prims.
        return default
    if value is None:
        return default
    return bool(value)


def _read_color_attr(attr: Usd.Attribute | None, time: Usd.TimeCode) -> tuple[float, float, float]:
    if not attr:
        return 1.0, 1.0, 1.0
    try:
        value = attr.Get(time)
    except Exception:  # noqa: BLE001 - USD attribute reads can fail on stale/invalid prims.
        return 1.0, 1.0, 1.0
    if value is None:
        return 1.0, 1.0, 1.0
    try:
        return float(value[0]), float(value[1]), float(value[2])
    except (IndexError, TypeError, ValueError):
        return 1.0, 1.0, 1.0


def compute_luminance(model: AbstractLightModel | None) -> float:
    """Compute a proportional luminance-like brightness factor.

    Assumes `inputs:color` is authored in linear sRGB / Rec.709 primaries. Applies
    Rec.709 luminosity weights to `color * temperature`, then multiplies by
    `intensity * 2^exposure`. The result is not an absolute cd/m2 value; it is
    meaningful only relative to the cone threshold used by `compute_threshold_distance`.
    Returns 0.0 when the light is unselected or unreadable.
    """
    if not model:
        return 0.0
    light = model.light
    if light is None:
        return 0.0
    time = model.time

    intensity = _read_float_attr(light.GetIntensityAttr(), time, 0.0)
    exposure = _read_float_attr(light.GetExposureAttr(), time, 0.0)
    cr, cg, cb = _read_color_attr(light.GetColorAttr(), time)
    enable_temp = _read_bool_attr(light.GetEnableColorTemperatureAttr(), time, False)
    if enable_temp:
        temp_k = _read_float_attr(light.GetColorTemperatureAttr(), time, 6500.0)
        # `BlackbodyTemperatureAsRgb` returns a unit-Y normalized linear-RGB triple — same
        # convention Remix uses on the C++ side.
        temp_rgb = UsdLux.BlackbodyTemperatureAsRgb(temp_k)
        cr *= float(temp_rgb[0])
        cg *= float(temp_rgb[1])
        cb *= float(temp_rgb[2])

    brightness = _REC709_R * cr + _REC709_G * cg + _REC709_B * cb
    return max(0.0, brightness * intensity * (2.0**exposure))


def compute_threshold_distance(
    light_class: type[UsdLux.BoundableLightBase] | type[UsdLux.NonboundableLightBase],
    radius: float,
    luminance: float,
    threshold_lux: float,
) -> float:
    """Distance at which the light's on-axis illuminance falls below `threshold_lux`.

    Closed-form: `d = R · sqrt(π·L/T)` for SphereLight, `d = R · sqrt(max(0, π·L/T − 1))`
    for DiskLight on-axis. `L` is the proportional brightness factor from `compute_luminance`.
    Returns 0.0 for unsupported light classes or non-positive inputs.
    """
    if luminance <= 0.0 or threshold_lux <= 0.0 or radius <= 0.0:
        return 0.0
    ratio = math.pi * luminance / threshold_lux
    if light_class is UsdLux.SphereLight:
        return radius * math.sqrt(ratio)
    if light_class is UsdLux.DiskLight:
        return radius * math.sqrt(max(0.0, ratio - 1.0))
    return 0.0


def get_manipulator_class(light: Usd.Prim) -> type[ConcreteLightManipulatorCls] | None:
    global _manipulator_classes
    if _manipulator_classes is None:
        _manipulator_classes = {}
        for cls in (
            RectLightManipulator,
            DiskLightManipulator,
            DistantLightManipulator,
            SphereLightManipulator,
            CylinderLightManipulator,
        ):
            _manipulator_classes[cls.light_class] = cls

    for light_class, cls in _manipulator_classes.items():
        if light.IsA(light_class):
            return cls
    return None


class _HoverArrows:
    """
    Arrows that can appear when a user hovers over them.

    Example Usage:
        >>> hover_arrows = _HoverArrows()
        >>> hover_arrows.define((0, 0, 0), (1, 1, 1))
        >>> hover_arrows.define((0, 0, 0), (1, 1, -1))
        >>> # the hover gesture should trigger self.show / self.hide
        >>> hover_arrows.shapes[0].gestures = [custom_gesture, hover_gesture]
    """

    def __init__(self):
        self.arrow_shafts_group: list[sc.Line] = []
        self.arrows_group: list[sc.PolygonMesh] = []

    def define(self, point1, point2):
        # TODO: So far this assumes z direction
        px, py, pz = point1
        p2x, p2y, p2z = point2
        reverse = pz > p2z
        if reverse:
            shaft = sc.Line((px, py, pz), (p2x, p2y, p2z - ARROW_TIP), **DEFAULT_SHAPE_STYLE)
        else:
            shaft = sc.Line((px, py, pz - ARROW_TIP), (p2x, p2y, p2z), **DEFAULT_SHAPE_STYLE)
        arrow_point = make_arrow_point((p2x, p2y, p2z), COLOR, reverse=reverse)
        self.arrow_shafts_group.append(shaft)
        self.arrows_group.append(arrow_point)
        return shaft

    @property
    def shapes(self):
        """The arrow shape objects that should receive gestures"""
        # Note: Using lines only because attaching gestures to arrow meshes was problematic for two reasons:
        #   - on_ended_fn was not always called.
        #   - multiple intensity gestures were triggered at one time
        return self.arrow_shafts_group

    def show(self):
        set_thickness(self.arrow_shafts_group, HOVER_THICKNESS)
        set_color(self.arrows_group, HOVER_COLOR)
        set_visible(self.arrows_group, True)

    def hide(self):
        # the hover might end while we are in middle of a drag, but we want to stay highlighted so
        # that the user is not confused about whether they are still holding handle.
        if is_mouse_button_down():
            return
        set_thickness(self.arrow_shafts_group, THICKNESS)
        set_color(self.arrows_group, COLOR)
        set_visible(self.arrows_group, False)


class AbstractLightManipulator(sc.Manipulator):
    """Base class for light manipulators"""

    light_class = None
    model_class = None

    # An intensity scale per light type since they can have such a different effect on a scene.
    # Per-light divisor = that light type's default intensity / INTENSITY_SCALE.
    # The eventual result is: length = (i * INTENSITY_SCALE) / (default intensity)
    # Subclasses override; `intensity_scale` property below applies threshold scaling on spotlights.
    _base_intensity_scale = 500 / INTENSITY_SCALE

    supports_spotlight_cone = False

    def __init__(self, viewport_layers, **kwargs):
        super().__init__(**kwargs)
        self._viewport_layers = viewport_layers
        self.__root_xf = sc.Transform()
        self._x_xform = sc.Transform()
        self._shape_xform = sc.Transform()
        self._is_dragging = False
        self._shaping_authored_cache: bool | None = None
        self._cone_xform: sc.Transform | None = None
        self._cone_visible = True
        self._cone_threshold = CONE_THRESHOLD_DEFAULT
        self._cone_sides = CONE_SIDES_DEFAULT
        self._cone_outer_color: tuple[float, float, float] = CONE_OUTER_COLOR_DEFAULT
        self._cone_inner_color: tuple[float, float, float] = CONE_INNER_COLOR_DEFAULT
        self._cone_refresh_deferred = False
        self._interaction_end_subscription = None

    def __del__(self):
        with suppress(Exception):
            self.destroy()

    def destroy(self) -> None:
        self._revoke_interaction_end_subscription()
        self._cone_refresh_deferred = False
        self._cone_xform = None
        self._shaping_authored_cache = None

    def _revoke_interaction_end_subscription(self):
        if self._interaction_end_subscription is None:
            return
        self._interaction_end_subscription.revoke()
        self._interaction_end_subscription = None

    @property
    def cone_visible(self) -> bool:
        return self._cone_visible

    @cone_visible.setter
    def cone_visible(self, value: bool):
        value = bool(value)
        if self._cone_visible == value:
            return
        self._cone_visible = value
        if self.supports_spotlight_cone:
            self.invalidate()

    @property
    def cone_threshold(self) -> float:
        return self._cone_threshold

    @cone_threshold.setter
    def cone_threshold(self, value: float):
        value = max(CONE_THRESHOLD_MIN, float(value))
        if self._cone_threshold == value:
            return
        self._cone_threshold = value
        if self.supports_spotlight_cone:
            self.invalidate()

    @property
    def cone_sides(self) -> int:
        return self._cone_sides

    @cone_sides.setter
    def cone_sides(self, value: int):
        value = max(CONE_SIDES_MIN_INPUT, int(value))
        if self._cone_sides == value:
            return
        self._cone_sides = value
        if self.supports_spotlight_cone:
            self.invalidate()

    @property
    def cone_outer_color(self) -> tuple[float, float, float]:
        return self._cone_outer_color

    @cone_outer_color.setter
    def cone_outer_color(self, value: tuple[float, float, float]):
        value = tuple(float(c) for c in value)
        if len(value) != 3:
            raise ValueError(f"cone_outer_color requires exactly 3 components, got {len(value)}")
        if self._cone_outer_color == value:
            return
        self._cone_outer_color = value
        if self.supports_spotlight_cone:
            self.invalidate()

    @property
    def cone_inner_color(self) -> tuple[float, float, float]:
        return self._cone_inner_color

    @cone_inner_color.setter
    def cone_inner_color(self, value: tuple[float, float, float]):
        value = tuple(float(c) for c in value)
        if len(value) != 3:
            raise ValueError(f"cone_inner_color requires exactly 3 components, got {len(value)}")
        if self._cone_inner_color == value:
            return
        self._cone_inner_color = value
        if self.supports_spotlight_cone:
            self.invalidate()

    @property
    def viewport_layers(self) -> ViewportLayers:
        return self._viewport_layers

    @property
    def xform(self) -> sc.Transform:
        return self._x_xform

    @property
    def shape_xform(self) -> sc.Transform:
        return self._shape_xform

    @property
    def show_intensity_controls(self) -> bool:
        viewport_layer = getattr(self.model, "_viewport_layer", None)
        if viewport_layer is None:
            return True
        return viewport_layer.intensity_controls_visible

    def _build_minimal_intensity_xform(self) -> list | None:
        return None

    def _minimal_intensity_indicator_length(self) -> float:
        return 1.0

    def build_minimal_intensity_xform(self):
        if not self.model:
            return
        xform = self._build_minimal_intensity_xform()
        if xform:
            self._minimal_intensity_xform.transform = xform

    def _build_single_intensity_arrow(
        self,
        point1: tuple[float, float, float],
        point2: tuple[float, float, float],
        attr_map: dict[int, str | None],
        directions: list[int],
        multipliers: list[int],
        persistent_head: bool = False,
        interactive: bool = True,
    ):
        hover_arrows = _HoverArrows()
        arrow = hover_arrows.define(point1, point2)
        if persistent_head:
            arrow_head = hover_arrows.arrows_group[-1]
            arrow_head.visible = True
        if not interactive:
            return
        if persistent_head:

            def reset_arrow_appearance():
                if is_mouse_button_down():
                    return
                set_thickness([arrow], THICKNESS)
                set_color([arrow_head], COLOR)

            hover_gesture = sc.HoverGesture(
                on_began_fn=lambda _sender: (
                    set_thickness([arrow], HOVER_THICKNESS),
                    set_color([arrow_head], HOVER_COLOR),
                ),
                on_ended_fn=lambda _sender: reset_arrow_appearance(),
            )
        else:
            hover_gesture = sc.HoverGesture(
                on_began_fn=lambda _sender: hover_arrows.show(),
                on_ended_fn=lambda _sender: hover_arrows.hide(),
            )
        arrow.gestures = [
            LightDragGesture(self, directions, multipliers, attr_map, on_ended_fn=hover_arrows.hide),
            hover_gesture,
        ]

    @abc.abstractmethod
    def _build_shape_xform(self):
        raise NotImplementedError()

    def build_shape_xform(self):
        if not self.model:
            return
        xform = self._build_shape_xform()
        if xform:
            self._shape_xform.transform = xform

    @abc.abstractmethod
    def _build_manipulator_geometry(self):
        raise NotImplementedError()

    def _build_cone_xform(self) -> list | None:
        """Identity transform — frustum geometry is emitted in stage units directly by
        `_build_cone_geometry`, so no additional scale is applied here.

        Kept so the `cone_xform` scene-graph anchor and the `build_cone_xform()` call
        chain still exist — subclasses can override to apply uniform hover-feedback or
        animation scale on the cone without rebuilding geometry.
        """
        return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

    def _get_stage_meters_per_unit(self) -> float:
        """Look up meters_per_unit from the light's stage, with a Remix-default fallback.

        Falls back to 0.01 (Remix's cm-per-unit convention) when the stage or prim isn't
        reachable — e.g. during early manipulator construction or in minimal test contexts.
        """
        default = 0.01
        model = self.model
        if not model:
            return default
        light = model.light
        prim = light.GetPrim() if light else None
        if prim is None:
            return default
        stage = prim.GetStage()
        if stage is None:
            return default
        value = UsdGeom.GetStageMetersPerUnit(stage)
        return value if value else default

    def _get_source_radius(self) -> float:
        """Return the emitter's source radius in stage units.

        DiskLight and SphereLight expose a `radius` model item; for anything else (or a
        prim whose radius isn't authored), return 0.0 so the frustum collapses to the
        equivalent point-apex cone — a safe degenerate.
        """
        if not self.model:
            return 0.0
        radius_item = getattr(self.model, "radius", None)
        if radius_item is None:
            return 0.0
        try:
            return max(0.0, float(self.model.get_as_float(radius_item)))
        except (TypeError, ValueError):
            return 0.0

    def build_cone_xform(self):
        """Recompute `_cone_xform` from `_build_cone_xform`. Cheap — matrix-only update.

        `_cone_xform` is `None` until `_build_cone_geometry` runs for the first time;
        calls before then are no-ops."""
        if not self.model or self._cone_xform is None:
            return
        xform = self._build_cone_xform()
        if xform:
            self._cone_xform.transform = xform

    def _has_shaping_authored(self) -> bool:
        """True iff the model exposes a ShapingAPI cone angle in (0°, 90°) — a spotlight in the Remix sense."""
        if not self.model:
            return False
        cone_item = getattr(self.model, "cone_angle", None)
        if cone_item is None:
            return False
        cone_values = self.model.get_as_floats(cone_item)
        if not cone_values:
            return False
        angle_deg = float(cone_values[0])
        return 0.0 < angle_deg < 90.0

    def _needs_cone_geometry_rebuild(self) -> bool:
        return self.supports_spotlight_cone and (self._has_shaping_authored() or self._cone_xform is not None)

    def _defer_cone_geometry_rebuild(self):
        self._cone_refresh_deferred = True
        if self._interaction_end_subscription is None:
            self._interaction_end_subscription = _register_interaction_end_listener(self._on_interaction_finished)

    def _refresh_cone_geometry_when_safe(self):
        if not self._needs_cone_geometry_rebuild():
            return
        if _is_any_interaction_active():
            self._defer_cone_geometry_rebuild()
            return
        self.invalidate()

    def _on_interaction_finished(self, _stage: Usd.Stage):
        if not self._cone_refresh_deferred or _is_any_interaction_active():
            return
        self._cone_refresh_deferred = False
        self._revoke_interaction_end_subscription()
        if self._needs_cone_geometry_rebuild():
            self.invalidate()

    @property
    def intensity_scale(self) -> float:
        """Intensity-to-arrow-length divisor. Spotlight-capable manipulators with shaping authored
        scale this by √(T/T_default) so the arrow tracks the cone's threshold response. Kept linear
        in intensity so `LightDragGesture`'s z↔intensity inverse stays valid."""
        if self._shaping_authored_cache is None:
            has_shaping = self._has_shaping_authored()
        else:
            has_shaping = self._shaping_authored_cache
        if not (self.supports_spotlight_cone and has_shaping):
            return self._base_intensity_scale
        threshold = max(self._cone_threshold, CONE_THRESHOLD_MIN)
        return self._base_intensity_scale * math.sqrt(threshold / CONE_THRESHOLD_DEFAULT)

    def _compute_cone_length_units(self) -> float:
        """Cone-of-influence display length in stage units, or 0 when no cone should be drawn.

        The photometric distance is converted to meters, clamped to the visible display range,
        then converted back to stage units.
        """
        if not self._cone_visible or not self.supports_spotlight_cone or not self._has_shaping_authored():
            return 0.0
        meters_per_unit = self._get_stage_meters_per_unit()
        base_radius = self._get_source_radius()
        brightness = compute_luminance(self.model)
        distance_units = compute_threshold_distance(self.light_class, base_radius, brightness, self._cone_threshold)
        distance_meters = distance_units * meters_per_unit
        if distance_meters <= 0.0:
            return 0.0
        distance_meters = max(CONE_LENGTH_MIN, min(CONE_LENGTH_MAX, distance_meters))
        return distance_meters / meters_per_unit

    def _build_cone_geometry(self):
        """Draw a frustum along -Z from the light's source rim when shaping cone is authored < 90°.

        Emits an outer frustum and, when `shaping:cone:softness > 0`, an inner frustum sharing
        the same near rim with a narrower far rim.
        """
        self._cone_xform = None
        # `_compute_cone_length_units` is the single gate — returns 0 unless cone-visible,
        # spotlight-capable, shaping authored in (0°, 90°), and non-zero on-axis illuminance.
        length_units = self._compute_cone_length_units()
        if length_units <= 0.0:
            return
        # `shaping:cone:angle` is the half-angle measured off the primary axis; existence and
        # bounds were already validated by `_has_shaping_authored` inside the call above.
        angle_deg = float(self.model.get_as_floats(self.model.cone_angle)[0])
        outer_half = math.radians(angle_deg)
        eps = 1e-3
        outer_half = max(eps, min(math.pi / 2.0 - eps, outer_half))

        softness_item = getattr(self.model, "softness", None)
        softness = 0.0
        if softness_item is not None:
            softness_values = self.model.get_as_floats(softness_item)
            if softness_values:
                softness = max(0.0, min(1.0, float(softness_values[0])))
        # Remix's penumbra: softness is a cos-space delta added to the cone-angle cosine, so
        # the inner cone collapses to a point when `cos_outer + softness ≥ 1`.
        cos_outer = math.cos(outer_half)
        cos_inner = min(1.0, cos_outer + softness)
        inner_half = math.acos(cos_inner)

        base_radius = self._get_source_radius()

        outer_color = cl(*self._cone_outer_color, 1.0)
        inner_color = cl(*self._cone_inner_color, 1.0)
        outer_style = {"thickness": THICKNESS, "color": outer_color}
        outer_arc_style = {"thickness": THICKNESS, "color": outer_color, "wireframe": True, "sector": False}
        inner_style = {"thickness": THICKNESS, "color": inner_color}
        inner_arc_style = {"thickness": THICKNESS, "color": inner_color, "wireframe": True, "sector": False}

        self._cone_xform = sc.Transform()
        self.build_cone_xform()
        with self._cone_xform:
            if base_radius > 1e-6:
                sc.Arc(base_radius, axis=2, begin=-math.pi, end=math.pi, **outer_arc_style)
            self._draw_disk_source_frustum(
                outer_half, base_radius, length_units, self._cone_sides, outer_style, outer_arc_style
            )
            if softness > 0.0 and inner_half > eps:
                self._draw_disk_source_frustum(
                    inner_half, base_radius, length_units, self._cone_sides, inner_style, inner_arc_style
                )

    @staticmethod
    def _draw_disk_source_frustum(
        half_angle: float,
        base_radius: float,
        length_units: float,
        sides: int,
        line_style: dict[str, object],
        arc_style: dict[str, object],
    ) -> None:
        """Emit `sides` spokes and a far-rim arc. The near rim is drawn by the caller."""
        far_radius = base_radius + length_units * math.tan(half_angle)
        for i in range(sides):
            phi = (2.0 * math.pi) * (i / float(sides))
            cos_phi = math.cos(phi)
            sin_phi = math.sin(phi)
            near = (base_radius * cos_phi, base_radius * sin_phi, 0.0)
            far = (far_radius * cos_phi, far_radius * sin_phi, -length_units)
            sc.Line(near, far, **line_style)
        with sc.Transform(sc.Matrix44.get_translation_matrix(0.0, 0.0, -length_units)):
            sc.Arc(far_radius, axis=2, begin=-math.pi, end=math.pi, **arc_style)

    def _build(self):
        self._shape_xform = sc.Transform()
        self._minimal_intensity_xform = sc.Transform()
        # Build the shape's transform
        self.build_shape_xform()
        with self._shape_xform:
            self._build_manipulator_geometry()
        # Cone geometry lives at the `_x_xform` level (outside `_shape_xform`) so it does not
        # inherit the light's dimensional scaling. Cone-capable lights are proportional, so
        # `_x_xform` stays at 1.0 and the photometric length remains in stage units.
        self._build_cone_geometry()
        self.build_minimal_intensity_xform()
        with self._minimal_intensity_xform:
            self._build_minimal_intensity_geometry()

    def _build_minimal_intensity_geometry(self):
        return

    def on_build(self):
        """Called when the model is changed"""
        model = self.model
        if not model:
            return

        # if we don't have selection then just return
        prim_path_item = model.prim_path
        if not prim_path_item or not prim_path_item.value:
            return

        self.__root_xf = sc.Transform(model.get_as_floats(model.transform))
        with self.__root_xf:
            self._x_xform = sc.Transform(
                transform=sc.Matrix44.get_scale_matrix(*[model.get_as_float(model.manipulator_scale)] * 3)
            )
            with self._x_xform:
                self._build()

    def _on_model_updated(self, item: sc.AbstractManipulatorItem):
        """Handle light subclass specific updates"""
        if item in {
            self.model.intensity,
        }:
            # if intensity changed, update shape xform
            self.build_shape_xform()

    def mark_drag_began(self):
        self._is_dragging = True
        self._shaping_authored_cache = self._has_shaping_authored()

    def mark_drag_ended(self):
        self._is_dragging = False
        self._shaping_authored_cache = None
        self._cone_refresh_deferred = False
        self._revoke_interaction_end_subscription()
        if self._needs_cone_geometry_rebuild():
            self.invalidate()

    def on_model_updated(self, item: sc.AbstractManipulatorItem):
        # Regenerate the mesh
        if not self.model:
            return

        match item:
            case self.model.transform:
                # If transform changed, update the root transform
                self.__root_xf.transform = self.model.get_as_floats(item)
            case self.model.prim_path | self.model.manipulator_scale:
                # If prim_path or scale changed, redraw everything
                self.invalidate()
            case _:
                self._on_model_updated(item)


class RectLightManipulator(AbstractLightManipulator):
    light_class = UsdLux.RectLight
    model_class = RectLightModel

    _base_intensity_scale = RECT_LIGHT_INTENSITY / INTENSITY_SCALE

    # XXX: TYPING - best we can do until sc.Manipulator becomes generic on model
    @property
    def model(self) -> RectLightModel:
        return super().model

    def _build_shape_xform(self) -> list | None:
        if self.model.width and self.model.height and self.model.intensity:
            x = max(self.model.get_as_float(self.model.width), 0.0)
            y = max(self.model.get_as_float(self.model.height), 0.0)
            # set the intensity scale with a minimum added to make sure manipulator is grab-able
            z = max(self.model.get_as_float(self.model.intensity), 0.0) / self.intensity_scale + INTENSITY_MIN
            return [x, 0, 0, 0, 0, y, 0, 0, 0, 0, z, 0, 0, 0, 0, 1]
        return None

    def _build_manipulator_geometry(self):
        # Build the shape geometry as unit-sized
        h = 0.5
        z = -1.0
        # the rectangle
        shape1 = sc.Line((-h, h, 0), (h, h, 0), **DEFAULT_SHAPE_STYLE)
        shape2 = sc.Line((-h, -h, 0), (h, -h, 0), **DEFAULT_SHAPE_STYLE)
        shape3 = sc.Line((h, h, 0), (h, -h, 0), **DEFAULT_SHAPE_STYLE)
        shape4 = sc.Line((-h, h, 0), (-h, -h, 0), **DEFAULT_SHAPE_STYLE)
        rectangle_lines = [shape1, shape2, shape3, shape4]
        # add gesture to the lines of the rectangle to update width or height of the light
        vertical_hover_gesture = sc.HoverGesture(
            on_began_fn=lambda sender: set_thickness([shape1, shape2], HOVER_THICKNESS),
            on_ended_fn=lambda sender: set_thickness([shape1, shape2], THICKNESS),
        )
        rect_attr_map = {0: "width", 1: "height", 2: "intensity"}
        shape1.gestures = [LightDragGesture(self, [1], [1], rect_attr_map), vertical_hover_gesture]
        shape2.gestures = [LightDragGesture(self, [1], [-1], rect_attr_map), vertical_hover_gesture]

        horizontal_hover_gesture = sc.HoverGesture(
            on_began_fn=lambda sender: set_thickness([shape3, shape4], HOVER_THICKNESS),
            on_ended_fn=lambda sender: set_thickness([shape3, shape4], THICKNESS),
        )
        shape3.gestures = [LightDragGesture(self, [0], [1], rect_attr_map), horizontal_hover_gesture]
        shape4.gestures = [LightDragGesture(self, [0], [-1], rect_attr_map), horizontal_hover_gesture]

        if self.show_intensity_controls:
            # create hover arrows in the z-axis to indicate the intensity
            hover_arrows = _HoverArrows()
            hover_arrows.define((h, h, 0), (h, h, z))
            hover_arrows.define((-h, -h, 0), (-h, -h, z))
            hover_arrows.define((h, -h, 0), (h, -h, z))
            hover_arrows.define((-h, h, 0), (-h, h, z))
            for arrow in hover_arrows.shapes:
                arrow.gestures = [
                    LightDragGesture(self, [2], [-1], rect_attr_map, on_ended_fn=hover_arrows.hide),
                    sc.HoverGesture(
                        on_began_fn=lambda _sender: hover_arrows.show(),
                        on_ended_fn=lambda _sender: hover_arrows.hide(),
                    ),
                ]

            # create 4 rectangles at the corner, and add gesture to update width, height and intensity at the
            # same time
            r1 = make_square((h - SQUARE_CENTER_TO_EDGE, -h + SQUARE_CENTER_TO_EDGE, 0))
            r2 = make_square((h - SQUARE_CENTER_TO_EDGE, h - SQUARE_CENTER_TO_EDGE, 0))
            r3 = make_square((-h + SQUARE_CENTER_TO_EDGE, h - SQUARE_CENTER_TO_EDGE, 0))
            r4 = make_square((-h + SQUARE_CENTER_TO_EDGE, -h + SQUARE_CENTER_TO_EDGE, 0))
            hover_squares = [r1, r2, r3, r4]

            def highlight_all():
                set_thickness(rectangle_lines, HOVER_THICKNESS)
                set_color(hover_squares, HOVER_COLOR)
                hover_arrows.show()

            def unhighlight_all():
                if is_mouse_button_down():
                    return
                set_thickness(rectangle_lines, THICKNESS)
                set_color(hover_squares, CLEAR_COLOR)
                hover_arrows.hide()

            highlight_all_gesture = sc.HoverGesture(
                on_began_fn=lambda sender: highlight_all(),
                on_ended_fn=lambda sender: unhighlight_all(),
            )

            r1.gestures = [
                LightDragGesture(self, [0, 1], [1, -1], rect_attr_map, on_ended_fn=unhighlight_all),
                highlight_all_gesture,
            ]
            r2.gestures = [
                LightDragGesture(self, [0, 1], [1, 1], rect_attr_map, on_ended_fn=unhighlight_all),
                highlight_all_gesture,
            ]
            r3.gestures = [
                LightDragGesture(self, [0, 1], [-1, 1], rect_attr_map, on_ended_fn=unhighlight_all),
                highlight_all_gesture,
            ]
            r4.gestures = [
                LightDragGesture(self, [0, 1], [-1, -1], rect_attr_map, on_ended_fn=unhighlight_all),
                highlight_all_gesture,
            ]

    def _build_minimal_intensity_xform(self) -> list | None:
        if self.show_intensity_controls or not (self.model.width and self.model.height):
            return None
        length = max(self._minimal_intensity_indicator_length(), 1.0)
        y = max(self.model.get_as_float(self.model.height), 0.0) * 0.5 + 0.7
        y += max(length * 0.25, 0.0)
        return [length, 0, 0, 0, 0, length, 0, 0, 0, 0, length, 0, 0, y, 0, 1]

    def _minimal_intensity_indicator_length(self) -> float:
        if not (self.model.width and self.model.height):
            return super()._minimal_intensity_indicator_length()
        width = self.model.get_as_float(self.model.width)
        height = self.model.get_as_float(self.model.height)
        return max(width, height, 0.0) * 0.3

    def _build_minimal_intensity_geometry(self):
        if not self.show_intensity_controls:
            rect_attr_map = {0: "width", 1: "height", 2: "intensity"}
            self._build_single_intensity_arrow(
                (0, 0, 0), (0, 0, -1.0), rect_attr_map, [2], [-1], persistent_head=True, interactive=False
            )

    def _on_model_updated(self, item: sc.AbstractManipulatorItem):
        if item in {self.model.width, self.model.height, self.model.intensity}:
            # if width, height or intensity changed, update shape xform
            self.build_shape_xform()
            self.build_minimal_intensity_xform()


class DiskLightManipulator(AbstractLightManipulator):
    light_class = UsdLux.DiskLight
    model_class = DiskLightModel
    supports_spotlight_cone = True

    _base_intensity_scale = DISK_LIGHT_INTENSITY / INTENSITY_SCALE

    _arc_style = dict(DEFAULT_SHAPE_STYLE)
    _arc_style.update({"wireframe": True, "sector": False})

    # XXX: TYPING - best we can do until sc.Manipulator becomes generic on model
    @property
    def model(self) -> DiskLightModel:
        return super().model

    def _build_shape_xform(self) -> list | None:
        if self.model.radius and self.model.intensity:
            r = max(self.model.get_as_float(self.model.radius), 0.0)
            z = max(self.model.get_as_float(self.model.intensity), 0.0) / self.intensity_scale + INTENSITY_MIN
            return [r, 0, 0, 0, 0, r, 0, 0, 0, 0, z, 0, 0, 0, 0, 1]
        return None

    def _build_manipulator_geometry(self):
        # Build the shape geometry as unit-sized
        r = 1.0
        z = -1.0
        # the circle - (arc gestures are only working between -pi and +pi)
        shape1 = sc.Arc(r, axis=2, begin=0, end=math.pi / 2, **DEFAULT_ARC_STYLE)
        shape2 = sc.Arc(r, axis=2, begin=math.pi / 2, end=math.pi, **DEFAULT_ARC_STYLE)
        shape3 = sc.Arc(r, axis=2, begin=-math.pi, end=-math.pi / 2, **DEFAULT_ARC_STYLE)
        shape4 = sc.Arc(r, axis=2, begin=-math.pi / 2, end=0, **DEFAULT_ARC_STYLE)
        circle_lines = [shape1, shape2, shape3, shape4]

        # add gesture to the lines of the rectangle to update width or height of the light
        circle_hover_gesture = sc.HoverGesture(
            on_began_fn=lambda sender: set_thickness(circle_lines, HOVER_THICKNESS),
            on_ended_fn=lambda sender: set_thickness(circle_lines, THICKNESS),
        )
        disk_attr_map = {0: "radius", 1: None, 2: "intensity"}
        shape1.gestures = [LightDragGesture(self, [0], [1], disk_attr_map), circle_hover_gesture]
        shape2.gestures = [LightDragGesture(self, [0], [-1], disk_attr_map), circle_hover_gesture]
        shape3.gestures = [LightDragGesture(self, [0], [-1], disk_attr_map), circle_hover_gesture]
        shape4.gestures = [LightDragGesture(self, [0], [1], disk_attr_map), circle_hover_gesture]

        if self.show_intensity_controls:
            # create hover arrows in the z-axis to indicate the intensity
            hover_arrows = _HoverArrows()
            hover_arrows.define((r, 0, 0), (r, 0, z))
            hover_arrows.define((-r, 0, 0), (-r, 0, z))
            hover_arrows.define((0, -r, 0), (0, -r, z))
            hover_arrows.define((0, r, 0), (0, r, z))
            for arrow in hover_arrows.shapes:
                arrow.gestures = [
                    LightDragGesture(self, [2], [-1], disk_attr_map, on_ended_fn=hover_arrows.hide),
                    sc.HoverGesture(
                        on_began_fn=lambda _sender: hover_arrows.show(),
                        on_ended_fn=lambda _sender: hover_arrows.hide(),
                    ),
                ]

            # create 4 rectangles at the corner, and add gesture to update radius and intensity at the
            # same time
            r1 = make_square((r - SQUARE_CENTER_TO_EDGE, -r + SQUARE_CENTER_TO_EDGE, 0))
            r2 = make_square((r - SQUARE_CENTER_TO_EDGE, r - SQUARE_CENTER_TO_EDGE, 0))
            r3 = make_square((-r + SQUARE_CENTER_TO_EDGE, r - SQUARE_CENTER_TO_EDGE, 0))
            r4 = make_square((-r + SQUARE_CENTER_TO_EDGE, -r + SQUARE_CENTER_TO_EDGE, 0))
            hover_squares = [r1, r2, r3, r4]

            def highlight_all():
                set_thickness(circle_lines, HOVER_THICKNESS)
                set_color(hover_squares, HOVER_COLOR)
                hover_arrows.show()

            def unhighlight_all():
                if is_mouse_button_down():
                    return
                set_thickness(circle_lines, THICKNESS)
                set_color(hover_squares, CLEAR_COLOR)
                hover_arrows.hide()

            highlight_all_gesture = sc.HoverGesture(
                on_began_fn=lambda sender: highlight_all(),
                on_ended_fn=lambda sender: unhighlight_all(),
            )

            r1.gestures = [
                LightDragGesture(self, [0], [1, -1], disk_attr_map, on_ended_fn=unhighlight_all),
                highlight_all_gesture,
            ]
            r2.gestures = [
                LightDragGesture(self, [0], [1, 1], disk_attr_map, on_ended_fn=unhighlight_all),
                highlight_all_gesture,
            ]
            r3.gestures = [
                LightDragGesture(self, [0], [-1, 1], disk_attr_map, on_ended_fn=unhighlight_all),
                highlight_all_gesture,
            ]
            r4.gestures = [
                LightDragGesture(self, [0], [-1, -1], disk_attr_map, on_ended_fn=unhighlight_all),
                highlight_all_gesture,
            ]

    def _build_minimal_intensity_xform(self) -> list | None:
        if self.show_intensity_controls or not self.model.radius:
            return None
        length = max(self._minimal_intensity_indicator_length(), 1.0)
        y = max(self.model.get_as_float(self.model.radius), 0.0) + 0.7
        y += max(length * 0.25, 0.0)
        return [length, 0, 0, 0, 0, length, 0, 0, 0, 0, length, 0, 0, y, 0, 1]

    def _minimal_intensity_indicator_length(self) -> float:
        if not self.model.radius:
            return super()._minimal_intensity_indicator_length()
        return max(self.model.get_as_float(self.model.radius), 0.0) * 0.6

    def _build_minimal_intensity_geometry(self):
        if not self.show_intensity_controls:
            disk_attr_map = {0: "radius", 1: None, 2: "intensity"}
            self._build_single_intensity_arrow(
                (0, 0, 0), (0, 0, -1.0), disk_attr_map, [2], [-1], persistent_head=True, interactive=False
            )

    def _on_model_updated(self, item: sc.AbstractManipulatorItem):
        if item in {self.model.radius, self.model.intensity}:
            self.build_shape_xform()
            self.build_minimal_intensity_xform()
            if not self._is_dragging:
                self._refresh_cone_geometry_when_safe()
        elif item in {
            self.model.cone_angle,
            self.model.softness,
            self.model.exposure,
            self.model.color,
            self.model.color_temperature,
            self.model.enable_color_temperature,
        }:
            self._refresh_cone_geometry_when_safe()


class DistantLightManipulator(AbstractLightManipulator):
    light_class = UsdLux.DistantLight
    model_class = DistantLightModel

    _base_intensity_scale = DISTANT_LIGHT_INTENSITY / INTENSITY_SCALE

    # XXX: TYPING - best we can do until sc.Manipulator becomes generic on model
    @property
    def model(self) -> DistantLightModel:
        return super().model

    def _build_shape_xform(self) -> list | None:
        if self.model.intensity:
            z = max(self.model.get_as_float(self.model.intensity), 0.0) / self.intensity_scale + INTENSITY_MIN
            return [5, 0, 0, 0, 0, 5, 0, 0, 0, 0, z, 0, 0, 0, 0, 1]
        return None

    def _build_manipulator_geometry(self):
        if self.show_intensity_controls:
            attr_map = {0: None, 1: None, 2: "intensity"}
            self._build_single_intensity_arrow((0, 1.2, 0), (0, 1.2, -1.0), attr_map, [2], [-1])

    def _build_minimal_intensity_xform(self) -> list | None:
        length = self._minimal_intensity_indicator_length()
        return [length, 0, 0, 0, 0, length, 0, 0, 0, 0, length, 0, 0, 2.8, 0, 1]

    def _minimal_intensity_indicator_length(self) -> float:
        return 5.0

    def _build_minimal_intensity_geometry(self):
        if not self.show_intensity_controls:
            attr_map = {0: None, 1: None, 2: "intensity"}
            # Keep the distant-light intensity handle offset from the pivot so it does not sit on top of the
            # transform axes.
            self._build_single_intensity_arrow(
                (0, 0, 0), (0, 0, -1.0), attr_map, [2], [-1], persistent_head=True, interactive=False
            )


class IntensityMixinFor3DManipulators:
    """Base class for 3D light manipulators with an intensity control at the pivot"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Since these are not flat (2D) light shapes, we cannot just use z for intensity and we need to create a new
        # transform so that when we try to reflect intensity, the geometry of the manipulator is not affected.
        # Note: In the future, we could just add this to all manipulators and reroute intensity changes to it.
        self._intensity_xform = sc.Transform()

    def _build_intensity_xform(self) -> list | None:
        if self.model.intensity:
            i = max(self.model.get_as_float(self.model.intensity), 0.0) / self.intensity_scale + INTENSITY_MIN
            return [i, 0, 0, 0, 0, i, 0, 0, 0, 0, i, 0, 0, 0, 0, 1]
        return None

    def build_intensity_xform(self):
        if not self.model:
            return
        xform = self._build_intensity_xform()
        if xform:
            self._intensity_xform.transform = xform

    @staticmethod
    def _three_rotation_matrices():
        """A matrix for each axis"""
        return [
            sc.Matrix44.get_rotation_matrix(x=0.0, y=0.0, z=0.0, degrees=True),
            sc.Matrix44.get_rotation_matrix(x=0.0, y=-90.0, z=0.0, degrees=True),
            sc.Matrix44.get_rotation_matrix(x=-90.0, y=0.0, z=0.0, degrees=True),
        ]

    def _build_intensity_geometry(self):
        z = 1.0
        orientations = {
            0: [2],
            1: [0],
            2: [1],
        }
        flags = {
            0: 1,
            # This one is reversed. Could also switch to 2nd matrix to:
            #  Matrix.get_rotation_matrix(x=0.0, y=90.0, z=0.0, degrees=True)
            # but then would need to flip circle sectors one (or add a second _three_rotation_matrices).
            1: -1,
            2: 1,
        }
        arrow_attr_map = {0: "intensity", 1: "intensity", 2: "intensity"}
        # create hover arrows in the z-axis to indicate the intensity
        hover_arrows = _HoverArrows()
        hover_gesture = sc.HoverGesture(
            on_began_fn=lambda _sender: hover_arrows.show(), on_ended_fn=lambda _sender: hover_arrows.hide()
        )
        for i, rotation_transform in enumerate(self._three_rotation_matrices()):
            with sc.Transform(rotation_transform):
                positive_arrow = hover_arrows.define((0, 0, 0), (0, 0, z))
                negative_arrow = hover_arrows.define((0, 0, 0), (0, 0, -z))
                positive_arrow.gestures = [
                    LightDragGesture(
                        self,
                        orientations[i],
                        [1 * flags[i]],
                        arrow_attr_map,
                        on_ended_fn=hover_arrows.hide,
                        shape_xform=self._intensity_xform,
                    ),
                    hover_gesture,
                ]
                negative_arrow.gestures = [
                    LightDragGesture(
                        self,
                        orientations[i],
                        [-1 * flags[i]],
                        arrow_attr_map,
                        on_ended_fn=hover_arrows.hide,
                        shape_xform=self._intensity_xform,
                    ),
                    hover_gesture,
                ]

    def _build(self):
        """Override the default to build a separate xform for handling intensity"""
        self._shape_xform = sc.Transform()
        self._intensity_xform = sc.Transform()
        self.build_shape_xform()
        with self._shape_xform:
            self._build_manipulator_geometry()
        if self.show_intensity_controls:
            self.build_intensity_xform()
            with self._intensity_xform:
                self._build_intensity_geometry()
        # Kept parallel to AbstractLightManipulator._build — the cone must not be scaled by
        # `_shape_xform` or `_intensity_xform`.
        self._build_cone_geometry()


class SphereLightManipulator(IntensityMixinFor3DManipulators, AbstractLightManipulator):
    light_class = UsdLux.SphereLight
    model_class = SphereLightModel
    supports_spotlight_cone = True

    _base_intensity_scale = SPHERE_LIGHT_INTENSITY / INTENSITY_SCALE

    # XXX: TYPING - best we can do until sc.Manipulator becomes generic on model
    @property
    def model(self) -> SphereLightModel:
        return super().model

    def _build_shape_xform(self) -> list | None:
        if self.model.radius:
            r = max(self.model.get_as_float(self.model.radius), 0.0)
            return [r, 0, 0, 0, 0, r, 0, 0, 0, 0, r, 0, 0, 0, 0, 1]
        return None

    def _build_manipulator_geometry(self):
        # Build the shape geometry as unit-sized
        r = 1.0

        orientations = {  # circle to "active axis"
            0: [0],
            1: [2],  # this circle is perpendicular to x axis so we use z
            2: [0],
        }
        flags = [[1], [-1], [-1], [1]]  # flags for each sector of circle
        sphere_attr_map = {0: "radius", 1: "radius", 2: "radius"}

        all_circle_lines = []
        for i, rotation_transform in enumerate(self._three_rotation_matrices()):
            shape_xform = sc.Transform(rotation_transform)
            with shape_xform:
                # the circle - (arc gestures are only working between -pi and +pi)
                shape1 = sc.Arc(r, axis=2, begin=0, end=math.pi / 2, **DEFAULT_ARC_STYLE)
                shape2 = sc.Arc(r, axis=2, begin=math.pi / 2, end=math.pi, **DEFAULT_ARC_STYLE)
                shape3 = sc.Arc(r, axis=2, begin=-math.pi, end=-math.pi / 2, **DEFAULT_ARC_STYLE)
                shape4 = sc.Arc(r, axis=2, begin=-math.pi / 2, end=0, **DEFAULT_ARC_STYLE)
                circle_lines = [shape1, shape2, shape3, shape4]
                all_circle_lines.extend([shape1, shape2, shape3, shape4])

                circle_hover_gesture = sc.HoverGesture(
                    on_began_fn=lambda sender: set_thickness(all_circle_lines, HOVER_THICKNESS),
                    on_ended_fn=lambda sender: set_thickness(all_circle_lines, THICKNESS),
                )
                for shape, flag in zip(circle_lines, flags):
                    shape.gestures = [
                        LightDragGesture(self, orientations[i], flag, sphere_attr_map),
                        circle_hover_gesture,
                    ]

    def _on_model_updated(self, item: sc.AbstractManipulatorItem):
        """Handle light subclass specific updates"""
        if item in {self.model.radius, self.model.intensity}:
            self.build_shape_xform()
            self.build_intensity_xform()
            if not self._is_dragging:
                self._refresh_cone_geometry_when_safe()
        elif item in {
            self.model.cone_angle,
            self.model.softness,
            self.model.exposure,
            self.model.color,
            self.model.color_temperature,
            self.model.enable_color_temperature,
        }:
            self._refresh_cone_geometry_when_safe()


class CylinderLightManipulator(IntensityMixinFor3DManipulators, AbstractLightManipulator):
    light_class = UsdLux.CylinderLight
    model_class = CylinderLightModel

    _base_intensity_scale = CYLINDER_LIGHT_INTENSITY / INTENSITY_SCALE

    # XXX: TYPING - best we can do until sc.Manipulator becomes generic on model
    @property
    def model(self) -> CylinderLightModel:
        return super().model

    def _build_shape_xform(self) -> list | None:
        if self.model.radius:
            r = max(self.model.get_as_float(self.model.radius), 0.0)
            x = max(self.model.get_as_float(self.model.length), 0.0)
            return [x, 0, 0, 0, 0, r, 0, 0, 0, 0, r, 0, 0, 0, 0, 1]
        return None

    @staticmethod
    def _two_translation_matrices():
        """A matrix for each end of the cylinder"""
        return [
            sc.Matrix44.get_translation_matrix(x=0.5, y=0.0, z=0.0),
            sc.Matrix44.get_translation_matrix(x=-0.5, y=0.0, z=0.0),
        ]

    def _build_manipulator_geometry(self):
        # Build the shape geometry as unit-sized
        r = 1
        z = 0.5

        all_circle_lines = []
        flags = [[1], [1], [-1], [-1]]  # flags for each sector of circle
        circle_attr_map = {0: "radius", 1: "radius", 2: "radius"}
        for translation_xform in self._two_translation_matrices():
            shape_xform = sc.Transform(translation_xform)
            with shape_xform:
                # the circle - (arc gestures are only working between -pi and +pi)
                shape1 = sc.Arc(r, axis=0, begin=0, end=math.pi / 2, **DEFAULT_ARC_STYLE)
                shape2 = sc.Arc(r, axis=0, begin=math.pi / 2, end=math.pi, **DEFAULT_ARC_STYLE)
                shape3 = sc.Arc(r, axis=0, begin=-math.pi, end=-math.pi / 2, **DEFAULT_ARC_STYLE)
                shape4 = sc.Arc(r, axis=0, begin=-math.pi / 2, end=0, **DEFAULT_ARC_STYLE)
                circle_lines = [shape1, shape2, shape3, shape4]
                all_circle_lines.extend(circle_lines)

                circle_hover_gesture = sc.HoverGesture(
                    on_began_fn=lambda sender: set_thickness(all_circle_lines, HOVER_THICKNESS),
                    on_ended_fn=lambda sender: set_thickness(all_circle_lines, THICKNESS),
                )
                for shape, flag in zip(circle_lines, flags):
                    shape.gestures = [
                        LightDragGesture(self, [2], flag, circle_attr_map),
                        circle_hover_gesture,
                    ]

        # the lines
        line_attr_map = {0: "length", 1: "length", 2: "length"}
        length_lines = []
        s = math.sin(math.pi / 4) * r
        for x, y in [(-s, s), (-s, -s), (s, s), (s, -s)]:
            shape1 = sc.Line((-z, x, y), (0, x, y), **DEFAULT_SHAPE_STYLE)
            shape2 = sc.Line((-z, x, y), (z, x, y), **DEFAULT_SHAPE_STYLE)
            length_lines.extend([shape1, shape2])
            length_hover_gesture = sc.HoverGesture(
                on_began_fn=lambda sender: set_thickness(length_lines, HOVER_THICKNESS),
                on_ended_fn=lambda sender: set_thickness(length_lines, THICKNESS),
            )
            shape1.gestures = [LightDragGesture(self, [0], [-1], line_attr_map), length_hover_gesture]
            shape2.gestures = [LightDragGesture(self, [0], [1], line_attr_map), length_hover_gesture]

    def _on_model_updated(self, item: sc.AbstractManipulatorItem):
        """Handle light subclass specific updates"""
        if item in {self.model.radius, self.model.length}:
            self.build_shape_xform()
        if item in {
            self.model.intensity,
        }:
            self.build_intensity_xform()
