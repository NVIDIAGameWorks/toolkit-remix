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
from typing import List

import carb
import omni.kit.usd.layers as _layers
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManager
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.waypoint.core import get_instance as _get_waypoint_instance
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.usd.commands import remove_prim_spec as _remove_prim_spec
from pxr import Sdf, Usd

_CONTEXT = "/exts/lightspeed.event.waypoint_creation/context"


class WaypointCreationCore(_ILSSEvent):

    WAYPOINT_ROOT_PRIM_PATH = "/Viewport_Waypoints"
    WAYPOINT_GAME_CAM_NAME = "Waypoint_GameCam"

    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_context_name": None,
            "_context": None,
            "_stage_event_sub": None,
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

        self._waypoints_migrated = False

    @property
    def name(self) -> str:
        """Name of the event"""
        return "WaypointCreationCore"

    def _install(self):
        """Function that will create the behavior"""
        self._uninstall()

        self._stage_event_sub = self._context.get_stage_event_stream().create_subscription_to_pop(self.__on_stage_event)
        self._layer_event_sub = self._layers.get_event_stream().create_subscription_to_pop(self.__on_layer_event)

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._stage_event_sub = None
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

        # Use the project root layer edit context in case the waypoint override hasn't yet been configured
        with Usd.EditContext(stage, stage.GetRootLayer()):
            await self._waypoint_instance.waypoint_obj.create_waypoint_async(
                new_waypoint_path=f"{self.WAYPOINT_ROOT_PRIM_PATH}/{self.WAYPOINT_GAME_CAM_NAME}"
            )
        self._reset_persp_camera()

    def _reset_game_cam_waypoints(self):
        waypoints = self._waypoint_instance.waypoint_obj.get_waypoints()
        game_waypoint = [
            waypoint for waypoint in waypoints if waypoint.name == WaypointCreationCore.WAYPOINT_GAME_CAM_NAME
        ]
        if game_waypoint:
            waypoint = game_waypoint[0]
            stage = self._context.get_stage()

            # Use the project root layer edit context in case the waypoint override hasn't yet been configured
            with Usd.EditContext(stage, stage.GetRootLayer()):
                self._waypoint_instance.waypoint_obj.delete_waypoint(waypoint)

            # Fix bug that don't delete waypoint
            path = waypoint.path
            if self._context.get_stage().GetPrimAtPath(path):
                omni.kit.commands.execute("DeletePrimsCommand", paths=[path], destructive=True)

        asyncio.ensure_future(self._create_game_camera_waypoint())

    def __on_stage_event(self, event):
        # Change the WaypointExtension edit target during relevant stage opens
        if event.type == int(omni.usd.StageEventType.OPENED) and self._waypoint_instance.waypoint_obj:
            self._waypoints_migrated = False
            project_layer = self._context.get_stage().GetRootLayer()
            if project_layer and not Sdf.Layer.IsAnonymousLayerIdentifier(project_layer.identifier):
                self._waypoint_instance.waypoint_obj.edit_target = project_layer
        elif event.type == int(omni.usd.StageEventType.CLOSED):
            # Clear the edit target override during stage close to prepare for alternate stage opens
            self._waypoint_instance.waypoint_obj.edit_target = None

    def __on_layer_event(self, event):
        """Function to handle layer events"""
        # Migrate any mod layer waypoints if needed
        project_layer = self._context.get_stage().GetRootLayer()
        if project_layer and not self._waypoints_migrated and self._get_sub_layer_waypoint_prim_specs(self._context):
            carb.log_warn(
                "Some of the root project layer's sub-layers contain waypoints. "
                "Waypoints should be stored on the project layer."
            )
            self._migrate_all_waypoints_to_project_layer(context=self._context)
            self._waypoints_migrated = True

        payload = _layers.get_layer_event_payload(event)
        if not payload:
            return
        capture_layer = self._layer_manager.get_layer(_LayerType.capture)
        if self._curr_capture == capture_layer:
            return

        if payload.event_type == _layers.LayerEventType.SUBLAYERS_CHANGED:
            if not self._waypoint_instance.waypoint_obj:
                self._waypoint_instance.create_waypoint_instance(self._context_name)
            self._curr_capture = capture_layer
            waypoints = self._waypoint_instance.waypoint_obj.get_waypoints()
            if waypoints:
                self._reset_game_cam_waypoints()
            else:
                asyncio.ensure_future(self._create_game_camera_waypoint())

    @staticmethod
    def _migrate_all_waypoints_to_project_layer(context: omni.usd.UsdContext):
        """
        Migrate all viewport waypoint prims from all sub-layers to the project root layer.
        Startup game camera waypoints will overwrite, but all other migrated waypoints will be renamed if needed.
        If there are no waypoints on the source sub-layers, this function will do nothing.

        Args:
            context (omni.usd.UsdContext): Context.
        """
        stage = context.get_stage()
        project_root_layer = stage.GetRootLayer()
        waypoints_prim_path = Sdf.Path(WaypointCreationCore.WAYPOINT_ROOT_PRIM_PATH)

        carb.log_warn("Migrating all sub-layer waypoints to the project root layer...")

        # Before migration, define destination parent prim and give it a definition specifier
        target_waypoint_parent_prim_spec = Sdf.CreatePrimInLayer(project_root_layer, waypoints_prim_path)
        target_waypoint_parent_prim_spec.specifier = Sdf.SpecifierDef

        # Iterate through prims and copy all waypoint prims to the target layer
        for waypoint_parent_prim_spec in WaypointCreationCore._get_sub_layer_waypoint_prim_specs(context):
            for waypoint_child_prim_spec in waypoint_parent_prim_spec.nameChildren:

                # Find a destination path
                is_game_cam = WaypointCreationCore.WAYPOINT_GAME_CAM_NAME in str(waypoint_child_prim_spec.path)
                if project_root_layer.GetPrimAtPath(waypoint_child_prim_spec.path) and not is_game_cam:
                    # If a waypoint prim already exists at dest, don't overwrite it; Game cam can be overwritten
                    dest_waypoint_prim_path = omni.usd.get_stage_next_free_path(
                        stage, waypoint_child_prim_spec.path, False
                    )
                else:
                    # Overwrite the prim otherwise
                    dest_waypoint_prim_path = waypoint_child_prim_spec.path

                # Copy the prim
                Sdf.CopySpec(
                    waypoint_parent_prim_spec.layer,
                    waypoint_child_prim_spec.path,
                    project_root_layer,
                    dest_waypoint_prim_path,
                )

                # Make sure the newly copied prim is a prim definition and not an override
                new_waypoints_prim_spec = project_root_layer.GetPrimAtPath(dest_waypoint_prim_path)
                new_waypoints_prim_spec.specifier = Sdf.SpecifierDef

            # Remove all waypoint prims from the source sub-layer
            _remove_prim_spec(waypoint_parent_prim_spec.layer, waypoint_parent_prim_spec.path)

        carb.log_warn("Waypoint migration complete. Please save to apply the changes.")

    @staticmethod
    def _layer_has_waypoints(layer: Sdf.Layer) -> bool:
        return bool(layer.GetPrimAtPath(Sdf.Path(WaypointCreationCore.WAYPOINT_ROOT_PRIM_PATH)))

    @staticmethod
    def _get_sub_layer_waypoint_prim_specs(context: omni.usd.UsdContext) -> List[Sdf.PrimSpec]:
        """
        Returns all waypoint prim specs existing on sub-layers. The project root layer waypoint prims are not included.
        If no waypoints prim can be found on the stage, this function will return an empty list.

        Args:
            context (omni.usd.UsdContext): Context.

        Returns:
            A list of Sdf.PrimSpec objects that are on all sub-layers and not the stage root layer.
        """
        stage = context.get_stage()
        waypoints_prim_path = Sdf.Path(WaypointCreationCore.WAYPOINT_ROOT_PRIM_PATH)
        waypoints_prim = stage.GetPrimAtPath(waypoints_prim_path)

        # Return an empty list if the waypoints prim is not yet valid / if the stage is not ready
        if not waypoints_prim or not waypoints_prim.IsValid():
            return []

        sub_layer_waypoint_prims = []
        for prim_spec in waypoints_prim.GetPrimStack():
            if prim_spec.layer != stage.GetRootLayer():
                sub_layer_waypoint_prims.append(prim_spec)
        return sub_layer_waypoint_prims

    def destroy(self):
        _reset_default_attrs(self)
