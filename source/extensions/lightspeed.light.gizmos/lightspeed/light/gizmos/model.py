# Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
__all__ = ["LightGizmosModel"]

from enum import IntEnum

import omni.kit.commands
import omni.usd
from omni.ui import scene as sc
from pxr import Gf, Usd, UsdGeom, UsdLux


class LightType(IntEnum):
    DiskLight = 0
    RectLight = 1
    CylinderLight = 2
    SphereLight = 3
    DistantLight = 4
    DomeLight = 5
    UnknownLight = 6


class LightGizmosModel(sc.AbstractManipulatorModel):
    """
    User part. The model tracks the transform and info of the selected object.
    """

    class TransformItem(sc.AbstractManipulatorItem):
        def __init__(self, transform):
            super().__init__()
            self.value = transform

    class VisibleItem(sc.AbstractManipulatorItem):
        def __init__(self):
            super().__init__()
            self.value = False

    class LightTypeItem(sc.AbstractManipulatorItem):
        def __init__(self):
            super().__init__()
            self.value = LightType.UnknownLight

    def __init__(self, prim: Usd.Prim, usd_context_name, scale: float):
        super().__init__()

        self._usd_context_name = usd_context_name
        self._gizmo_scale = scale

        # Current selection
        self._prim = prim
        self._current_path = str(prim.GetPrimPath())

        self.transform = LightGizmosModel.TransformItem(self._get_transform())
        self.visible = LightGizmosModel.VisibleItem()
        self.light_type = LightGizmosModel.LightTypeItem()

        # gizmo scale will modify the transform directly
        self.set_gizmo_scale(scale)

    def _get_context(self) -> Usd.Stage:
        # Get the UsdContext we are attached to
        return omni.usd.get_context(self._usd_context_name)

    def update_from_prim(self):
        self.set_value(self.transform, self._get_transform())
        self.set_value(self.light_type, self._get_light_type())
        self.set_value(self.visible, self._is_visible())

    def get_item(self, identifier):
        match (identifier):
            case "transform":
                return self.transform
            case "visible":
                return self.visible
            case "light_type":
                return self.light_type
            case "name":
                return self._current_path
        return None

    def get_as_floats(self, item):
        if item:
            # Get the value directly from the item
            return item.value
        return []

    def get_as_bools(self, item):
        if item:
            # Get the value directly from the item
            return item.value
        return []

    def set_value(self, item, value):
        if not self._current_path:
            return

        if not item or item.value == value:
            return

        # Set directly to the item
        item.value = value
        # This makes the manipulator updated
        self._item_changed(item)

    def get_prim_path(self):
        return self._current_path

    def set_gizmo_scale(self, scale):
        self._gizmo_scale = scale
        # recalculate the transform since that will need to change
        self.set_value(self.transform, self._get_transform())

    def _is_visible(self):
        stage = self._get_context().get_stage()
        if not stage or not self._current_path:
            return False
        if not self._prim.IsActive():
            return False
        imageable = UsdGeom.Imageable(self._prim)
        return imageable.ComputeVisibility() != UsdGeom.Tokens.invisible

    def _get_transform(self):
        """Returns transform of currently selected object"""
        stage = self._get_context().get_stage()
        # default should also account for gizmo scale
        final_transform = Gf.Matrix4d().SetScale(Gf.Vec3d(self._gizmo_scale))
        if not stage or not self._current_path:
            return [j for sub in final_transform for j in sub]

        # Get transform directly from USD
        light_transform = UsdGeom.Imageable(self._prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        final_transform.SetTranslateOnly(light_transform.ExtractTranslation())

        return [j for sub in final_transform for j in sub]

    def _get_light_type(self):
        if self._prim.IsA(UsdLux.DomeLight):
            return LightType.DomeLight
        if self._prim.IsA(UsdLux.DiskLight):
            return LightType.DiskLight
        if self._prim.IsA(UsdLux.RectLight):
            return LightType.RectLight
        if self._prim.IsA(UsdLux.SphereLight):
            return LightType.SphereLight
        if self._prim.IsA(UsdLux.CylinderLight):
            return LightType.CylinderLight
        if self._prim.IsA(UsdLux.DistantLight):
            return LightType.DistantLight
        return LightType.UnknownLight
