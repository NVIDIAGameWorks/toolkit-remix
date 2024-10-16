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
from omni.kit.waypoint.core import WaypointChangeCallbacks as _WaypointChangeCallbacks
from pxr import Usd

_CONTEXT = "/exts/lightspeed.event.waypoint_game_camera/context"


class WaypointGameCameraCore(_ILSSEvent):

    WAYPOINT_NAME = "Waypoint_GameCam"

    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_context_name": None,
            "_context": None,
            "_layer_event_sub": None,
            "_waypoint_instance": None,
            "_ext_callback": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._waypoint_instance = _get_waypoint_instance()
        self._context_name = carb.settings.get_settings().get(_CONTEXT) or ""

        self._context = omni.usd.get_context(self._context_name)
        self._layers = _layers.get_layers()
        self._layer_manager = _LayerManager(self._context_name)
        self._curr_capture = self._layer_manager.get_layer(_LayerType.capture)
        self.__last_game_waypoint = False

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
        if self._waypoint_instance and self._waypoint_instance.waypoint_obj:
            self._waypoint_instance.waypoint_obj.deregister_callback(self._ext_callback)
        self._layer_event_sub = None

    def _reset_persp_camera(self):
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
        stage = self._context.get_stage()
        if not stage:
            carb.log_warn("No stage found. Not setting waypoint.")
            return
        game_camera = stage.GetPrimAtPath("/RootNode/Camera")
        if not game_camera:
            carb.log_warn("No game camera found. Not setting waypoint.")
            return

        # Need to wait for the camera to switch + image to render
        self._waypoint_instance.waypoint_obj.viewport_widget.set_active_camera("/RootNode/Camera")
        for _ in range(6):
            await omni.kit.app.get_app().next_update_async()

        if not stage:
            self._reset_persp_camera()
            return
        with Usd.EditContext(stage, stage.GetRootLayer()):
            self.__last_game_waypoint = True
            await self._waypoint_instance.waypoint_obj.create_waypoint_async()
            self.__last_game_waypoint = False
        self._reset_persp_camera()

    def _on_waypoint_created(self, waypoint) -> None:
        if not self.__last_game_waypoint:
            return
        if not waypoint:
            carb.log_warn("No waypoint camera found. Unable to rename.")
            self._reset_persp_camera()
            return
        if WaypointGameCameraCore.WAYPOINT_NAME not in waypoint.name:
            stage = self._context.get_stage()
            with Usd.EditContext(stage, stage.GetRootLayer()):
                waypoint.rename(WaypointGameCameraCore.WAYPOINT_NAME)

    def _reset_waypoints(self):
        waypoints = self._waypoint_instance.waypoint_obj.get_waypoints()
        game_waypoint = [waypoint for waypoint in waypoints if waypoint.name == WaypointGameCameraCore.WAYPOINT_NAME]
        if game_waypoint:
            waypoint = game_waypoint[0]
            stage = self._context.get_stage()
            with Usd.EditContext(stage, stage.GetRootLayer()):
                self._waypoint_instance.waypoint_obj.delete_waypoint(waypoint)
            # fix bug that don't delete waypoint
            path = waypoint.path
            if self._context.get_stage().GetPrimAtPath(path):
                omni.kit.commands.execute("DeletePrimsCommand", paths=[path], destructive=True)

        asyncio.ensure_future(self._create_game_camera_waypoint())

    def __on_layer_event(self, event):
        """Function to handle layer events"""
        payload = _layers.get_layer_event_payload(event)
        if not payload:
            return
        capture_layer = self._layer_manager.get_layer(_LayerType.capture)
        if self._curr_capture == capture_layer:
            return

        if payload.event_type == _layers.LayerEventType.SUBLAYERS_CHANGED:
            if not self._waypoint_instance.waypoint_obj:
                self._waypoint_instance.create_waypoint_instance(self._context_name)
                self._ext_callback = _WaypointChangeCallbacks(on_waypoint_created=self._on_waypoint_created)
                self._waypoint_instance.waypoint_obj.register_callback(self._ext_callback)
            self._curr_capture = capture_layer
            waypoints = self._waypoint_instance.waypoint_obj.get_waypoints()
            if waypoints:
                self._reset_waypoints()
            else:
                asyncio.ensure_future(self._create_game_camera_waypoint())

    def destroy(self):
        _reset_default_attrs(self)
