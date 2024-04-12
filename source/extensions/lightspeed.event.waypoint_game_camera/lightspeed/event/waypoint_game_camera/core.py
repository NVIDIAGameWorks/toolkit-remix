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
import asyncio

import carb
import omni.kit.usd.layers as _layers
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManager
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.waypoint.core import get_instance as _get_waypoint_instance
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

_CONTEXT = "/exts/lightspeed.event.waypoint_game_camera/context"


class WaypointGameCameraCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_context_name": None,
            "_context": None,
            "_layer_event_sub": None,
            "_waypoint_instance": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._waypoint_instance = _get_waypoint_instance()
        self._context_name = carb.settings.get_settings().get(_CONTEXT) or ""

        self._context = omni.usd.get_context(self._context_name)
        self._layers = _layers.get_layers()
        self._layer_manager = _LayerManager(self._context_name)
        self._curr_capture = self._layer_manager.get_layer(_LayerType.capture)

        self._waypoint_name = "Waypoint_GameCam"

    @property
    def name(self) -> str:
        """Name of the event"""
        return "WaypointGameCameraCore"

    def _install(self):
        """Function that will create the behavior"""
        self._uninstall()

        self._layer_event_sub = self._layers.get_event_stream().create_subscription_to_pop(self.__on_layer_event)

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._layer_event_sub = None

    async def _reset_persp_camera(self):
        """Function to reset to perspective camera"""
        stage = self._context.get_stage()
        persp_camera = stage.GetPrimAtPath("/OmniverseKit_Persp")
        if not persp_camera:
            carb.log_warn("No perspective camera found.")
            return
        self._waypoint_instance.waypoint_obj.viewport_widget.set_active_camera("/OmniverseKit_Persp")

    @omni.usd.handle_exception
    async def _create_game_camera_waypoint(self):
        """Function to set game camera Waypoint"""
        # Need to refresh a few times on start up to get thumbnail
        for _ in range(4):
            await omni.kit.app.get_app().next_update_async()

        stage = self._context.get_stage()
        game_camera = stage.GetPrimAtPath("/RootNode/Camera")
        if not game_camera:
            carb.log_warn("No game camera found. Not setting waypoint.")
            return

        self._waypoint_instance.waypoint_obj.viewport_widget.set_active_camera("/RootNode/Camera")
        self._waypoint_instance.waypoint_obj.create_waypoint()

        # Another refresh to pick up the newly created waypoint for renaming
        for _ in range(6):
            await omni.kit.app.get_app().next_update_async()
        waypoints = self._waypoint_instance.waypoint_obj.get_waypoints()
        if waypoints:
            waypoint = [j for i, j in enumerate(waypoints)][-1]
            if self._waypoint_name not in waypoint.name:
                self._waypoint_instance.waypoint_obj.rename_waypoint(waypoint, self._waypoint_name)

        asyncio.ensure_future(self._reset_persp_camera())

    @omni.usd.handle_exception
    async def _reset_waypoints(self):
        waypoint = self._waypoint_instance.waypoint_obj.get_waypoint(self._waypoint_name)
        self._waypoint_instance.waypoint_obj.delete_waypoint(waypoint)
        asyncio.ensure_future(self._create_game_camera_waypoint())

    def __on_layer_event(self, event):
        """Function to handle layer events"""
        if not self._waypoint_instance.waypoint_obj:
            self._waypoint_instance.create_waypoint_instance(self._context_name)

        payload = _layers.get_layer_event_payload(event)
        if not payload:
            return
        capture_layer = self._layer_manager.get_layer(_LayerType.capture)
        if self._curr_capture == capture_layer:
            return

        if payload.event_type == _layers.LayerEventType.SUBLAYERS_CHANGED:
            self._curr_capture = capture_layer
            waypoints = self._waypoint_instance.waypoint_obj.get_waypoints()
            if waypoints:
                asyncio.ensure_future(self._reset_waypoints())
            else:
                asyncio.ensure_future(self._create_game_camera_waypoint())

    def destroy(self):
        _reset_default_attrs(self)
