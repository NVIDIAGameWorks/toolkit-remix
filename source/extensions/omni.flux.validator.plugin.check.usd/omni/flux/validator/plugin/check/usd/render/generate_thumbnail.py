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
import ctypes
import functools
import io
from typing import Any, Optional, Tuple

import carb.settings
import carb.tokens
import omni.client
import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from omni.kit.viewport.utility import capture_viewport_to_buffer, frame_viewport_selection, get_active_viewport
from PIL import Image
from pxr import Gf, Kind, Sdf, Tf, Usd, UsdGeom, UsdLux

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD  # noqa PLE0402

RENDERER_RESOLUTION_WIDTH = "/app/renderer/resolution/width"
RENDERER_RESOLUTION_HEIGHT = "/app/renderer/resolution/height"
RENDERER_MODE = "/rtx/rendermode"
CAPTURE_VIEWPORT_ONLY = "/persistent/app/captureFrame/viewport"
CAPTURE_ALPHA_TO_1 = "/app/captureFrame/setAlphaTo1"
VIEWPORT_DISPLAY_OPTIONS = "/persistent/app/viewport/displayOptions"
POST_BACKGROUND_ZERO_APLHA_ENABLED = "/rtx/post/backgroundZeroAlpha/enabled"
POST_BACKGROUND_ZERO_APLHA_COMPISITED = "/rtx/post/backgroundZeroAlpha/backgroundComposite"
POST_BACKGROUND_ZERO_OUTPUT_APLHA_COMPISITED = "/rtx/post/backgroundZeroAlpha/outputAlphaInComposite"


class GenerateThumbnail(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        light_rig_path: str = "${omni.flux.validator.plugin.check.usd}/data/rigs/default_light_template.usda"
        light_rotation: Optional[Tuple[float, float, float]] = None
        thumbnail_size: Tuple[int, int] = (256, 256)
        render_mode: str = "RayTracing"
        light_intensity_multipler: Optional[int] = 1
        viewport_api: Optional[str] = None  # TODO: define a function to run like "my_module.get_viewport_api"

    name = "GenerateThumbnail"
    tooltip = "This plugin will generate the thumbnail"
    data_type = Data
    display_name = "Generate the thumbnail"

    def __init__(self):
        super().__init__()
        self._waiting_for_asset_loaded = True
        self._fix_ran = False
        self._current_resolution_width = None
        self._current_resolution_height = None
        self._current_capture_only_viewport = None
        self._current_display_options = None
        self._current_render_mode = None
        self._current_capture_alpha = None
        self._current_background_zero_alpha_enabled = None
        self._current_background_zero_alpha_composited = None
        self._current_background_zero_output_alpha_composited = None

    def __push_pop_renderer_settings(self, schema_data: Data, push: bool) -> None:
        settings = carb.settings.get_settings()
        if push:
            # Save current renderer settings
            self._current_resolution_width = settings.get(RENDERER_RESOLUTION_WIDTH)
            self._current_resolution_height = settings.get(RENDERER_RESOLUTION_HEIGHT)
            self._current_capture_only_viewport = settings.get(CAPTURE_VIEWPORT_ONLY)
            self._current_display_options = settings.get(VIEWPORT_DISPLAY_OPTIONS)
            self._current_render_mode = settings.get(RENDERER_MODE)
            self._current_capture_alpha = settings.get(CAPTURE_ALPHA_TO_1)
            self._current_background_zero_alpha_enabled = settings.get(POST_BACKGROUND_ZERO_APLHA_ENABLED)
            self._current_background_zero_alpha_composited = settings.get(POST_BACKGROUND_ZERO_APLHA_COMPISITED)
            self._current_background_zero_output_alpha_composited = settings.get(
                POST_BACKGROUND_ZERO_OUTPUT_APLHA_COMPISITED
            )

            # Set the renderer settings

            # Here we use higher resolution when capturing viewport and down sampling later for better edge quality
            settings.set(RENDERER_RESOLUTION_WIDTH, schema_data.thumbnail_size[0] * 2)
            settings.set(RENDERER_RESOLUTION_HEIGHT, schema_data.thumbnail_size[1] * 2)
            settings.set(RENDERER_MODE, schema_data.render_mode)
            settings.set(CAPTURE_VIEWPORT_ONLY, True)
            settings.set(VIEWPORT_DISPLAY_OPTIONS, 0)

            settings.set(CAPTURE_ALPHA_TO_1, False)
            settings.set(POST_BACKGROUND_ZERO_APLHA_ENABLED, True)
            settings.set(POST_BACKGROUND_ZERO_APLHA_COMPISITED, False)
            settings.set(POST_BACKGROUND_ZERO_OUTPUT_APLHA_COMPISITED, True)
        else:
            # Restore the renderer settings
            settings.set(RENDERER_RESOLUTION_WIDTH, self._current_resolution_width)
            settings.set(RENDERER_RESOLUTION_HEIGHT, self._current_resolution_height)
            settings.set(RENDERER_MODE, self._current_render_mode)
            settings.set(CAPTURE_VIEWPORT_ONLY, self._current_capture_only_viewport)
            settings.set(VIEWPORT_DISPLAY_OPTIONS, self._current_display_options)
            settings.set(CAPTURE_ALPHA_TO_1, self._current_capture_alpha)
            settings.set(POST_BACKGROUND_ZERO_APLHA_ENABLED, self._current_background_zero_alpha_enabled)
            settings.set(POST_BACKGROUND_ZERO_APLHA_COMPISITED, self._current_background_zero_alpha_composited)
            settings.set(
                POST_BACKGROUND_ZERO_OUTPUT_APLHA_COMPISITED, self._current_background_zero_output_alpha_composited
            )

    def __on_viewport_captured(
        self, schema_data: Data, output_url, buffer, buffer_size, width, height, _format
    ) -> None:
        """
        Function called when capturing viewport
        """
        try:
            ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.POINTER(ctypes.c_byte * buffer_size)
            ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
            content = ctypes.pythonapi.PyCapsule_GetPointer(buffer, None)
        except Exception as e:  # noqa PLW0718
            carb.log_error(f"[Thumbnail] Failed to get capture buffer: {e}")
            return

        # Crop and down sample
        data = self._generate_thumbnail_data(schema_data, content.contents, (width, height))

        # Save to output url
        result = omni.client.write_file(output_url, data)
        if result != omni.client.Result.OK:
            carb.log_error(f"[Thumbnail] Cannot write {output_url}, error code: {result}.")
        else:
            carb.log_info(f"[Thumbnail] Exported to {output_url}")

    def _generate_thumbnail_data(self, schema_data: Data, raw_data, size: Tuple[int, int]) -> bytes:
        """
        Generate desired thumbnail data from raw data
        """
        # Constrcut Image object
        im = Image.frombytes("RGBA", size, raw_data)

        # Crop the center of the image if necessary
        width, height = im.size  # Get dimensions
        if width != height:
            if width > height:
                left = (width - height) / 2
                right = width - left
                top = 0
                bottom = height
            else:
                left = 0
                right = width
                top = (height - width) / 2
                bottom = height - top
            im = im.crop((left, top, right, bottom))

        im.thumbnail((schema_data.thumbnail_size[0], schema_data.thumbnail_size[1]), Image.LANCZOS)  # noqa

        # Save to buffer
        buffer = io.BytesIO()
        im.save(buffer, "png")
        return buffer.getvalue()

    def _on_stage_event(self, event) -> None:
        # This pin is setup when we are waiting for an MDL file to load
        if event.type == int(omni.usd.StageEventType.ASSETS_LOADED) and self._waiting_for_asset_loaded:
            self._waiting_for_asset_loaded = False

    def __get_thumbnail_path(self, stage_url: str, schema_data: Data) -> _OmniUrl:
        return (
            _OmniUrl(_OmniUrl(stage_url).parent_url)
            / ".thumbs"
            / f"{schema_data.thumbnail_size[0]}x{schema_data.thumbnail_size[1]}"
            / f"{_OmniUrl(stage_url).name}.png"
        )

    def __get_camera_translate_from_stage(self, stage) -> Optional[Tuple[float, float, float]]:
        camera_path = "/OmniverseKit_Persp"
        camera_prim = stage.GetPrimAtPath(camera_path)
        if not camera_prim.IsValid():
            return None
        xf_tr = camera_prim.GetProperty("xformOp:translate")
        return tuple(xf_tr.Get())

    def _reset_camera(self, stage):
        cam_prefix = "/OmniverseKit_"
        isettings = carb.settings.acquire_settings_interface()
        up_axis = UsdGeom.GetStageUpAxis(stage)

        def add_viewport_camera(cam_name, translate, rotate, ortho, md_name, counter):
            cam_path = f'{cam_prefix}{cam_name}{counter if counter else ""}'
            prim = stage.GetPrimAtPath(cam_path)
            existed = prim and prim.IsValid()
            # Test if it's a camera, but also might be a pure-over which Define should take.
            if existed and not prim.IsA(UsdGeom.Camera) and prim.GetTypeName():
                carb.log_warn(f'Usd.Prim exists at "{cam_path}", but is not a UsdGeom.Camera')
                if counter < 10:
                    return add_viewport_camera(cam_name, translate, rotate, ortho, md_name, counter + 1)
                return (None, False)

            camera = UsdGeom.Camera.Define(stage, cam_path)
            add_xform = (not existed) or (not camera.GetOrderedXformOps())
            target = Gf.Vec3d(0, 0, 0)
            attr_defaults_key = "/persistent/app/primCreation/typedDefaults/camera"
            camera.GetFocalLengthAttr().Set(18.147562)
            if up_axis == "Z":
                up = Gf.Vec3d(0, 0, 1)
            elif up_axis == "X":
                up = Gf.Vec3d(1, 0, 0)
            else:
                up = Gf.Vec3d(0, 1, 0)
            decomp = (Gf.Vec3d(-1, 0, 0), Gf.Vec3d(0, -1, 0), Gf.Vec3d(0, 0, -1))
            look_at = Gf.Matrix4d().SetLookAt(translate, target, up)
            # Put target into camera space for center of interest
            center_of_interest = look_at.Transform(target)
            # Extract x-y-z rotation
            rotation = look_at.ExtractRotation().Decompose(decomp[0], decomp[1], decomp[2])
            if rotation:
                rotate = rotation
            else:
                carb.log_warn("LookAt decomposition failed for camera {md_name}")

            prim = camera.GetPrim()

            # Setup with any user-specified defaults
            if attr_defaults_key:
                isettings.set_default(f"{attr_defaults_key}/clippingRange", (1.0, 10000000.0))
                attr_keys = isettings.get_settings_dictionary(attr_defaults_key)
                for name, value in (attr_keys.get_dict() if attr_keys else {}).items():
                    # Catch failures and issue an error, but continue on
                    try:
                        attr = prim.GetAttribute(name)
                        if attr:
                            attr.Set(value)
                    except Exception:  # noqa PLW0718
                        import traceback

                        carb.log_error(traceback.format_exc())

            def set_op_value(attr_name, add_op, vec3):
                try:
                    xf_op = add_op()
                except Tf.ErrorException:
                    xf_attr = camera.GetPrim().GetAttribute(f"xformOp:{attr_name}")
                    xf_op = UsdGeom.XformOp(xf_attr) if xf_attr and xf_attr.IsValid() else None
                    if not xf_op:
                        raise

                precision = xf_op.GetPrecision()
                if precision == UsdGeom.XformOp.PrecisionFloat:
                    xf_op.Set(Gf.Vec3f(vec3[0], vec3[1], vec3[2]))
                elif precision == UsdGeom.XformOp.PrecisionHalf:
                    xf_op.Set(Gf.Vec3h(vec3[0], vec3[1], vec3[2]))
                else:
                    xf_op.Set(Gf.Vec3d(vec3[0], vec3[1], vec3[2]))

            set_op_value("translate", camera.AddTranslateOp, translate)
            set_op_value("rotateXYZ", camera.AddRotateXYZOp, rotate)
            set_op_value("scale", camera.AddScaleOp, (1, 1, 1))

            if not center_of_interest:
                zlen = Gf.Vec3d(translate[0], translate[1], translate[2]).GetLength()
                center_of_interest = Gf.Vec3d(0, 0, -zlen)
            prim.CreateAttribute(
                "omni:kit:centerOfInterest", Sdf.ValueTypeNames.Vector3d, True, Sdf.VariabilityUniform
            ).Set(center_of_interest)

            Usd.ModelAPI(prim).SetKind(Kind.Tokens.component)
            cam_md = {"hide_in_stage_window": True, "no_delete": True}
            prim.SetCustomDataByKey("omni:kit", cam_md)

            return (camera, add_xform)

        add_viewport_camera("Persp", (500.0, 500.0, 500.0), (-35, 45, 0), False, "Perspective", 0)

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns:
            bool: True if the check passed, False if not. If the check is True, it will NOT run the fix
            str: the message you want to show, like "Succeeded to check this"
            any: data that you want to pass. For now this is used no where. So you can pass whatever you want (None)
        """
        message = ""
        success = True

        context = omni.usd.get_context(context_plugin_data)
        stage_url = context.get_stage_url()

        thumb_path = self.__get_thumbnail_path(stage_url, schema_data)
        if not self._fix_ran:
            if thumb_path.exists:
                if thumb_path.delete() != omni.client.Result.OK:
                    return False, f"[Thumbnail] Failed to delete thumbanil: {thumb_path}", None
                message += f"Deleted existing thumbnail {thumb_path}"
            success = False

        self._fix_ran = False

        return success, message, None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to fix the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        progress = 0
        success = True

        self.on_progress(progress, "Start", success)

        self._waiting_for_asset_loaded = True

        viewport_api = get_active_viewport(usd_context_name=context_plugin_data)
        ext_manager = omni.kit.app.get_app().get_extension_manager()
        ext_to_load = "omni.kit.viewport.bundle"
        viewport_bundle_ext_loaded = ext_manager.is_extension_enabled(ext_to_load)
        if not viewport_api:
            # load a viewport
            if not viewport_bundle_ext_loaded:
                ext_manager.set_extension_enabled_immediate(ext_to_load, True)
            viewport_api = get_active_viewport(usd_context_name=context_plugin_data)
            if not viewport_api:
                return False, "Can't find any viewport", None

        rig_path = carb.tokens.get_tokens_interface().resolve(schema_data.light_rig_path)

        context = omni.usd.get_context(context_plugin_data)
        stage = context.get_stage()
        stage_url = context.get_stage_url()

        rig_prim_path = "/OmniKit_Viewport_LightRigGeo_thumbnail"
        thumb_path = self.__get_thumbnail_path(stage_url, schema_data)
        message = f"Generating {str(thumb_path)}\n"
        self.on_progress(0.5, message, True)
        with Usd.EditContext(stage, stage.GetSessionLayer()):

            self._reset_camera(stage)
            timeout = 500
            i = 0
            while True:
                translate = self.__get_camera_translate_from_stage(stage)
                if translate == (500.0, 500.0, 500.0):
                    break
                i += 1
                if i == timeout:
                    return False, "Can't reset the camera", None
                await omni.kit.app.get_app().next_update_async()

            self._stage_event_sub = context.get_stage_event_stream().create_subscription_to_pop(
                self._on_stage_event, name="thumbnail_generation stage update"
            )

            # import the template as a layer and lock it
            light_rig_geo_prim = stage.OverridePrim(rig_prim_path)
            light_rig_geo_prim.GetReferences().SetReferences([Sdf.Reference(rig_path)])
            if schema_data.light_rotation:
                omni.kit.commands.execute(
                    "TransformPrimSRTCommand",
                    path=str(light_rig_geo_prim.GetPath()),
                    new_rotation_euler=Gf.Vec3d(
                        schema_data.light_rotation[0], schema_data.light_rotation[1], schema_data.light_rotation[2]
                    ),
                )

            # multiply light intensity
            for prim in stage.TraverseAll():
                if hasattr(UsdLux, "LightAPI"):
                    if not prim.HasAPI(UsdLux.LightAPI):
                        continue
                    intensity_attr = UsdLux.LightAPI(prim).GetIntensityAttr()
                elif prim.IsA(UsdLux.Light):
                    intensity_attr = UsdLux.Light(prim).GetIntensityAttr()
                else:
                    continue
                current_value = intensity_attr.Get()
                intensity_attr.Set(current_value * schema_data.light_intensity_multipler)

            context.get_selection().set_selected_prim_paths([], False)
            frame_viewport_selection(viewport_api=viewport_api, force_legacy_api=True)

            if thumb_path.exists and thumb_path.delete() != omni.client.Result.OK:
                return False, f"[Thumbnail] Failed to delete thumbanil: {thumb_path}", None

            self.__push_pop_renderer_settings(schema_data, True)

            # we are gonna resets the view so we need to wait render_iterations
            timeout = 20
            i = 0
            while self._waiting_for_asset_loaded:
                await asyncio.sleep(1)
                i += 1
                if i == timeout:
                    return False, "Time out. Can't load the asset", None

            await omni.kit.viewport.utility.next_viewport_frame_async(viewport_api)

            capture = capture_viewport_to_buffer(
                viewport_api, functools.partial(self.__on_viewport_captured, schema_data, str(thumb_path))
            )
            await capture.wait_for_result()

            self.__push_pop_renderer_settings(schema_data, False)

        self._fix_ran = True

        if not viewport_bundle_ext_loaded:
            ext_manager.set_extension_enabled_immediate(ext_to_load, False)

        return thumb_path.exists, "Ok", None

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
