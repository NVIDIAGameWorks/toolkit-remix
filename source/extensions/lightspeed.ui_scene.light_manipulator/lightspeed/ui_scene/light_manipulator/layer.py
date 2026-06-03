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

from contextlib import suppress

import carb
import omni.usd
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.scene_view.opengl import ViewportOpenGLSceneView
from pxr import UsdLux

from .constants import (
    CONE_INNER_COLOR_DEFAULT,
    CONE_OUTER_COLOR_DEFAULT,
    CONE_SIDES_DEFAULT,
    CONE_SIDES_MAX_INPUT,
    CONE_SIDES_MIN_INPUT,
    CONE_THRESHOLD_DEFAULT,
    CONE_THRESHOLD_MIN,
)
from .light_manipulator import AbstractLightManipulator, get_manipulator_class

# TODO: We reuse this transform manipulator setting for now, but we should create an independent setting for
#  light manipulators
SETTING_MANIPULATOR_SCALE = "/persistent/exts/omni.kit.manipulator.transform/manipulator/scaleMultiplier"
SETTING_LIGHT_MANIPULATOR_VISIBLE = "/persistent/app/viewport/manipulator/lightManipulatorsVisible"
SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE = "/persistent/app/viewport/manipulator/lightIntensityControlsVisible"
SETTING_SPOTLIGHT_CONE_VISIBLE = "/persistent/app/viewport/manipulator/spotlightConeVisible"
SETTING_SPOTLIGHT_CONE_ILLUMINANCE_THRESHOLD = "/persistent/app/viewport/manipulator/spotlightConeIlluminanceThreshold"
SETTING_SPOTLIGHT_CONE_SIDES = "/persistent/app/viewport/manipulator/spotlightConeSides"
SETTING_SPOTLIGHT_CONE_OUTER_COLOR = "/persistent/app/viewport/manipulator/spotlightConeOuterColor"
SETTING_SPOTLIGHT_CONE_INNER_COLOR = "/persistent/app/viewport/manipulator/spotlightConeInnerColor"


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
            "_intensity_controls_visible": False,
            # need to maintain ref for carb settings:
            # "__light_manipulator_visible_setting": None,
            "_manipulators": {},
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._setting_subscriptions: list[carb.settings.SubscriptionId] = []

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

        isettings = carb.settings.get_settings()
        isettings.set_default(SETTING_LIGHT_MANIPULATOR_VISIBLE, True)
        isettings.set_default(SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE, False)
        self._setting_subscriptions.append(
            isettings.subscribe_to_node_change_events(
                SETTING_LIGHT_MANIPULATOR_VISIBLE, self._light_manipulator_setting_change
            )
        )
        self._setting_subscriptions.append(
            isettings.subscribe_to_node_change_events(
                SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE, self._light_manipulator_setting_change
            )
        )
        self._setting_subscriptions.append(
            isettings.subscribe_to_node_change_events(SETTING_MANIPULATOR_SCALE, self._light_manipulator_setting_change)
        )
        self._setting_subscriptions.append(
            isettings.subscribe_to_node_change_events(
                SETTING_SPOTLIGHT_CONE_VISIBLE, self._spotlight_cone_setting_change
            )
        )
        self._setting_subscriptions.append(
            isettings.subscribe_to_node_change_events(
                SETTING_SPOTLIGHT_CONE_ILLUMINANCE_THRESHOLD, self._spotlight_cone_threshold_setting_change
            )
        )
        self._setting_subscriptions.append(
            isettings.subscribe_to_node_change_events(
                SETTING_SPOTLIGHT_CONE_SIDES, self._spotlight_cone_sides_setting_change
            )
        )
        # Color settings are 3-float arrays; carb writes them element-by-element so we
        # subscribe to each child path rather than the parent.
        for i in range(3):
            self._setting_subscriptions.append(
                isettings.subscribe_to_node_change_events(
                    f"{SETTING_SPOTLIGHT_CONE_OUTER_COLOR}/{i}",
                    self._spotlight_cone_outer_color_setting_change,
                )
            )
            self._setting_subscriptions.append(
                isettings.subscribe_to_node_change_events(
                    f"{SETTING_SPOTLIGHT_CONE_INNER_COLOR}/{i}",
                    self._spotlight_cone_inner_color_setting_change,
                )
            )

        # Create a default SceneView (it has a default camera-model)
        self._scene_view = ViewportOpenGLSceneView(self._viewport_api, visible=True)

        # Register the SceneView with the Viewport to get projection and view updates
        self._viewport_api.add_scene_view(self._scene_view)

        self._manipulators: dict[str, AbstractLightManipulator] = {}
        # Default to visible when the setting hasn't been initialized (test contexts, pre-toml).
        cone_setting_value = carb.settings.get_settings().get(SETTING_SPOTLIGHT_CONE_VISIBLE)
        self._cone_visible: bool = True if cone_setting_value is None else bool(cone_setting_value)
        self._cone_threshold: float = self._read_cone_threshold_setting()
        self._cone_sides: int = self._read_cone_sides_setting()
        self._cone_outer_color: tuple[float, float, float] = self._read_cone_color_setting(
            SETTING_SPOTLIGHT_CONE_OUTER_COLOR, CONE_OUTER_COLOR_DEFAULT
        )
        self._cone_inner_color: tuple[float, float, float] = self._read_cone_color_setting(
            SETTING_SPOTLIGHT_CONE_INNER_COLOR, CONE_INNER_COLOR_DEFAULT
        )

        # Trigger a settings update to obtain defaults
        self._light_manipulator_setting_change(None, carb.settings.ChangeEventType.CHANGED)

        # Lights menu (incl. Spotlight Cones toggle) is owned by lightspeed.light.gizmos to avoid
        # duplicate Show-By-Type entries; this layer only reacts to the shared settings.
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
    def intensity_controls_visible(self):
        return self._intensity_controls_visible

    @intensity_controls_visible.setter
    def intensity_controls_visible(self, value):
        if self._intensity_controls_visible != value:
            self._intensity_controls_visible = value
            for manipulator in self._manipulators.values():
                manipulator.invalidate()

    @property
    def manipulators(self):
        return self._manipulators

    def _get_context(self) -> omni.usd.UsdContext:
        # Get the UsdContext we are attached to
        return omni.usd.get_context(self._usd_context_name)

    def _light_manipulator_setting_change(self, _item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType):
        if event_type != carb.settings.ChangeEventType.CHANGED:
            return
        settings = carb.settings.get_settings()
        self.visible = bool(settings.get(SETTING_LIGHT_MANIPULATOR_VISIBLE))
        self.intensity_controls_visible = bool(settings.get(SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE))
        self.manipulator_scale = self._get_global_manipulator_scale()

    def _spotlight_cone_setting_change(self, _item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType):
        if event_type != carb.settings.ChangeEventType.CHANGED:
            return
        self._cone_visible = bool(carb.settings.get_settings().get(SETTING_SPOTLIGHT_CONE_VISIBLE))
        for manipulator in self._manipulators.values():
            manipulator.cone_visible = self._cone_visible

    def _spotlight_cone_threshold_setting_change(
        self, _item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType
    ):
        if event_type != carb.settings.ChangeEventType.CHANGED:
            return
        self._cone_threshold = self._read_cone_threshold_setting()
        for manipulator in self._manipulators.values():
            manipulator.cone_threshold = self._cone_threshold

    def _spotlight_cone_sides_setting_change(
        self, _item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType
    ):
        if event_type != carb.settings.ChangeEventType.CHANGED:
            return
        self._cone_sides = self._read_cone_sides_setting()
        for manipulator in self._manipulators.values():
            manipulator.cone_sides = self._cone_sides

    def _spotlight_cone_outer_color_setting_change(
        self, _item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType
    ):
        if event_type != carb.settings.ChangeEventType.CHANGED:
            return
        self._cone_outer_color = self._read_cone_color_setting(
            SETTING_SPOTLIGHT_CONE_OUTER_COLOR, CONE_OUTER_COLOR_DEFAULT
        )
        for manipulator in self._manipulators.values():
            manipulator.cone_outer_color = self._cone_outer_color

    def _spotlight_cone_inner_color_setting_change(
        self, _item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType
    ):
        if event_type != carb.settings.ChangeEventType.CHANGED:
            return
        self._cone_inner_color = self._read_cone_color_setting(
            SETTING_SPOTLIGHT_CONE_INNER_COLOR, CONE_INNER_COLOR_DEFAULT
        )
        for manipulator in self._manipulators.values():
            manipulator.cone_inner_color = self._cone_inner_color

    def _read_cone_threshold_setting(self) -> float:
        """Read the illuminance-threshold setting, clamped to the divide-by-zero floor."""
        value = carb.settings.get_settings().get(SETTING_SPOTLIGHT_CONE_ILLUMINANCE_THRESHOLD)
        if value is None:
            return CONE_THRESHOLD_DEFAULT
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return CONE_THRESHOLD_DEFAULT
        return max(CONE_THRESHOLD_MIN, numeric)

    def _read_cone_sides_setting(self) -> int:
        """Read the cone-subdivisions setting, clamped to UI bounds."""
        value = carb.settings.get_settings().get(SETTING_SPOTLIGHT_CONE_SIDES)
        if value is None:
            return CONE_SIDES_DEFAULT
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return CONE_SIDES_DEFAULT
        return max(CONE_SIDES_MIN_INPUT, min(CONE_SIDES_MAX_INPUT, numeric))

    @staticmethod
    def _read_cone_color_setting(key: str, default: tuple[float, float, float]) -> tuple[float, float, float]:
        """Read a 3-float RGB color setting, falling back to `default` on missing/malformed values."""
        value = carb.settings.get_settings().get(key)
        if value is None:
            return default
        try:
            components = tuple(float(c) for c in value)
        except (TypeError, ValueError):
            return default
        if len(components) != 3:
            return default
        return components

    def _get_global_manipulator_scale(self):
        try:
            return float(carb.settings.get_settings().get(SETTING_MANIPULATOR_SCALE))
        except TypeError:  # for when carb setting hasn't been initialized yet
            return 1.0

    def _create_manipulators(self, stage):
        if not stage:
            return

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
                manipulator.cone_visible = self._cone_visible
                manipulator.cone_threshold = self._cone_threshold
                manipulator.cone_sides = self._cone_sides
                manipulator.cone_outer_color = self._cone_outer_color
                manipulator.cone_inner_color = self._cone_inner_color
                self._manipulators[str(light.GetPrimPath())] = manipulator

    def _destroy_manipulators(self):
        for manipulator in self._manipulators.values():
            with suppress(Exception):
                manipulator.destroy()

        if self._scene_view:
            self._scene_view.scene.clear()

        # Release stale manipulators
        self._manipulators = {}

    def _on_stage_event(self, event):
        """Called by stage_event_stream"""
        if not self._scene_view:
            return

        match event.type:
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
        settings = carb.settings.get_settings()
        for subscription in self._setting_subscriptions:
            settings.unsubscribe_to_change_events(subscription)
        self._setting_subscriptions = []
        if self._scene_view and self._viewport_api:
            # Be a good citizen, and un-register the SceneView from Viewport updates
            self._viewport_api.remove_scene_view(self._scene_view)
        self._destroy_manipulators()
        self._viewport_layers = None
        _reset_default_attrs(self)
