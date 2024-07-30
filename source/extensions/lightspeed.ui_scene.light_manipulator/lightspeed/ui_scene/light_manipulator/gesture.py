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

from typing import TYPE_CHECKING

import omni.appwindow
import omni.kit
import omni.kit.commands
from omni.ui import scene as sc

from .constants import DIMENSION_MIN, INTENSITY_MIN

if TYPE_CHECKING:
    from lightspeed.trex.viewports.shared.widget.interface import LayerItem
    from lightspeed.trex.viewports.shared.widget.layers import ViewportLayers

    from .light_manipulator import AbstractLightManipulator
    from .light_model import AbstractLightModel


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


class LightDragGesture(sc.DragGesture):
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
                value = max(value, DIMENSION_MIN)
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
                    value = max(value, DIMENSION_MIN)
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
