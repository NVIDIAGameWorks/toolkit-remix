"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
from typing import Callable

import omni.kit.window.file
import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.layer_manager.layer_types import LayerType
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class Setup:
    def __init__(self, context_name: str):
        self._default_attr = {"_context": None, "_layer_manager": None, "_sub_stage_event": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._context = omni.usd.get_context(context_name)
        self._layer_manager = _LayerManagerCore(context_name=context_name)
        self._sub_stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_stage_event, name="StageChanged"
        )

    def open_stage(self, path, callback=None):
        omni.kit.window.file.open_stage(path)
        if callback:
            callback()

    def __on_stage_event(self, event):
        if event.type in [
            int(omni.usd.StageEventType.OPENED),
        ]:
            self._layer_manager.set_edit_target_layer(LayerType.replacement)

    def create_new_work_file(self):
        self._context.new_stage_with_callback(self._on_new_stage_created)

    def _on_new_stage_created(self, result: bool, error: str):
        asyncio.ensure_future(self._deferred_startup(self._context))

    @omni.usd.handle_exception
    async def _deferred_startup(self, context):
        """Or crash"""
        await omni.kit.app.get_app_interface().next_update_async()
        await context.new_stage_async()
        await omni.kit.app.get_app_interface().next_update_async()
        stage = context.get_stage()
        while (context.get_stage_state() in [omni.usd.StageState.OPENING, omni.usd.StageState.CLOSING]) or not stage:
            await asyncio.sleep(0.1)
        # set some metadata
        root_layer = stage.GetRootLayer()
        self._layer_manager.set_custom_data_layer_type(root_layer, _LayerType.workfile)

        # TODO, TMP
        from pxr import Gf, UsdGeom  # noqa PLC0415

        # set the camera
        camera = stage.GetPrimAtPath("/OmniverseKit_Persp")
        camera_prim = UsdGeom.Camera(camera)
        camera_prim.ClearXformOpOrder()
        # omni.kit.commands.execute("TransformPrimCommand", path="/OmniverseKit_Persp", usd_context_name=context)

        hello = UsdGeom.Xform.Define(stage, "/hello")
        translate = hello.AddXformOp(UsdGeom.XformOp.TypeTranslate, UsdGeom.XformOp.PrecisionDouble, "")
        translate.Set(Gf.Vec3f(0, 0, 0))
        rotate = hello.AddXformOp(UsdGeom.XformOp.TypeRotateXYZ, UsdGeom.XformOp.PrecisionDouble, "")
        rotate.Set(Gf.Vec3f(0, 0, 0))
        scale = hello.AddXformOp(UsdGeom.XformOp.TypeScale, UsdGeom.XformOp.PrecisionDouble, "")
        scale.Set(Gf.Vec3f(1, 1, 1))
        stage.SetDefaultPrim(hello.GetPrim())
        cube = UsdGeom.Cube.Define(stage, "/hello/world")
        cube.GetSizeAttr().Set(50)

        hello = UsdGeom.Xform.Define(stage, "/hello1")
        translate = hello.AddXformOp(UsdGeom.XformOp.TypeTranslate, UsdGeom.XformOp.PrecisionDouble, "")
        translate.Set(Gf.Vec3f(70, 0, 0))
        rotate = hello.AddXformOp(UsdGeom.XformOp.TypeRotateXYZ, UsdGeom.XformOp.PrecisionDouble, "")
        rotate.Set(Gf.Vec3f(0, 0, 0))
        scale = hello.AddXformOp(UsdGeom.XformOp.TypeScale, UsdGeom.XformOp.PrecisionDouble, "")
        scale.Set(Gf.Vec3f(1, 1, 1))
        sphere = UsdGeom.Cube.Define(stage, "/hello1/world1")
        sphere.GetSizeAttr().Set(40)
        print("hellloooo")

    def save(self):
        omni.kit.window.file.save()

    def save_as(self, on_save_done: Callable[[bool, str], None] = None):
        omni.kit.window.file.save_as(False, on_save_done=on_save_done)

    def destroy(self):
        _reset_default_attrs(self)
