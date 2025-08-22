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

__all__ = ["ParticleGizmosLayer"]

import carb
import lightspeed.trex.utils.common.prim_utils as _prim_utils
import omni.usd
from lightspeed.common.constants import PARTICLE_SCHEMA_NAME, VIEWPORT_MENU_SHOW_BY_TYPE
from lightspeed.trex.viewports.manipulators.global_selection import GlobalSelection
from omni.kit.scene_view.opengl import ViewportOpenGLSceneView
from omni.kit.viewport.menubar.core import CategoryCollectionItem, CategoryStateItem
from omni.kit.viewport.menubar.display import get_instance as _get_menubar_instance
from pxr import Tf, Usd, UsdGeom, UsdShade

from .manipulator import ParticleGizmoManipulator
from .model import ParticleGizmoModel

SETTING_PARTICLE_GIZMO_VISIBLE = "/persistent/app/viewport/gizmo/particlesGizmoVisible"
# FIXME: Gizmo scale not working
CARB_SETTING_GIZMO_SCALE = "/persistent/app/viewport/gizmo/scale"
CARB_SETTING_CONST_GIZMO_SCALE = "/persistent/app/viewport/gizmo/constantScale"
CARB_SETTING_CONST_SCALE_ENABLED = "/persistent/app/viewport/gizmo/constantScaleEnabled"


class ParticleGizmosLayer:
    """The Particle Gizmo Manipulator, placed into a Viewport"""

    def __init__(self, desc: dict):
        self._scene_view = None
        self._viewport_api = desc.get("viewport_api")

        # Save the UsdContext name (we currently only work with single Context)
        self._usd_context_name = self._viewport_api.usd_context_name

        # Track selection
        self._events = omni.usd.get_context(self._usd_context_name).get_stage_event_stream()
        self._stage_event_sub = self._events.create_subscription_to_pop(
            self._on_stage_event, name="Particle Gizmos Stage Update"
        )
        self._stage_listener = None
        self._current_stage = None
        self._ignore_update = False

        self._gizmo_scale = 1.0

        isettings = carb.settings.get_settings()
        isettings.subscribe_to_node_change_events(SETTING_PARTICLE_GIZMO_VISIBLE, self._particles_gizmo_setting_change)
        isettings.subscribe_to_node_change_events(CARB_SETTING_GIZMO_SCALE, self._particles_gizmo_setting_change)
        isettings.subscribe_to_node_change_events(CARB_SETTING_CONST_GIZMO_SCALE, self._particles_gizmo_setting_change)
        isettings.subscribe_to_node_change_events(
            CARB_SETTING_CONST_SCALE_ENABLED, self._particles_gizmo_setting_change
        )

        # Create a default SceneView (it has a default camera-model)
        self._scene_view = ViewportOpenGLSceneView(self._viewport_api, visible=True)

        # Register the SceneView with the Viewport to get projection and view updates
        self._viewport_api.add_scene_view(self._scene_view)

        self._manipulators = {}

        # Trigger a settings update to obtain defaults
        self._particles_gizmo_setting_change(None, carb.settings.ChangeEventType.CHANGED)

        self._add_menubar_items()

    def __del__(self):
        self.destroy()

    def _add_menubar_items(self):
        inst = _get_menubar_instance()
        if not inst:
            return
        gizmos_collection_item = CategoryCollectionItem(
            "Particles",
            [
                CategoryStateItem("Gizmos", setting_path=SETTING_PARTICLE_GIZMO_VISIBLE),
            ],
        )
        self.__menubar_items = [gizmos_collection_item]
        for menubar_item in self.__menubar_items:
            inst.register_custom_category_item(VIEWPORT_MENU_SHOW_BY_TYPE, menubar_item)

    def _remove_menubar_items(self):
        inst = _get_menubar_instance()
        for item in self.__menubar_items:
            inst.deregister_custom_category_item(VIEWPORT_MENU_SHOW_BY_TYPE, item)

    def _particles_gizmo_setting_change(self, item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType):
        if event_type != carb.settings.ChangeEventType.CHANGED:
            return
        self.visible = bool(carb.settings.get_settings().get(SETTING_PARTICLE_GIZMO_VISIBLE))
        self.gizmo_scale = self._get_global_gizmo_scale()

    def _get_global_gizmo_scale(self):
        try:
            settings = carb.settings.get_settings()
            if settings.get_as_bool(CARB_SETTING_CONST_SCALE_ENABLED):
                return settings.get_as_float(CARB_SETTING_CONST_GIZMO_SCALE) * 0.1
            return settings.get_as_float(CARB_SETTING_GIZMO_SCALE)
        except TypeError:  # for when carb setting hasn't been initialized yet
            return 1.0

    @property
    def name(self):
        return "Particle Gizmos"

    @property
    def categories(self):
        return ["scene"]

    @property
    def visible(self):
        return self._scene_view.visible if self._scene_view is not None else False

    @visible.setter
    def visible(self, value):
        if self._scene_view is not None:
            self._scene_view.visible = value

    @property
    def gizmo_scale(self):
        return self._gizmo_scale

    @gizmo_scale.setter
    def gizmo_scale(self, value):
        if self._gizmo_scale != value:
            self._gizmo_scale = value
            for manipulator in self._manipulators.values():
                manipulator.model.set_gizmo_scale(value)

    def destroy(self):
        if self._scene_view and self._viewport_api:
            # Be a good citizen, and un-register the SceneView from Viewport updates
            self._viewport_api.remove_scene_view(self._scene_view)
        self._remove_menubar_items()
        self._revoke_listeners()
        self._destroy_manipulators()
        # Remove our references to these objects
        self._viewport_api = None
        self._scene_view = None
        self._stage_event_sub = None

    def _revoke_listeners(self):
        # Revoke any existing listeners
        if self._stage_listener:
            self._stage_listener.Revoke()
            self._stage_listener = None

    def _on_stage_event(self, event):
        """Called by stage_event_stream"""
        if not self._scene_view:
            return
        if event.type == int(omni.usd.StageEventType.OPENED):
            self._current_stage = omni.usd.get_context(self._usd_context_name).get_stage()
            self._create_listener(self._current_stage)
        elif event.type == int(omni.usd.StageEventType.HIERARCHY_CHANGED):
            # TODO: This is called meny times during set up, when only an anon stage is open, so it would be
            #  good to limit the number of times this is called.
            # Create the manipulators
            self._create_manipulators(self._current_stage)
        elif event.type == int(omni.usd.StageEventType.CLOSED):
            self._revoke_listeners()
            self._destroy_manipulators()

    def _create_listener(self, stage):
        # Do no work if there is no stage
        if not stage:
            return
        # Add a Tf.Notice listener to update the transforms of all particle systems
        if self._stage_listener:
            self._revoke_listeners()
        self._stage_listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._notice_changed, stage)

    def _notice_changed(self, notice, stage):
        """Called by Tf.Notice"""
        # Check to see if we need to update some transforms
        if self._ignore_update or stage != self._current_stage:
            return
        self._ignore_update = True
        for path in notice.GetChangedInfoOnlyPaths():
            if not path.IsPropertyPath():
                continue
            prim_path = str(path.GetPrimPath())
            if prim_path in self._manipulators:
                self._manipulators[prim_path].model.update_from_prim()
            else:
                # Update on any parent transformation changes too
                for manipulator in self._manipulators.values():
                    if not manipulator.model.get_prim_path().startswith(prim_path):
                        continue
                    if UsdGeom.Xformable.IsTransformationAffectedByAttrNamed(path.name):
                        manipulator.model.update_from_prim()
        self._ignore_update = False

    def _create_manipulators(self, stage):
        # Do no work if there is no stage
        if not stage:
            return

        # Release stale manipulators
        self._destroy_manipulators()

        # trigger settings update
        self._particles_gizmo_setting_change(None, carb.settings.ChangeEventType.CHANGED)

        # Add the manipulator into the SceneView's scene
        with self._scene_view.scene:

            particle_prims = []
            for prim in stage.TraverseAll():
                if not prim.IsA(UsdGeom.Mesh):
                    continue

                # Check if prim has RemixParticleSystem schema directly applied
                if prim.HasAPI(PARTICLE_SCHEMA_NAME):
                    particle_prims.append(prim)
                    continue

                # Check if prim has a material with RemixParticleSystem schema
                material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
                if material and material.GetPrim().HasAPI(PARTICLE_SCHEMA_NAME):
                    particle_prims.append(prim)

            for particle_prim in particle_prims:
                if _prim_utils.is_mesh_prototype(particle_prim):
                    continue

                manipulator = ParticleGizmoManipulator(
                    self._viewport_api,
                    model=ParticleGizmoModel(particle_prim, self._usd_context_name, self._gizmo_scale),
                )
                self._manipulators[str(particle_prim.GetPrimPath())] = manipulator

            GlobalSelection.get_instance().set_manipulators(self._manipulators, category="particles")

    def _destroy_manipulators(self):
        if self._scene_view:
            self._scene_view.scene.clear()

        # Release stale manipulators
        for manipulator in self._manipulators.values():
            manipulator.destroy()
        self._manipulators = {}
        GlobalSelection.get_instance().set_manipulators(self._manipulators, category="particles")
