# Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
__all__ = ["LightGizmosLayer"]

import carb
import omni.usd
from lightspeed.trex.viewports.manipulators.global_selection import GlobalSelection
from omni.kit.scene_view.opengl import ViewportOpenGLSceneView
from pxr import Tf, Usd, UsdLux

from .manipulator import LightGizmosManipulator
from .model import LightGizmosModel

CARB_SETTING_GIZMO_SCALE = "/persistent/app/viewport/gizmo/scale"
CARB_SETTING_CONST_GIZMO_SCALE = "/persistent/app/viewport/gizmo/constantScale"
CARB_SETTING_CONST_SCALE_ENABLED = "/persistent/app/viewport/gizmo/constantScaleEnabled"


class LightGizmosLayer:
    """The Object Info Manupulator, placed into a Viewport"""

    def __init__(self, desc: dict):
        self._scene_view = None
        self._viewport_api = desc.get("viewport_api")

        # Save the UsdContext name (we currently only work with single Context)
        self._usd_context_name = self._viewport_api.usd_context_name
        usd_context = self._get_context()

        # Track selection
        self._events = usd_context.get_stage_event_stream()
        self._stage_event_sub = self._events.create_subscription_to_pop(
            self._on_stage_event, name="Light Gizmos Stage Update"
        )
        self._stage_listener = None

        self._gizmo_scale = 1.0

        self._light_visible_setting = f"/app/viewport/usdcontext-{self._usd_context_name}/scene/lights/visible"
        carb.settings.get_settings().set(self._light_visible_setting, True)

        isettings = carb.settings.get_settings()
        isettings.subscribe_to_node_change_events(self._light_visible_setting, self._light_gizmo_setting_change)
        isettings.subscribe_to_node_change_events(CARB_SETTING_GIZMO_SCALE, self._light_gizmo_setting_change)
        isettings.subscribe_to_node_change_events(CARB_SETTING_CONST_GIZMO_SCALE, self._light_gizmo_setting_change)
        isettings.subscribe_to_node_change_events(CARB_SETTING_CONST_SCALE_ENABLED, self._light_gizmo_setting_change)

        # Create a default SceneView (it has a default camera-model)
        self._scene_view = ViewportOpenGLSceneView(self._viewport_api, visible=True)

        # Register the SceneView with the Viewport to get projection and view updates
        self._viewport_api.add_scene_view(self._scene_view)

        self._manipulators = {}

        # Trigger a settings update to obtain defaults
        self._light_gizmo_setting_change(None, carb.settings.ChangeEventType.CHANGED)

    def __del__(self):
        self.destroy()

    def _light_gizmo_setting_change(self, item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType):
        if event_type != carb.settings.ChangeEventType.CHANGED:
            return
        self.visible = bool(carb.settings.get_settings().get(self._light_visible_setting))
        self.gizmo_scale = self._get_global_gizmo_scale()

    def _get_global_gizmo_scale(self):
        try:
            if bool(carb.settings.get_settings().get(CARB_SETTING_CONST_SCALE_ENABLED)):
                return float(carb.settings.get_settings().get(CARB_SETTING_CONST_GIZMO_SCALE)) * 0.1
            return float(carb.settings.get_settings().get(CARB_SETTING_GIZMO_SCALE))
        except TypeError:  # for when carb setting hasn't been initialized yet
            return 1.0

    @property
    def name(self):
        return "Light Gizmos"

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

    def _get_context(self) -> Usd.Stage:
        # Get the UsdContext we are attached to
        return omni.usd.get_context(self._usd_context_name)

    def destroy(self):
        if self._scene_view and self._viewport_api:
            # Be a good citizen, and un-register the SceneView from Viewport updates
            self._viewport_api.remove_scene_view(self._scene_view)
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
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            GlobalSelection.get_instance().on_selection_changed(
                self._get_context(), self._viewport_api, list(self._manipulators.values())
            )
        elif (
            event.type == int(omni.usd.StageEventType.OPENED)
            or event.type == int(omni.usd.StageEventType.HIERARCHY_CHANGED)
            or event.type == int(omni.usd.StageEventType.ACTIVE_LIGHT_COUNTS_CHANGED)
        ):
            stage = self._get_context().get_stage()
            # Create the manipulators
            self._create_manipulators(stage)
        elif event.type == int(omni.usd.StageEventType.CLOSED):
            self._destroy_manipulators()

    def _notice_changed(self, notice, stage):
        """Called by Tf.Notice"""
        # Paths of all changed prims
        changed_paths = [str(p.GetPrimPath()) for p in notice.GetChangedInfoOnlyPaths()]
        # Check to see if we need to update some transforms
        for light_path in changed_paths:
            if light_path in self._manipulators:
                self._manipulators[light_path].model.update_from_prim()

    def _create_manipulators(self, stage):
        # Release stale manipulators
        self._destroy_manipulators()

        # Add a Tf.Notice listener to update the transforms of all lights
        self._stage_listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._notice_changed, stage)

        # trigger settings update
        self._light_gizmo_setting_change(None, carb.settings.ChangeEventType.CHANGED)

        # Add the manipulator into the SceneView's scene
        with self._scene_view.scene:
            lights = [
                prim
                for prim in stage.TraverseAll()
                if (prim.HasAPI(UsdLux.LightAPI) if hasattr(UsdLux, "LightAPI") else prim.IsA(UsdLux.Light))
            ]
            for light in lights:
                manipulator = LightGizmosManipulator(
                    self._viewport_api, model=LightGizmosModel(light, self._usd_context_name, self._gizmo_scale)
                )
                self._manipulators[str(light.GetPrimPath())] = manipulator

    def _destroy_manipulators(self):
        self._revoke_listeners()

        if self._scene_view:
            self._scene_view.scene.clear()

        # Release stale manipulators
        for manipulator in self._manipulators.values():
            manipulator.destroy()
        self._manipulators = {}
