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

import asyncio

import carb
import carb.settings
import omni.kit.commands
import omni.kit.undo
import omni.usd
from lightspeed.common import constants
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.utils.common.camera import clear_game_camera_overrides as _clear_game_camera_overrides
from lightspeed.trex.utils.common.camera import PSEUDO_ORTHOGRAPHIC_CAMERA_PATHS as _ORTHOGRAPHIC_CAMERA_PATHS
from lightspeed.trex.utils.common.camera import (
    configure_pseudo_orthographic_perspective_cameras as _configure_pseudo_orthographic_perspective_cameras,
)
from lightspeed.trex.utils.common.camera import (
    copy_capture_camera_to_perspective as _copy_capture_camera_to_perspective,
)
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from pxr import Usd

_CONTEXT = "/exts/lightspeed.event.capture_persp_to_persp/context"


class EventCapturePerspToPerspCore(_ILSSEvent):
    _CAPTURE_GEOMETRY_PATHS = (constants.ROOTNODE_MESHES, constants.ROOTNODE_INSTANCES)
    _ORTHOGRAPHIC_FRAME_ZOOM = 0.6

    def __init__(self):
        super().__init__()
        settings = carb.settings.get_settings()
        self._context_name: str = settings.get(_CONTEXT) or ""
        self._context = omni.usd.get_context(self._context_name)
        self._layer_manager = _LayerManagerCore(self._context_name)
        self._sub_capture_layer_imported = None

    @property
    def name(self) -> str:
        """Name of the event"""
        return "CapturePerspToPersp"

    def _get_valid_capture_geometry_paths(self, stage) -> list[str]:
        geometry_paths = []
        for prim_path in self._CAPTURE_GEOMETRY_PATHS:
            prim = stage.GetPrimAtPath(prim_path)
            if prim.IsValid():
                geometry_paths.append(prim_path)
        return geometry_paths

    def _frame_orthographic_cameras(self, stage):
        geometry_paths = self._get_valid_capture_geometry_paths(stage)
        if not geometry_paths:
            carb.log_warn("Can't find capture geometry to frame orthographic cameras")
            return

        configured_camera_paths = set(_configure_pseudo_orthographic_perspective_cameras(stage, geometry_paths))
        for camera_path in _ORTHOGRAPHIC_CAMERA_PATHS:
            if camera_path not in configured_camera_paths:
                carb.log_warn(
                    f"Orthographic camera {camera_path} was not configured, won't frame it to capture geometry"
                )
                continue
            camera_prim = stage.GetPrimAtPath(camera_path)
            camera_path_string = str(camera_path)
            if not camera_prim.IsValid():
                carb.log_warn(f"Orthographic camera {camera_path} is invalid, won't frame it to capture geometry")
                continue
            omni.kit.commands.execute(
                "FramePrimsCommand",
                prim_to_move=camera_path_string,
                prims_to_frame=geometry_paths,
                time_code=Usd.TimeCode.Default(),
                usd_context_name=self._context_name,
                aspect_ratio=1.0,
                zoom=self._ORTHOGRAPHIC_FRAME_ZOOM,
            )

    def _install(self):
        """Function that will create the behavior"""
        self._uninstall()

        self._sub_capture_layer_imported = _get_event_manager_instance().subscribe_global_custom_event(
            constants.GlobalEventNames.CAPTURE_LAYER_IMPORTED.value, self._on_capture_layer_imported
        )

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._sub_global_event_registered = None
        self._sub_global_event_unregistered = None
        self._sub_capture_layer_imported = None

    def _set_perspective_camera(self):
        """Setup the session camera to match the capture camera"""
        stage = self._context.get_stage()
        if stage is None:
            return
        capture_layer = self._layer_manager.get_layer_of_type(_LayerType.capture)
        if capture_layer is None:
            carb.log_warn("Can't find a capture layer, won't be setting up the default camera to match game")
            return

        carb.log_info("Setting up perspective camera from capture")
        _clear_game_camera_overrides(stage, capture_layer)
        _copy_capture_camera_to_perspective(stage, capture_layer)
        with omni.kit.undo.disabled():
            self._frame_orthographic_cameras(stage)

    @omni.usd.handle_exception
    async def _deferred_set_perspective_camera(self):
        await omni.kit.app.get_app().next_update_async()
        self._set_perspective_camera()

    @_ignore_function_decorator(attrs=["_ignore_on_event"])
    def _on_capture_layer_imported(self):
        stage = self._context.get_stage()
        if not stage:
            return
        asyncio.ensure_future(self._deferred_set_perspective_camera())
