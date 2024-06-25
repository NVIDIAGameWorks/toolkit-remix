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
    "DiskLightManipulator",
    "DistantLightManipulator",
    "RectLightManipulator",
    "SphereLightManipulator",
]

import abc
import math
from typing import TYPE_CHECKING

import carb.input
import omni.appwindow
import omni.kit
import omni.kit.commands
from omni.ui import color as cl
from omni.ui import scene as sc
from pxr import Usd, UsdLux

from .light_model import (
    AbstractLightModel,
    DiskLightModel,
    DistantLightModel,
    RectLightModel,
    SphereLightModel,
    UsdLuxLight,
)

if TYPE_CHECKING:
    from lightspeed.trex.viewports.shared.widget.interface import LayerItem
    from lightspeed.trex.viewports.shared.widget.layers import ViewportLayers

ConcreteLightManipulatorCls: RectLightManipulator | DiskLightManipulator | DistantLightManipulator = None

# this INTENSITY_SCALE is to make the manipulators a reasonable length with large intensity number
INTENSITY_SCALE = 3.5  # global scaler of how big intensity appears
INTENSITY_MIN = 0.2  # min length to make sure something shows for user to grab on to (twice arrow height)
# defaults are from: `omni.flux.light_creator.widget/omni/flux/light_creator/widget/setup_ui.py`
DISTANT_LIGHT_INTENSITY = 25
SPHERE_LIGHT_INTENSITY = 100
RECT_LIGHT_INTENSITY = 400
DISK_LIGHT_INTENSITY = 500
CYLINDER_LIGHT_INTENSITY = 140

ARROW_WIDTH = 0.03
ARROW_HEIGHT = 0.1
ARROW_P = [
    [ARROW_WIDTH, ARROW_WIDTH, 0],
    [-ARROW_WIDTH, ARROW_WIDTH, 0],
    [0, 0, ARROW_HEIGHT],
    #
    [ARROW_WIDTH, -ARROW_WIDTH, 0],
    [-ARROW_WIDTH, -ARROW_WIDTH, 0],
    [0, 0, ARROW_HEIGHT],
    #
    [ARROW_WIDTH, ARROW_WIDTH, 0],
    [ARROW_WIDTH, -ARROW_WIDTH, 0],
    [0, 0, ARROW_HEIGHT],
    #
    [-ARROW_WIDTH, ARROW_WIDTH, 0],
    [-ARROW_WIDTH, -ARROW_WIDTH, 0],
    [0, 0, ARROW_HEIGHT],
    #
    [ARROW_WIDTH, ARROW_WIDTH, 0],
    [-ARROW_WIDTH, ARROW_WIDTH, 0],
    [-ARROW_WIDTH, -ARROW_WIDTH, 0],
    [ARROW_WIDTH, -ARROW_WIDTH, 0],
]

ARROW_VC = [3, 3, 3, 3, 4]
ARROW_VI = list(range(sum(ARROW_VC)))
# length of line almost to tip of arrow but shorter to make sure line doesn't dull point
# when drawn
ARROW_TIP = ARROW_HEIGHT - 0.02

_manipulator_classes: dict[UsdLuxLight, ConcreteLightManipulatorCls] | None = None

# Style settings, as kwargs
THICKNESS = 1
HOVER_THICKNESS = THICKNESS + 2
COLOR = cl.yellow
HOVER_COLOR = cl.yellow  # color for arrows and corner rectangles when hovered
CLEAR_COLOR = cl(0, 0, 0, 0)  # the key is that alpha is 0 here
DEFAULT_SHAPE_STYLE = {"thickness": THICKNESS, "color": COLOR}
SQUARE_WIDTH = 0.06
SQUARE_CENTER_TO_EDGE = 0.5 * SQUARE_WIDTH + 0.01 * THICKNESS


def is_mouse_button_down(button=carb.input.MouseInput.LEFT_BUTTON) -> bool:
    iinput = carb.input.acquire_input_interface()
    app_window = omni.appwindow.get_default_app_window()
    mouse = app_window.get_mouse()
    is_down = iinput.get_mouse_value(mouse, button)
    return is_down


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


def get_manipulator_class(light: Usd.Prim) -> type[ConcreteLightManipulatorCls] | None:
    global _manipulator_classes
    if _manipulator_classes is None:
        _manipulator_classes = {}
        for cls in (RectLightManipulator, DiskLightManipulator, DistantLightManipulator, SphereLightManipulator):
            _manipulator_classes[cls.light_class] = cls

    for light_class, cls in _manipulator_classes.items():
        if light.IsA(light_class):
            return cls
    return None


class _DisableViewportLayers:
    """Object that hides viewport layers and then resets state when it goes out of scope."""

    # intentionally make this a class attribute in order to ensure that no matter what order
    # this disable instance is created or destroyed that layers will be restored properly.
    # Note: this should be sufficient, even though there is a chance that if you drag twice
    # in quick succession the first drag may re-enable layers before the second drag completes.
    # Having a layer not disabled while dragging is a trivial problem compared with it staying
    # incorrectly disabled after a drag.
    __cls_layers: dict[LayerItem, bool] = {}

    def __init__(self, viewport_layers: ViewportLayers, layers_and_categories: list[tuple[str, str]]):
        self.__layers: list[LayerItem] = []
        for layer, category in layers_and_categories:
            found_layer = viewport_layers.find_viewport_layer(layer, category)
            # make sure not to disable same layer twice and record the modified state
            if found_layer and found_layer not in self.__cls_layers:
                self.__cls_layers[found_layer] = found_layer.visible
                self.__layers.append(found_layer)
                found_layer.visible = False

    def __del__(self):
        # only restore the layers that this instance disabled
        for layer in self.__layers:
            # pop the layer off the class storage so that the next instantiation can
            # record the state fresh.
            layer.visible = self.__cls_layers.pop(layer)


def disable_other_drag_gestures(viewport_layers):
    """
    Disable selection rect and prim transform effects on a Viewport.

    Returns an object that resets selection when it goes out of scope.
    """
    disable_items = [
        ("Selection", "manipulator"),
        ("Prim Transform", "manipulator"),
    ]
    return _DisableViewportLayers(viewport_layers, disable_items)


class _DragGesture(sc.DragGesture):
    """Gesture to capture a drag on a light manipulator"""

    def __init__(
        self,
        manipulator: AbstractLightManipulator,
        orientations: list[int],
        flag: list[int],
        orientation_attr_map: dict[int, str],
        on_ended_fn=None,
        shape_xform: sc.Transform = None,
    ):
        super().__init__()
        self._manipulator = manipulator
        self.model: AbstractLightModel = self._manipulator.model
        # record this _previous_ray_point to get the mouse moved vector
        self._previous_ray_point = None
        # this defines the orientation of the move, 0 means x, 1 means y, 2 means z. It's a list so that we
        # can move a selection
        self.orientations = orientations
        # this defines the mapping between direction of a drag and the attr it should affect
        self.orientation_attr_map = orientation_attr_map
        if not shape_xform:
            shape_xform = self._manipulator.shape_xform
        self._shape_xform = shape_xform
        # global flag to indicate if the manipulator changes all the width, height and intensity, rectangle manipulator
        # in the example
        self.is_global = len(self.orientations) > 1
        # this defines the negative or positive of the move. E.g. when we move the positive x line to the right, it
        # enlarges the width, and when we move the negative line to the left, it also enlarges the width
        # 1 means positive and -1 means negative. It's a list so that we can reflect list orientation
        self.flag = flag
        self.user_on_ended_fn = on_ended_fn
        self.__disable_gestures = None  # noqa PLW0238 Unused private member - used as context manager!

    def _get_axis_attr(self, orientation: int) -> str:
        return self.orientation_attr_map[orientation]

    def _on_began(self):
        """
        Record the current values to the model for the omni.kit.command and
        do any required initializations.
        """
        for orientation in self.orientations:
            item = self.model.get_item(self._get_axis_attr(orientation))
            self.model.set_item_value(item, self.model.get_as_float(item))

        if self.is_global:
            intensity_item = self.model.intensity
            self.model.set_item_value(intensity_item, self.model.get_as_float(intensity_item))

        # Initialize these attributes in case on_changed is never called. It seems like that happens occasionally.
        # None values will be non-ops.
        self.x_new = None
        self.y_new = None
        self.z_new = None
        self.intensity_new = None
        self._results = {0: None, 1: None, 2: None}

    def on_began(self):
        # When the user drags the slider, we don't want to see the selection
        # rect. In Viewport Next, it works well automatically because the
        # selection rect is a manipulator with its gesture, and we add the
        # slider manipulator to the same SceneView.
        # In Viewport Legacy, the selection rect is not a manipulator. Thus it's
        # not disabled automatically, and we need to disable it with the following code.
        self.__disable_gestures = disable_other_drag_gestures(  # noqa PLW0238 Unused private member
            self._manipulator.viewport_layers
        )

        # initialize the self._previous_ray_point
        self._previous_ray_point = self.gesture_payload.ray_closest_point

        # record the current values to the model for the omni.kit.command
        self._on_began()

    def _on_changed(self, moved_x, moved_y, moved_z):
        """Update USD with the appropriate values based on the drag deltas"""
        # since self._shape_xform.transform = [x, 0, 0, 0,
        #                                      0, y, 0, 0,
        #                                      0, 0, z, 0,
        #                                      0, 0, 0, 1]
        # for example, when we want to update the  RectLightManipulator, we are actually
        # updating self._shape_xform.transform[0] for width and self._shape_xform.transform[5]
        # for height and self._shape_xform.transform[10] for intensity
        x = self._shape_xform.transform[0]
        y = self._shape_xform.transform[5]
        z = self._shape_xform.transform[10]

        self.x_new = max(x + moved_x, 0.0)
        self.y_new = max(y + moved_y, 0.0)
        self.z_new = max(z + moved_z, 0.0)

        def update_intensity(intensity_new_: float):
            # get a clamped value for calculations removing the minimum scale that was added
            self.intensity_new = max(intensity_new_ - INTENSITY_MIN, 0.0)
            self.model.set_raw_intensity_multiple(self.model.intensity, self.intensity_new)

        # update the USD as well as update the ui
        for axis, value in ((0, self.x_new), (1, self.y_new), (2, self.z_new)):
            if axis not in self.orientations:
                continue
            attribute = self._get_axis_attr(axis)
            if attribute == "intensity":
                update_intensity(value)
            else:
                item = self.model.get_item(self._get_axis_attr(axis))
                self.model.set_float_multiple(self._get_axis_attr(axis), item, value)

        if self.is_global:
            # need to update the intensity in a different way
            # Note: This is a little unwieldy for the user, so we may want to just lock intensity if we get [0, 1]
            # for orientation and just resize the rectangle. Still this is ok since it keeps the overall power of the
            # rect light somewhat constant. As area increases... intensity decreases.
            intensity_new = z * x * y / max(self.x_new * self.y_new, 1.0)
            update_intensity(intensity_new)

        self._results = {0: self.x_new, 1: self.y_new, 2: self.z_new}

    def on_changed(self):
        object_ray_point = self.gesture_payload.ray_closest_point
        # calculate the ray moved vector
        moved = [a - b for a, b in zip(object_ray_point, self._previous_ray_point)]
        # transfer moved from world to object space, [0] to make it a normal, not point
        moved = self._manipulator.xform.transform_space(sc.Space.WORLD, sc.Space.OBJECT, moved + [0])
        # 2.0 because `_shape_xform.transform` is a scale matrix and it means
        # the width of the rectangle is twice the scale matrix.
        moved_x = moved[0] * 2.0 * self.flag[0]
        moved_y = moved[1] * 2.0 * (self.flag[1] if self.is_global else self.flag[0])
        moved_z = moved[2] * self.flag[0]

        # update the self._previous_ray_point
        self._previous_ray_point = object_ray_point

        self._on_changed(moved_x, moved_y, moved_z)

    def _on_ended(self):
        """Set the final values using `set_float_commands` to make change undoable"""
        for orientation in self.orientations:
            if self._get_axis_attr(orientation) == "intensity":
                if self.intensity_new:
                    self.model.set_raw_intensity_commands_multiple(self.model.intensity, self.intensity_new)
            else:
                item = self.model.get_item(self._get_axis_attr(orientation))
                value = self._results[orientation]
                if value:
                    self.model.set_float_commands_multiple(self._get_axis_attr(orientation), item, value)

        if self.is_global and self.z_new:
            self.model.set_raw_intensity_commands_multiple(self.model.intensity, self.intensity_new)

    def on_ended(self):
        # This re-enables the selection in the Viewport Legacy
        self.__disable_gestures = None  # noqa PLW0238 Unused private member

        if self.is_global:
            # start group command
            omni.kit.undo.begin_group()

        self._on_ended()

        if self.is_global:
            # end group command
            omni.kit.undo.end_group()
        if self.user_on_ended_fn:
            self.user_on_ended_fn()


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
    # For each light type, we light type's default intensity / INTENSITY SCALE
    # The eventual result is: length = (i * INTENSITY_SCALE) / (default intensity)
    intensity_scale = 500 / INTENSITY_SCALE

    def __init__(self, viewport_layers, **kwargs):
        super().__init__(**kwargs)
        self._viewport_layers = viewport_layers
        self.__root_xf = sc.Transform()
        self._x_xform = sc.Transform()
        self._shape_xform = sc.Transform()

    @property
    def viewport_layers(self) -> ViewportLayers:
        return self._viewport_layers

    @property
    def xform(self) -> sc.Transform:
        return self._x_xform

    @property
    def shape_xform(self) -> sc.Transform:
        return self._shape_xform

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

    def _build(self):
        self._shape_xform = sc.Transform()
        # Build the shape's transform
        self.build_shape_xform()
        with self._shape_xform:
            self._build_manipulator_geometry()

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
        if item in (self.model.intensity,):
            # if intensity changed, update shape xform
            self.build_shape_xform()

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

    intensity_scale = RECT_LIGHT_INTENSITY / INTENSITY_SCALE

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
        shape1.gestures = [_DragGesture(self, [1], [1], rect_attr_map), vertical_hover_gesture]
        shape2.gestures = [_DragGesture(self, [1], [-1], rect_attr_map), vertical_hover_gesture]

        horizontal_hover_gesture = sc.HoverGesture(
            on_began_fn=lambda sender: set_thickness([shape3, shape4], HOVER_THICKNESS),
            on_ended_fn=lambda sender: set_thickness([shape3, shape4], THICKNESS),
        )
        shape3.gestures = [_DragGesture(self, [0], [1], rect_attr_map), horizontal_hover_gesture]
        shape4.gestures = [_DragGesture(self, [0], [-1], rect_attr_map), horizontal_hover_gesture]

        # create hover arrows in the z-axis to indicate the intensity
        hover_arrows = _HoverArrows()
        hover_arrows.define((h, h, 0), (h, h, z))
        hover_arrows.define((-h, -h, 0), (-h, -h, z))
        hover_arrows.define((h, -h, 0), (h, -h, z))
        hover_arrows.define((-h, h, 0), (-h, h, z))
        for arrow in hover_arrows.shapes:
            arrow.gestures = [
                _DragGesture(self, [2], [-1], rect_attr_map, on_ended_fn=hover_arrows.hide),
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
            _DragGesture(self, [0, 1], [1, -1], rect_attr_map, on_ended_fn=unhighlight_all),
            highlight_all_gesture,
        ]
        r2.gestures = [
            _DragGesture(self, [0, 1], [1, 1], rect_attr_map, on_ended_fn=unhighlight_all),
            highlight_all_gesture,
        ]
        r3.gestures = [
            _DragGesture(self, [0, 1], [-1, 1], rect_attr_map, on_ended_fn=unhighlight_all),
            highlight_all_gesture,
        ]
        r4.gestures = [
            _DragGesture(self, [0, 1], [-1, -1], rect_attr_map, on_ended_fn=unhighlight_all),
            highlight_all_gesture,
        ]

    def _on_model_updated(self, item: sc.AbstractManipulatorItem):
        if item in (self.model.width, self.model.height, self.model.intensity):
            # if width, height or intensity changed, update shape xform
            self.build_shape_xform()


class DiskLightManipulator(AbstractLightManipulator):
    light_class = UsdLux.DiskLight
    model_class = DiskLightModel

    intensity_scale = DISK_LIGHT_INTENSITY / INTENSITY_SCALE

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
        shape1 = sc.Arc(r, axis=2, begin=0, end=math.pi / 2, **self._arc_style)
        shape2 = sc.Arc(r, axis=2, begin=math.pi / 2, end=math.pi, **self._arc_style)
        shape3 = sc.Arc(r, axis=2, begin=-math.pi, end=-math.pi / 2, **self._arc_style)
        shape4 = sc.Arc(r, axis=2, begin=-math.pi / 2, end=0, **self._arc_style)
        circle_lines = [shape1, shape2, shape3, shape4]

        # add gesture to the lines of the rectangle to update width or height of the light
        circle_hover_gesture = sc.HoverGesture(
            on_began_fn=lambda sender: set_thickness(circle_lines, HOVER_THICKNESS),
            on_ended_fn=lambda sender: set_thickness(circle_lines, THICKNESS),
        )
        disk_attr_map = {0: "radius", 1: None, 2: "intensity"}
        shape1.gestures = [_DragGesture(self, [0], [1], disk_attr_map), circle_hover_gesture]
        shape2.gestures = [_DragGesture(self, [0], [-1], disk_attr_map), circle_hover_gesture]
        shape3.gestures = [_DragGesture(self, [0], [-1], disk_attr_map), circle_hover_gesture]
        shape4.gestures = [_DragGesture(self, [0], [1], disk_attr_map), circle_hover_gesture]

        # create hover arrows in the z-axis to indicate the intensity
        hover_arrows = _HoverArrows()
        hover_arrows.define((r, 0, 0), (r, 0, z))
        hover_arrows.define((-r, 0, 0), (-r, 0, z))
        hover_arrows.define((0, -r, 0), (0, -r, z))
        hover_arrows.define((0, r, 0), (0, r, z))
        for arrow in hover_arrows.shapes:
            arrow.gestures = [
                _DragGesture(self, [2], [-1], disk_attr_map, on_ended_fn=hover_arrows.hide),
                sc.HoverGesture(
                    on_began_fn=lambda _sender: hover_arrows.show(), on_ended_fn=lambda _sender: hover_arrows.hide()
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
            _DragGesture(self, [0], [1, -1], disk_attr_map, on_ended_fn=unhighlight_all),
            highlight_all_gesture,
        ]
        r2.gestures = [
            _DragGesture(self, [0], [1, 1], disk_attr_map, on_ended_fn=unhighlight_all),
            highlight_all_gesture,
        ]
        r3.gestures = [
            _DragGesture(self, [0], [-1, 1], disk_attr_map, on_ended_fn=unhighlight_all),
            highlight_all_gesture,
        ]
        r4.gestures = [
            _DragGesture(self, [0], [-1, -1], disk_attr_map, on_ended_fn=unhighlight_all),
            highlight_all_gesture,
        ]

    def _on_model_updated(self, item: sc.AbstractManipulatorItem):
        if item in (self.model.radius, self.model.intensity):
            # if width, height or intensity changed, update shape xform
            self.build_shape_xform()


class DistantLightManipulator(AbstractLightManipulator):
    light_class = UsdLux.DistantLight
    model_class = DistantLightModel

    intensity_scale = DISTANT_LIGHT_INTENSITY / INTENSITY_SCALE

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
        # Build the shape geometry as unit-sized
        r = 0.5
        z = -1.0
        attr_map = {0: None, 1: None, 2: "intensity"}
        # create hover arrows in the z-axis to indicate the intensity
        hover_arrows = _HoverArrows()
        hover_arrows.define((r, 0, 0), (r, 0, z))
        hover_arrows.define((-r, 0, 0), (-r, 0, z))
        hover_arrows.define((0, -r, 0), (0, -r, z))
        hover_arrows.define((0, r, 0), (0, r, z))
        for arrow in hover_arrows.shapes:
            arrow.gestures = [
                _DragGesture(self, [2], [-1], attr_map, on_ended_fn=hover_arrows.hide),
                sc.HoverGesture(
                    on_began_fn=lambda _sender: hover_arrows.show(), on_ended_fn=lambda _sender: hover_arrows.hide()
                ),
            ]


class SphereLightManipulator(AbstractLightManipulator):
    light_class = UsdLux.SphereLight
    model_class = SphereLightModel

    intensity_scale = SPHERE_LIGHT_INTENSITY / INTENSITY_SCALE

    _arc_style = dict(DEFAULT_SHAPE_STYLE)
    _arc_style.update({"wireframe": True, "sector": False})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._intensity_xform = sc.Transform()

    # XXX: TYPING - best we can do until sc.Manipulator becomes generic on model
    @property
    def model(self) -> SphereLightModel:
        return super().model

    def _build_shape_xform(self) -> list | None:
        if self.model.radius:
            r = max(self.model.get_as_float(self.model.radius), 0.0)
            return [r, 0, 0, 0, 0, r, 0, 0, 0, 0, r, 0, 0, 0, 0, 1]
        return None

    def _build_intensity_xform(self) -> list | None:
        if self.model.intensity:
            i = max(self.model.get_as_float(self.model.intensity), 0.0) / self.intensity_scale + INTENSITY_MIN
            return [i, 0, 0, 0, 0, i, 0, 0, 0, 0, i, 0, 0, 0, 0, 1]
        return None

    @staticmethod
    def _three_rotation_matrices():
        return [
            sc.Matrix44.get_rotation_matrix(x=0.0, y=0.0, z=0.0, degrees=True),
            sc.Matrix44.get_rotation_matrix(x=0.0, y=-90.0, z=0.0, degrees=True),
            sc.Matrix44.get_rotation_matrix(x=-90.0, y=0.0, z=0.0, degrees=True),
        ]

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
                shape1 = sc.Arc(r, axis=2, begin=0, end=math.pi / 2, **self._arc_style)
                shape2 = sc.Arc(r, axis=2, begin=math.pi / 2, end=math.pi, **self._arc_style)
                shape3 = sc.Arc(r, axis=2, begin=-math.pi, end=-math.pi / 2, **self._arc_style)
                shape4 = sc.Arc(r, axis=2, begin=-math.pi / 2, end=0, **self._arc_style)
                circle_lines = [shape1, shape2, shape3, shape4]
                all_circle_lines.extend([shape1, shape2, shape3, shape4])

                circle_hover_gesture = sc.HoverGesture(
                    on_began_fn=lambda sender: set_thickness(all_circle_lines, HOVER_THICKNESS),
                    on_ended_fn=lambda sender: set_thickness(all_circle_lines, THICKNESS),
                )
                for shape, flag in zip(circle_lines, flags):
                    shape.gestures = [
                        _DragGesture(self, orientations[i], flag, sphere_attr_map),
                        circle_hover_gesture,
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
                    _DragGesture(
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
                    _DragGesture(
                        self,
                        orientations[i],
                        [-1 * flags[i]],
                        arrow_attr_map,
                        on_ended_fn=hover_arrows.hide,
                        shape_xform=self._intensity_xform,
                    ),
                    hover_gesture,
                ]

    def build_intensity_xform(self):
        if not self.model:
            return
        xform = self._build_intensity_xform()
        if xform:
            self._intensity_xform.transform = xform

    def _build(self):
        """Override the default to build a separate xform for handling intensity"""
        self._shape_xform = sc.Transform()
        self._intensity_xform = sc.Transform()
        self.build_shape_xform()
        with self._shape_xform:
            self._build_manipulator_geometry()
        self.build_intensity_xform()
        with self._intensity_xform:
            self._build_intensity_geometry()

    def _on_model_updated(self, item: sc.AbstractManipulatorItem):
        """Handle light subclass specific updates"""
        if item in (self.model.radius,):
            self.build_shape_xform()
        if item in (self.model.intensity,):
            self.build_intensity_xform()
