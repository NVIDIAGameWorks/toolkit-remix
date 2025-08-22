"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["ParticleGizmoModel"]

import omni.kit.commands
import omni.usd
from lightspeed.common.constants import PARTICLE_HIDE_EMITTER_ATTR
from omni.ui import scene as sc
from pxr import Gf, Sdf, Tf, Usd, UsdGeom


class ParticleGizmoModel(sc.AbstractManipulatorModel):
    """
    User part. The model tracks the transform and info of the selected object.
    """

    class TransformItem(sc.AbstractManipulatorItem):
        def __init__(self, transform):
            super().__init__()
            self.value = transform

    class BoolItem(sc.AbstractManipulatorItem):
        def __init__(self, value):
            super().__init__()
            self.value = value

    def __init__(self, prim: Usd.Prim, usd_context_name, scale: float):
        super().__init__()

        self._usd_context_name = usd_context_name
        self._usd_context = omni.usd.get_context(self._usd_context_name)
        self._gizmo_scale = scale

        # Current selection
        self._prim = prim
        self._current_path = str(prim.GetPrimPath())
        self.__redirect_path = None

        self.transform = ParticleGizmoModel.TransformItem(self._get_transform())
        self.gizmo_transform = ParticleGizmoModel.TransformItem(self._get_gizmo_transform())
        self.visible = ParticleGizmoModel.BoolItem(self._is_emitter_visible())
        self.selected = ParticleGizmoModel.BoolItem(self._is_selected())

        # gizmo scale will modify the transform directly
        self.set_gizmo_scale(scale)

        # Track selection change
        self._events = self._usd_context.get_stage_event_stream()
        self._stage_event_sub = self._events.create_subscription_to_pop(
            self._on_stage_event, name="Particle Manipulator Selection Change"
        )

        self._stage_listener: Tf.Listener | None = None
        # Add a Tf.Notice listener to update the particle attributes
        stage = self._get_context().get_stage()
        if stage:
            self._stage_listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_object_changed, stage)

    def destroy(self):
        if self._stage_listener is not None:
            self._stage_listener.Revoke()
            self._stage_listener = None
        self._stage_event_sub.unsubscribe()

    def _get_context(self) -> Usd.Stage:
        # Get the UsdContext we are attached to
        return omni.usd.get_context(self._usd_context_name)

    def set_item_value(self, item, value):
        """
        This is used to set the model value instead of the usd. (This is used to record previous value
        for omni.kit.commands)
        """
        item.value = value

    def set_path_redirect(self, path: Sdf.Path):
        self.__redirect_path = path

    def get_path_redirect(self):
        return self.__redirect_path

    def update_from_prim(self):
        self.set_item_value(self.transform, self._get_transform())
        self.set_item_value(self.gizmo_transform, self._get_gizmo_transform())
        self.set_item_value(self.visible, self._is_emitter_visible())

    def get_item(self, identifier: str) -> sc.AbstractManipulatorItem | None:
        return getattr(self, identifier, None)

    def _get_as_floats(
        self, item: sc.AbstractManipulatorItem
    ) -> list[float] | None:  # noqa PLE0602 - linter doesn't understand new type alias
        return None

    def get_as_floats(self, item: sc.AbstractManipulatorItem) -> list[float]:
        """get the item value directly from USD"""
        if item == self.transform:
            return self._get_transform()
        if item == self.gizmo_transform:
            return self._get_gizmo_transform()

        value: list[float] = self._get_as_floats(item)
        if value is not None:
            return value

        # Get the value directly from the item
        return [item.value]

    def get_prim_path(self):
        return self._current_path

    def set_gizmo_scale(self, scale):
        self._gizmo_scale = scale
        # recalculate the transform since that will need to change
        self.set_item_value(self.transform, self._get_transform())

    def _is_emitter_visible(self):
        """Returns whether the emitter mesh is visible in the scene"""
        stage = self._get_context().get_stage()
        if not stage or not self._current_path:
            return False
        if not self._prim.IsActive():
            return False
        hide_emitter = self._prim.GetAttribute(PARTICLE_HIDE_EMITTER_ATTR)
        if hide_emitter.Get():
            return False
        imageable = UsdGeom.Imageable(self._prim)
        return imageable.ComputeVisibility() != UsdGeom.Tokens.invisible

    def _get_transform(self):
        """Returns transform of currently selected object"""
        particle_transform = UsdGeom.Imageable(self._prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        return [col for row in particle_transform for col in row]

    def _get_gizmo_transform(self):
        stage = self._get_context().get_stage()
        # default should also account for gizmo scale
        final_transform = Gf.Matrix4d().SetScale(Gf.Vec3d(self._gizmo_scale))
        if not stage or not self._current_path:
            return [col for row in final_transform for col in row]

        # Get transform directly from USD
        particle_transform = UsdGeom.Imageable(self._prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        final_transform.SetTranslateOnly(particle_transform.ExtractTranslation())

        return [col for row in final_transform for col in row]

    def get_emitter_mesh(self):
        """Returns the mesh of the emitter"""
        return UsdGeom.Mesh(self._prim)

    def _invalidate_object(self):
        # Revoke the Tf.Notice listener, we don't need to update anything
        if self._stage_listener:
            self._stage_listener.Revoke()
            self._stage_listener = None

        # TODO:
        # Send a changed signal that will invalidate manipulator and redraw it.
        # self._item_changed(self.visible)

    def _on_stage_event(self, event):
        """Called by stage_event_stream"""
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            self._on_kit_selection_changed()

    def _is_selected(self):
        """Returns whether the particle system is selected in the scene"""
        if self._usd_context:
            prim_paths = self._usd_context.get_selection().get_selected_prim_paths()
            if prim_paths:
                prim_path = self._prim.GetPath().pathString
                return prim_path in prim_paths
        return False

    def _on_kit_selection_changed(self):
        # selection change, reset it for now

        usd_context = self._usd_context
        if not usd_context:
            self._invalidate_object()
            return

        stage = usd_context.get_stage()
        if not stage:
            self._invalidate_object()
            return

        selected = self._is_selected()
        if selected != self.selected.value:
            self.set_item_value(self.selected, selected)
            self._item_changed(self.selected)

    def _on_object_changed(self, notice: Usd.Notice.ObjectsChanged, stage: Usd.Stage):
        """Called by Tf.Notice. When USD data changes, we update the ui"""
        if not self._prim:
            return

        changed_items = set()
        for p in notice.GetChangedInfoOnlyPaths():
            prim_path = p.GetPrimPath()
            prim_path_str = prim_path.pathString
            if prim_path_str != self._current_path:
                # Update on any parent transformation changes too
                if Sdf.Path(self._current_path).HasPrefix(
                    prim_path
                ) and UsdGeom.Xformable.IsTransformationAffectedByAttrNamed(p.name):
                    changed_items.add(self.transform)
                continue

            if UsdGeom.Xformable.IsTransformationAffectedByAttrNamed(p.name):
                changed_items.add(self.transform)

            if p.name in (UsdGeom.Tokens.visibility, PARTICLE_HIDE_EMITTER_ATTR):
                changed_items.add(self.visible)

        for item in changed_items:
            self._item_changed(item)
