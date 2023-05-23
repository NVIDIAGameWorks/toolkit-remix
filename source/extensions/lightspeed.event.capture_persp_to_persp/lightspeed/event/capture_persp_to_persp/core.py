"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
import contextlib

import carb
import carb.settings
import omni.kit.undo
import omni.kit.usd.layers as _layers
import omni.usd
from lightspeed.events_manager.i_ds_event import ILSSEvent
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.utils.common import ignore_function_decorator as _ignore_function_decorator
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Gf, Sdf, Usd

_CONTEXT = "/exts/lightspeed.event.capture_persp_to_persp/context"


class CopyCapturePerspToPerspCore(ILSSEvent):

    _PERSP_PATH = "/OmniverseKit_Persp"

    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_subscription_layer": None,
            "_layer_manager": None,
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
        self._uninstall_layer_listener()
        layers = _layers.get_layers()
        self._subscription_layer = layers.get_event_stream().create_subscription_to_pop(
            self.__on_layer_event, name="LayerChange"
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
                Sdf.CopySpec(capture_layer, "/RootNode/Camera", session_layer, self._PERSP_PATH)

                xf_tr = camera_prim.GetProperty("xformOp:translate")
                translate = xf_tr.Get()
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

    @_ignore_function_decorator(attrs=["_ignore_on_event"])
    def __on_layer_event(self, event):
        payload = _layers.get_layer_event_payload(event)
        if not payload:
            return
        stage = self._context.get_stage()
        if not stage:
            return
        root_layer = stage.GetRootLayer()
        if not root_layer:
            return
        session_layer = stage.GetSessionLayer()
        if self.__last_session_layer != session_layer.identifier and root_layer.customLayerData.get("cameraSettings"):
            self.__last_session_layer = session_layer.identifier
            return
        self.__last_session_layer = session_layer.identifier

        if payload.event_type == _layers.LayerEventType.SUBLAYERS_CHANGED:
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
        self._uninstall_layer_listener()

    def _uninstall_layer_listener(self):
        self._subscription_layer = None

    def destroy(self):
        self._uninstall()
        _reset_default_attrs(self)
