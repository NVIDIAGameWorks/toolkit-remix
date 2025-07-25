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
import contextlib

import carb
import carb.settings
import omni.kit.undo
import omni.usd
from lightspeed.common import constants
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from pxr import Gf, Sdf, Usd

_CONTEXT = "/exts/lightspeed.event.capture_persp_to_persp/context"


class CopyCapturePerspToPerspCore(_ILSSEvent):

    _PERSP_PATH = "/OmniverseKit_Persp"

    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_subscription_layer": None,
            "_layer_manager": None,
            "_sub_global_event_registered": None,
            "_sub_global_event_unregistered": None,
            "_sub_capture_layer_imported": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        settings = carb.settings.get_settings()
        self.__context_name = settings.get(_CONTEXT) or ""
        self.__last_capture_layer = None
        self.__last_session_layer = None
        self._context = omni.usd.get_context(self.__context_name)
        self._layer_manager = _LayerManagerCore(self.__context_name)

    @property
    def name(self) -> str:
        """Name of the event"""
        return "Bake Reference from prim override"

    def _install(self):
        """Function that will create the behavior"""
        self._install_layer_listener()

    def _install_layer_listener(self):
        self._uninstall()
        self._sub_global_event_registered = _get_event_manager_instance().subscribe_global_custom_event_register(
            self._on_global_event_registered
        )
        self._sub_global_event_unregistered = _get_event_manager_instance().subscribe_global_custom_event_unregister(
            self._on_global_event_unregistered
        )

    @omni.usd.handle_exception
    async def _deferred_setup_perspective_camera(self):
        await omni.kit.app.get_app().next_update_async()
        # setup the session camera to match the capture camera
        stage = self._context.get_stage()
        capture_layer = self._layer_manager.get_layer(_LayerType.capture)
        if capture_layer is None:
            carb.log_warn("Can't find a capture layer, won't be setting up the default camera to match game")
            return
        session_layer = stage.GetSessionLayer()
        with contextlib.suppress(Exception):
            with Usd.EditContext(stage, session_layer):
                carb.log_info("Setting up perspective camera from capture")
                camera_prim = stage.GetPrimAtPath(self._PERSP_PATH)
                if not camera_prim.IsValid():
                    return
                captured_camera_prim = stage.GetPrimAtPath(constants.CAPTURED_CAMERA)
                if not captured_camera_prim.IsValid():  # support legacy camera location
                    captured_camera_prim = stage.GetPrimAtPath(constants.ROOTNODE_CAMERA)
                Sdf.CopySpec(capture_layer, captured_camera_prim.GetPath(), session_layer, self._PERSP_PATH)

                attr_position, _attr_rotation, _attr_scale, _attr_order = omni.usd.TransformHelper().get_transform_attr(
                    camera_prim.GetAttributes()
                )
                if attr_position:
                    if attr_position.GetName() == "xformOp:translate":
                        xf_tr = camera_prim.GetAttribute("xformOp:translate")
                        translate = xf_tr.Get()
                    elif attr_position.GetName() == "xformOp:transform":
                        xf_tr = camera_prim.GetAttribute("xformOp:transform")
                        value = xf_tr.Get()
                        if isinstance(value, Gf.Matrix4d):
                            matrix = value
                        else:
                            matrix = Gf.Matrix4d(*value)
                        translate = matrix.ExtractTranslation()

                zlen = Gf.Vec3d(translate[0], translate[1], translate[2]).GetLength()

                omni.kit.commands.execute(
                    "ChangePropertyCommand",
                    prop_path=str(camera_prim.GetPath().AppendProperty("omni:kit:centerOfInterest")),
                    value=Gf.Vec3d(0, 0, -zlen),
                    prev=None,
                    type_to_create_if_not_exist=Sdf.ValueTypeNames.Vector3d,
                    is_custom=True,
                    usd_context_name=self.__context_name,
                    variability=Sdf.VariabilityUniform,
                )

    def _on_global_event_registered(self, name: str):
        if name == constants.GlobalEventNames.IMPORT_CAPTURE_LAYER.value:
            self._sub_capture_layer_imported = _get_event_manager_instance().subscribe_global_custom_event(
                constants.GlobalEventNames.IMPORT_CAPTURE_LAYER.value, self._on_capture_layer_imported
            )

    def _on_global_event_unregistered(self, name: str):
        if name == constants.GlobalEventNames.IMPORT_CAPTURE_LAYER.value:
            self._sub_capture_layer_imported = None

    @_ignore_function_decorator(attrs=["_ignore_on_event"])
    def _on_capture_layer_imported(self):
        stage = self._context.get_stage()
        if not stage:
            return
        root_layer = stage.GetRootLayer()
        if not root_layer:
            return
        session_layer = stage.GetSessionLayer()
        if (
            self.__last_session_layer is not None
            and self.__last_session_layer != session_layer.identifier
            and root_layer.customLayerData.get("cameraSettings")
        ):
            self.__last_session_layer = session_layer.identifier
            return
        self.__last_session_layer = session_layer.identifier

        capture_layer = self._layer_manager.get_layer(_LayerType.capture)
        if not capture_layer:
            self.__last_capture_layer = None
            return
        if (
            self.__last_capture_layer is not None
            and not self.__last_capture_layer.expired
            and capture_layer.identifier == self.__last_capture_layer.identifier
        ):
            return
        self.__last_capture_layer = capture_layer
        asyncio.ensure_future(self._deferred_setup_perspective_camera())

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._sub_capture_layer_imported = None

    def destroy(self):
        self._uninstall()
        _reset_default_attrs(self)
