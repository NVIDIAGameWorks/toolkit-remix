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
    "AbstractLightModel",
    "CylinderLightModel",
    "DiskLightModel",
    "DistantLightModel",
    "RectLightModel",
    "UsdLuxLight",
]

from typing import TYPE_CHECKING

import omni.usd
from omni.ui import scene as sc
from pxr import Gf, Sdf, Tf, Usd, UsdGeom, UsdLux

if TYPE_CHECKING:
    from .layer import LightManipulatorLayer
    from .light_manipulator import AbstractLightManipulator

UsdLuxLight: UsdLux.BoundableLightBase | UsdLux.NonboundableLightBase = None
LightModelItem: StringItem | FloatItem | MatrixItem = None


def _flatten_matrix(matrix: Gf.Matrix4d):
    m0, m1, m2, m3 = matrix[0], matrix[1], matrix[2], matrix[3]
    return [
        m0[0],
        m0[1],
        m0[2],
        m0[3],
        m1[0],
        m1[1],
        m1[2],
        m1[3],
        m2[0],
        m2[1],
        m2[2],
        m2[3],
        m3[0],
        m3[1],
        m3[2],
        m3[3],
    ]


class MatrixItem(sc.AbstractManipulatorItem):
    """
    The Model Item represents the transformation. It doesn't contain anything
    because we take the transformation directly from USD when requesting.
    """

    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

    def __init__(self):
        super().__init__()
        self.value = self.identity.copy()


class FloatItem(sc.AbstractManipulatorItem):
    """The Model Item contains a single float value about some attribute"""

    def __init__(self, value=0.0):
        super().__init__()
        self.value = value


class StringItem(sc.AbstractManipulatorItem):
    """The Model Item contains a single string value about some attribute"""

    def __init__(self, value=""):
        super().__init__()
        self.value = value


class AbstractLightModel(sc.AbstractManipulatorModel):
    """
    A model that tracks the attributes of the selected light.
    """

    light_class: type[UsdLuxLight] = None
    linked_axes = [0, 0, 0]

    def __init__(self, prim: Usd.Prim, usd_context_name: str = "", viewport_layer: LightManipulatorLayer = None):
        super().__init__()

        self.prim_path = StringItem()
        self.transform = MatrixItem()
        self.intensity = FloatItem()
        self.manipulator_scale = FloatItem(1.0)
        self._time = Usd.TimeCode.Default()

        self._prim = prim
        self._usd_context_name = usd_context_name
        self._usd_context = omni.usd.get_context(self._usd_context_name)
        # allow scaling for non-physically proportionate light manipulators
        self._proportional = not (self._prim.IsA(UsdLux.DistantLight) or self._prim.IsA(UsdLux.DomeLight))
        self._viewport_layer = viewport_layer

        # support redirecting edits to another prim path than is displayed (useful with instances in order
        # to forward edits to the prototype prims)
        self.__redirect_path: Sdf.Path | None = None

        # Current selection
        self._light: UsdLuxLight = None
        self._xform_prim: Usd.Prim = None
        self._stage_listener: Tf.Listener | None = None

        # Track selection change
        self._events = self._usd_context.get_stage_event_stream()
        self._stage_event_sub = self._events.create_subscription_to_pop(
            self._on_stage_event, name="Light Manipulator Selection Change"
        )

    def __del__(self):
        self._invalidate_object()

    def set_path_redirect(self, path: Sdf.Path):
        self.__redirect_path = path

    def get_prim_path(self) -> str:
        return self.prim_path.value

    def set_manipulator_scale(self, scale: float):
        if self._proportional:
            return  # keep a constant 1.0 scale to ensure real world dimensions
        self.set_item_value(self.manipulator_scale, scale)
        self._item_changed(self.manipulator_scale)

    def update_from_prim(self):
        self.set_item_value(self.transform, self._get_transform(self._time))
        self.set_item_value(self.intensity, self._get_intensity(self._time))

    def get_item(self, identifier: str) -> sc.AbstractManipulatorItem | None:
        return getattr(self, identifier, None)

    def _get_as_floats(self, item: LightModelItem) -> list[float] | None:
        return None

    def get_as_floats(self, item: LightModelItem) -> list[float]:
        """get the item value directly from USD"""
        if item == self.transform:
            return self._get_transform(self._time)
        if item == self.intensity:
            return [self._get_intensity(self._time)]

        value: list[float] = self._get_as_floats(item)
        if value is not None:
            return value

        # Get the value directly from the item
        return [item.value]

    def set_float_commands(self, item, value: float | None):
        """
        Shortcut for `set_floats_commands` that sets an array with the size of one.
        """
        if value is None:
            return
        self.set_floats_commands(item, [value])

    def _set_floats_commands(self, item: LightModelItem, value: list[float]) -> bool:
        """Light specific implementation. Returns whether item was updated."""
        return False

    def set_floats_commands(self, item: LightModelItem, value: list[float] | None):
        """set the item value to USD using commands, this is useful because it supports undo/redo"""
        if not self.prim_path.value:
            return

        if value is None or not item:
            return

        changed = False
        # we get the previous value from the model instead of USD
        if item == self.intensity:
            prev_value = self.intensity.value
            if prev_value == value[0]:
                return
            intensity_attr = self._light.GetIntensityAttr()
            omni.kit.commands.execute(
                "ChangeProperty", prop_path=intensity_attr.GetPath(), value=value[0], prev=prev_value
            )
            changed = True
        else:
            self._set_floats_commands(item, value)

        if changed:
            # This makes the manipulator updated
            self._item_changed(item)

    # TODO?: Maybe we need to move this "multiple logic" to manipulator class...
    def _iter_other_model_items(
        self, name, item: LightModelItem
    ) -> iter[AbstractLightManipulator, AbstractLightModel, sc.AbstractManipulatorItem]:
        matching_item = None
        for manipulator in self._viewport_layer.manipulators.values():
            corresponding_item = manipulator.model.get_item(name)
            if corresponding_item:
                if item == corresponding_item:
                    matching_item = corresponding_item
                yield manipulator, manipulator.model, corresponding_item
        # safety check to ensure we are also setting the right model item
        if not matching_item:
            raise ValueError("No items matched original model item")

    def set_floats_multiple(self, name, item: LightModelItem, value: list[float]):
        """forward set_floats to all selected manipulator models"""
        with Sdf.ChangeBlock():
            for _, model, corresponding_item in self._iter_other_model_items(name, item):
                model.set_floats(corresponding_item, value)

    def set_floats_commands_multiple(self, name, item: LightModelItem, value: list[float]):
        """forward set_floats to all selected manipulator models"""
        with Sdf.ChangeBlock():
            for _, model, corresponding_item in self._iter_other_model_items(name, item):
                model.set_floats_commands(corresponding_item, value)

    def set_float_multiple(self, name, item: LightModelItem, value: float):
        """forward set_floats to all selected manipulator models"""
        with Sdf.ChangeBlock():
            for _, model, corresponding_item in self._iter_other_model_items(name, item):
                model.set_float(corresponding_item, value)

    def set_float_commands_multiple(self, name, item: LightModelItem, value: float):
        """forward set_floats to all selected manipulator models"""
        with Sdf.ChangeBlock():
            for _, model, corresponding_item in self._iter_other_model_items(name, item):
                model.set_float_commands(corresponding_item, value)

    def set_raw_intensity_multiple(self, item: LightModelItem, value: float):
        with Sdf.ChangeBlock():
            for manip, model, corresponding_item in self._iter_other_model_items("intensity", item):
                # multiply by manipulator scale to get the actual USD attribute value
                model.set_float(corresponding_item, value * manip.intensity_scale)

    def set_raw_intensity_commands_multiple(self, item: LightModelItem, value: float):
        with Sdf.ChangeBlock():
            for manip, model, corresponding_item in self._iter_other_model_items("intensity", item):
                # multiply by manipulator scale to get the actual USD attribute value
                model.set_float_commands(corresponding_item, value * manip.intensity_scale)

    def set_item_value(self, item: LightModelItem, value):
        """
        This is used to set the model value instead of the usd. (This is used to record previous value
        for omni.kit.commands)
        """
        item.value = value

    def _set_floats(self, item: LightModelItem, value):
        pass

    def set_floats(self, item: LightModelItem, value: list[float]):
        """
        Set the item value directly to USD. This is useful when we want to update the usd but
        not record it in commands.
        """
        if not self.prim_path.value:
            return

        if value is None or not item:
            return

        pre_value = self.get_as_floats(item)
        # no need to update if the updated value is the same
        if pre_value == value:
            return

        if item == self.intensity:
            self._set_intensity(self._time, value[0])
        else:
            self._set_floats(item, value)

    def _on_stage_event(self, event):
        """Called by stage_event_stream"""
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            self._on_kit_selection_changed()

    def _invalidate_object(self):
        # Revoke the Tf.Notice listener, we don't need to update anything
        if self._stage_listener:
            self._stage_listener.Revoke()
            self._stage_listener = None

        # Clear any cached UsdLux object
        self._light = None

        # Set the prim_path to empty
        self.prim_path.value = ""
        self._item_changed(self.prim_path)

    def _light_attribute_notice_changed(self, attribute_path: Sdf.Path) -> set[sc.AbstractManipulatorItem]:
        """Light specific implementation. Returns any items affected by attribute path."""
        return set()

    def _notice_changed(self, notice: Usd.Notice.ObjectsChanged, stage: Usd.Stage):
        """Called by Tf.Notice. When USD data changes, we update the ui"""
        light_path = self.prim_path.value
        if not light_path:
            return

        changed_items = set()
        for p in notice.GetChangedInfoOnlyPaths():
            prim_path = p.GetPrimPath().pathString
            if prim_path != light_path:
                # Update on any parent transformation changes too
                if light_path.startswith(prim_path) and UsdGeom.Xformable.IsTransformationAffectedByAttrNamed(p.name):
                    changed_items.add(self.transform)
                continue

            if UsdGeom.Xformable.IsTransformationAffectedByAttrNamed(p.name):
                changed_items.add(self.transform)
            elif self.intensity and p.name == "inputs:intensity":
                changed_items.add(self.intensity)
            else:
                changed_items.update(self._light_attribute_notice_changed(p))

        for item in changed_items:
            self._item_changed(item)

    def redirect(self, prim_path):
        if self.__redirect_path:
            return self.__redirect_path
        return prim_path

    def _on_kit_selection_changed(self):
        # selection change, reset it for now
        self._light = None

        usd_context = self._usd_context
        if not usd_context:
            return self._invalidate_object()

        stage = usd_context.get_stage()
        if not stage:
            return self._invalidate_object()

        prim_paths = usd_context.get_selection().get_selected_prim_paths()
        if not prim_paths:
            return self._invalidate_object()

        prim_path = self._prim.GetPath().pathString
        if prim_path not in prim_paths:
            return self._invalidate_object()

        # transform should still get selected prim path, so that it's correctly placed.
        self._xform_prim = stage.GetPrimAtPath(prim_path)
        # give opportunity to redirect model target
        light_prim_path = self.redirect(prim_path)

        prim = stage.GetPrimAtPath(light_prim_path)
        if prim and prim.IsA(self.light_class):
            self._light = self.light_class(prim)

        if not self._light:
            return self._invalidate_object()

        if prim_path != self.prim_path.value:
            self.prim_path.value = prim_path
            self._item_changed(self.prim_path)

        # Add a Tf.Notice listener to update the light attributes
        if not self._stage_listener:
            self._stage_listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._notice_changed, stage)
        return None

    def _get_transform(self, time: Usd.TimeCode) -> list[float]:
        """Returns world transform of currently selected object"""
        if not self._xform_prim:
            return MatrixItem.identity.copy()

        # Compute matrix from world-transform in USD
        world_xform = self.light_class(self._xform_prim).ComputeLocalToWorldTransform(time)
        # lights of a certain type have a behavior where the shape of the light will be preserved even if the
        # parent scale would morph it by only respecting the largest of the contradictory scale dimensions...
        # So we account for that here to keep our representation in line with the light geometry.
        world_transform = Gf.Transform(world_xform)
        scale = world_transform.GetScale()
        linked = [linked_axis * s for linked_axis, s in zip(self.linked_axes, scale)]
        if any(linked):
            maximum_value = max(linked)
            scale = [maximum_value if linked_axis else s for linked_axis, s in zip(self.linked_axes, scale)]
            world_transform.SetScale(scale)
            world_xform = world_transform.GetMatrix()

        # Flatten Gf.Matrix4d to list
        return _flatten_matrix(world_xform)

    def _get_intensity(self, time: Usd.TimeCode) -> float:
        """Returns intensity of currently selected light"""
        if not self._light:
            return 0.0

        # Get intensity directly from USD
        return self._light.GetIntensityAttr().Get(time)

    def _set_intensity(self, time: Usd.TimeCode, value: float):
        """set intensity of currently selected light"""
        if not self._light:
            return

        # set height directly to USD
        self._light.GetIntensityAttr().Set(value, time=time)


class DiskLightModel(AbstractLightModel):
    light_class = UsdLux.DiskLight
    linked_axes = [1, 1, 0]

    def __init__(self, prim: Usd.Prim, usd_context_name: str = "", viewport_layer: LightManipulatorLayer = None):
        super().__init__(prim, usd_context_name=usd_context_name, viewport_layer=viewport_layer)
        self.radius = FloatItem()

    def update_from_prim(self):
        super().update_from_prim()
        self.set_item_value(self.radius, self._get_radius(self._time))

    def _light_attribute_notice_changed(self, attribute_path: Sdf.Path) -> set[sc.AbstractManipulatorItem]:
        """Light specific implementation. Returns any items affected by attribute path."""
        changed_items = set()
        if self.radius and attribute_path.name == "inputs:radius":
            changed_items.add(self.radius)
        return changed_items

    def _get_radius(self, time: Usd.TimeCode) -> float:
        """Returns radius of currently selected light"""
        if not self._light:
            return 0.0

        # Get radius directly from USD
        return self._light.GetRadiusAttr().Get(time)

    def _set_radius(self, time: Usd.TimeCode, value: float):
        """set radius of currently selected light"""
        if not self._light:
            return

        # set radius directly to USD
        self._light.GetRadiusAttr().Set(value, time=time)

    def _set_floats(self, item: LightModelItem, value: list[float]):
        """
        Set the item value directly to USD. This is useful when we want to update the usd but
        not record it in commands.
        """
        if item == self.radius:
            self._set_radius(self._time, value[0])

    def _get_as_floats(self, item: LightModelItem) -> list[float] | None:
        if item == self.radius:
            return [self._get_radius(self._time)]
        return None

    def _set_floats_commands(self, item: LightModelItem, value: list[float]):
        # we get the previous value from the model instead of USD
        if item == self.radius:
            prev_value = self.radius.value
            if prev_value == value[0]:
                return False
            radius_attr = self._light.GetRadiusAttr()
            omni.kit.commands.execute(
                "ChangeProperty", prop_path=radius_attr.GetPath(), value=value[0], prev=prev_value
            )
            return True
        return False


class DistantLightModel(AbstractLightModel):
    light_class = UsdLux.DistantLight


class RectLightModel(AbstractLightModel):
    light_class = UsdLux.RectLight

    def __init__(self, prim: Usd.Prim, usd_context_name: str = "", viewport_layer: LightManipulatorLayer = None):
        super().__init__(prim, usd_context_name=usd_context_name, viewport_layer=viewport_layer)
        self.width = FloatItem()
        self.height = FloatItem()

    def update_from_prim(self):
        super().update_from_prim()
        self.set_item_value(self.height, self._get_height(self._time))
        self.set_item_value(self.width, self._get_width(self._time))

    def _light_attribute_notice_changed(self, attribute_path: Sdf.Path) -> set[sc.AbstractManipulatorItem]:
        """Light specific implementation. Returns any items affected by attribute path."""
        changed_items = set()
        if self.width and attribute_path.name == "inputs:width":
            changed_items.add(self.width)
        elif self.height and attribute_path.name == "inputs:height":
            changed_items.add(self.height)
        return changed_items

    def _get_width(self, time: Usd.TimeCode) -> float:
        """Returns width of currently selected light"""
        if not self._light:
            return 0.0

        # Get radius directly from USD
        return self._light.GetWidthAttr().Get(time)

    def _set_width(self, time: Usd.TimeCode, value: float):
        """set width of currently selected light"""
        if not self._light:
            return

        # set height directly to USD
        self._light.GetWidthAttr().Set(value, time=time)

    def _get_height(self, time: Usd.TimeCode) -> float:
        """Returns height of currently selected light"""
        if not self._light:
            return 0.0

        # Get height directly from USD
        return self._light.GetHeightAttr().Get(time)

    def _set_height(self, time: Usd.TimeCode, value: float):
        """set height of currently selected light"""
        if not self._light:
            return

        # set height directly to USD
        self._light.GetHeightAttr().Set(value, time=time)

    def _set_floats(self, item: LightModelItem, value: list[float]):
        """
        Set the item value directly to USD. This is useful when we want to update the usd but
        not record it in commands.
        """
        if item == self.height:
            self._set_height(self._time, value[0])
        elif item == self.width:
            self._set_width(self._time, value[0])

    def _get_as_floats(self, item: LightModelItem) -> list[float] | None:
        if item == self.width:
            return [self._get_width(self._time)]
        if item == self.height:
            return [self._get_height(self._time)]
        return None

    def _set_floats_commands(self, item: LightModelItem, value: list[float]):
        # we get the previous value from the model instead of USD
        if item == self.height:
            prev_value = self.height.value
            if prev_value == value[0]:
                return False
            height_attr = self._light.GetHeightAttr()
            omni.kit.commands.execute(
                "ChangeProperty", prop_path=height_attr.GetPath(), value=value[0], prev=prev_value
            )
            return True
        if item == self.width:
            prev_value = self.width.value
            if prev_value == value[0]:
                return False
            width_attr = self._light.GetWidthAttr()
            omni.kit.commands.execute("ChangeProperty", prop_path=width_attr.GetPath(), value=value[0], prev=prev_value)
            return True
        return False


class SphereLightModel(DiskLightModel):
    light_class = UsdLux.SphereLight
    linked_axes = [1, 1, 1]


class CylinderLightModel(DiskLightModel):
    light_class = UsdLux.CylinderLight
    linked_axes = [0, 1, 1]

    def __init__(self, prim: Usd.Prim, usd_context_name: str = "", viewport_layer: LightManipulatorLayer = None):
        super().__init__(prim, usd_context_name=usd_context_name, viewport_layer=viewport_layer)
        self.length = FloatItem()

    def update_from_prim(self):
        super().update_from_prim()
        self.set_item_value(self.length, self._get_length(self._time))

    def _light_attribute_notice_changed(self, attribute_path: Sdf.Path) -> set[sc.AbstractManipulatorItem]:
        """Light specific implementation. Returns any items affected by attribute path."""
        changed_items = super()._light_attribute_notice_changed(attribute_path)
        if self.length and attribute_path.name == "inputs:length":
            changed_items.add(self.length)
        return changed_items

    def _get_length(self, time: Usd.TimeCode) -> float:
        """Returns radius of currently selected light"""
        if not self._light:
            return 0.0
        return self._light.GetLengthAttr().Get(time)

    def _set_length(self, time: Usd.TimeCode, value: float):
        """set radius of currently selected light"""
        if not self._light:
            return
        self._light.GetLengthAttr().Set(value, time=time)

    def _set_floats(self, item: LightModelItem, value: list[float]):
        """
        Set the item value directly to USD. This is useful when we want to update the usd but
        not record it in commands.
        """
        super()._set_floats(item, value)
        if item == self.length:
            self._set_length(self._time, value[0])

    def _get_as_floats(self, item: LightModelItem) -> list[float] | None:
        values = super()._get_as_floats(item)
        if values:
            return values
        if item == self.length:
            return [self._get_length(self._time)]
        return None

    def _set_floats_commands(self, item: LightModelItem, value: list[float]):
        if super()._set_floats_commands(item, value):
            return True
        # we get the previous value from the model instead of USD
        if item == self.length:
            prev_value = self.length.value
            if prev_value == value[0]:
                return False
            length_attr = self._light.GetLengthAttr()
            omni.kit.commands.execute(
                "ChangeProperty", prop_path=length_attr.GetPath(), value=value[0], prev=prev_value
            )
            return True
        return False
