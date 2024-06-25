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

__all__ = ["LightManipulatorLayer"]

import carb
import omni.usd
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from lightspeed.trex.viewports.manipulators.global_selection import GlobalSelection
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.scene_view.opengl import ViewportOpenGLSceneView
from pxr import UsdLux

from .light_manipulator import AbstractLightManipulator, get_manipulator_class

# TODO: We reuse this transform manipulator setting for now, but we should create an independent setting for
#  light manipulators
SETTING_MANIPULATOR_SCALE = "/persistent/exts/omni.kit.manipulator.transform/manipulator/scaleMultiplier"


class LightManipulatorLayer:
    """The viewport layer for Light Manipulators.

    To add to a viewport:
    >>> RegisterViewportLayer(LightManipulatorLayer, "omni.kit.viewport.LightManipulatorLayer")
    """

    def __init__(self, desc: dict):
        self._default_attr = {
            "_scene_view": None,
            "_viewport_api": None,
            # do this one manually since we don't want to propagate destroy because we don't own it.
            # "_viewport_layers": None,
            "_usd_context_name": None,
            "_events": None,
            "_stage_event_sub": None,
            "_manipulator_scale": None,
            # need to maintain ref for carb settings:
            # "__light_manipulator_visible_setting": None,
            "_manipulators": {},
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._viewport_api = desc.get("viewport_api")
        self._viewport_layers = desc.get("layer_provider")

        # Save the UsdContext name (we currently only work with single Context)
        self._usd_context_name = self._viewport_api.usd_context_name
        usd_context = self._get_context()

        # Track selection
        self._events = usd_context.get_stage_event_stream()
        self._stage_event_sub = self._events.create_subscription_to_pop(
            self._on_stage_event, name="Light Manipulators Stage Update"
        )

        self._manipulator_scale = carb.settings.get_settings().get(SETTING_MANIPULATOR_SCALE)

        self.__light_manipulator_visible_setting = (
            f"/app/viewport/usdcontext-{self._usd_context_name}/scene/light_manipulators/visible"
        )
        carb.settings.get_settings().set(self.__light_manipulator_visible_setting, True)

        isettings = carb.settings.get_settings()
        isettings.subscribe_to_node_change_events(
            self.__light_manipulator_visible_setting, self._light_manipulator_setting_change
        )
        isettings.subscribe_to_node_change_events(SETTING_MANIPULATOR_SCALE, self._light_manipulator_setting_change)

        # Create a default SceneView (it has a default camera-model)
        self._scene_view = ViewportOpenGLSceneView(self._viewport_api, visible=True)

        # Register the SceneView with the Viewport to get projection and view updates
        self._viewport_api.add_scene_view(self._scene_view)

        self._manipulators: dict[str, AbstractLightManipulator] = {}

        # Trigger a settings update to obtain defaults
        self._light_manipulator_setting_change(None, carb.settings.ChangeEventType.CHANGED)

        self._core = _AssetReplacementsCore(self._usd_context_name)

    def __del__(self):
        self.destroy()

    @property
    def name(self):
        return "Light Manipulators"

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
    def manipulator_scale(self):
        return self._manipulator_scale

    @manipulator_scale.setter
    def manipulator_scale(self, value):
        if self._manipulator_scale != value:
            self._manipulator_scale = value
            for manipulator in self._manipulators.values():
                manipulator.model.set_manipulator_scale(value)

    @property
    def manipulators(self):
        return self._manipulators

    def _get_context(self) -> omni.usd.UsdContext:
        # Get the UsdContext we are attached to
        return omni.usd.get_context(self._usd_context_name)

    def _light_manipulator_setting_change(self, _item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType):
        if event_type != carb.settings.ChangeEventType.CHANGED:
            return
        self.visible = bool(carb.settings.get_settings().get(self.__light_manipulator_visible_setting))
        self.manipulator_scale = self._get_global_manipulator_scale()

    def _get_global_manipulator_scale(self):
        try:
            return float(carb.settings.get_settings().get(SETTING_MANIPULATOR_SCALE))
        except TypeError:  # for when carb setting hasn't been initialized yet
            return 1.0

    def _create_manipulators(self, stage):
        # Release stale manipulators
        self._destroy_manipulators()

        # trigger settings update
        self._light_manipulator_setting_change(None, carb.settings.ChangeEventType.CHANGED)

        # Add the manipulator into the SceneView's scene
        with self._scene_view.scene:
            lights = [
                prim
                for prim in stage.TraverseAll()
                if (prim.HasAPI(UsdLux.LightAPI) if hasattr(UsdLux, "LightAPI") else prim.IsA(UsdLux.Light))
            ]
            for light in lights:
                manipulator_class = get_manipulator_class(light)
                if not manipulator_class:
                    continue  # not supported yet
                manipulator = manipulator_class(
                    self._viewport_layers, model=manipulator_class.model_class(light, self._usd_context_name, self)
                )
                # "trex" specific redirecting
                if self._usd_context_name == _TrexContexts.STAGE_CRAFT.value:
                    redirect_targets = self._core.filter_transformable_prims([light.GetPrimPath()])
                    if redirect_targets:
                        if not len(redirect_targets) == 1:
                            raise ValueError(
                                "Lights should return one path or no paths if not transformable and "
                                "we can assume redirect is not needed."
                            )
                        manipulator.model.set_path_redirect(redirect_targets[0])
                # make sure this is initialized with the right value
                manipulator.model.set_manipulator_scale(self._manipulator_scale)
                self._manipulators[str(light.GetPrimPath())] = manipulator
            GlobalSelection.g_set_lightmanipulators(self._manipulators)

    def _destroy_manipulators(self):
        if self._scene_view:
            self._scene_view.scene.clear()

        # Release stale manipulators
        self._manipulators = {}
        GlobalSelection.g_set_lightmanipulators(self._manipulators)

    def _on_stage_event(self, event):
        """Called by stage_event_stream"""
        if not self._scene_view:
            return

        match event.type:
            case omni.usd.StageEventType.SELECTION_CHANGED.value:
                GlobalSelection.get_instance().on_selection_changed(
                    self._get_context(), self._viewport_api, list(self._manipulators.values())
                )
            case (
                omni.usd.StageEventType.HIERARCHY_CHANGED.value
                | omni.usd.StageEventType.ACTIVE_LIGHT_COUNTS_CHANGED.value
            ):
                stage = self._get_context().get_stage()
                # Create the manipulators
                self._create_manipulators(stage)
            case omni.usd.StageEventType.CLOSED.value:
                self._destroy_manipulators()

    def destroy(self):
        if self._scene_view and self._viewport_api:
            # Be a good citizen, and un-register the SceneView from Viewport updates
            self._viewport_api.remove_scene_view(self._scene_view)
        self._destroy_manipulators()
        self._viewport_layers = None
        _reset_default_attrs(self)
