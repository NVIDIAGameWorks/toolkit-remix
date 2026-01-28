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

import tempfile
from typing import Optional

import carb.settings
import carb.tokens
import omni.kit.app
import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from pxr import Gf, Sdf, Usd, UsdGeom

_LOOKDEV_USD_PATH = "/exts/omni.flux.lookdev.core/rigs"
_LOOKDEV_DEFAULT_MATERIAL_PATH = "/exts/omni.flux.lookdev.core/default_material_path"


class LookDevCore:
    def __init__(self, context_name: str):
        """
        Core to create rigs for lookdev

        Args:
            context_name: the context name to use
        """

        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self.__settings = carb.settings.get_settings()
        self.__context_name = context_name

    # Ideally CreateReferenceCommand would be used, but there are some issues with how it
    # tries to create unique prims in the stage, make all paths relative, and only supports Usd.Stage.Define
    # (no pure overs). The one thing that is nice about CreateReferenceCommand is that it handles differing up-axis
    # between stage and reference. So we repeat that behavior here, but NOTE: This is not dynamic, changing stage-up
    # does not affect the adjustment once it has been created (though adding/replacing with a new rig will trigger
    # the adjustment)
    @staticmethod
    def add_rig_reference(light_rig_geo_prim: Usd.Prim, rig_path: str):
        light_rig_geo_prim.GetReferences().SetReferences([Sdf.Reference(rig_path)])
        xformable = UsdGeom.Xformable(light_rig_geo_prim)
        # if not bool(xformable):
        #    return (None, None)

        # Can't query metadata on Sdf.Layer easily via Python, so need to go thorugh UsdGeom with a Usd.Stage
        # First check that the reference succeeded and the layer is reachable.
        asset_layer = Sdf.Layer.FindOrOpen(rig_path)
        if not asset_layer:
            return None, None

        ref_stage = Usd.Stage.Open(asset_layer, sessionLayer=None)
        if not ref_stage:
            return None, None

        ref_up = UsdGeom.GetStageUpAxis(ref_stage)
        cur_up = UsdGeom.GetStageUpAxis(light_rig_geo_prim.GetStage())
        if ref_up == cur_up:
            return None, None

        if cur_up == "Y":
            if ref_up == "Z":
                adjustment = Gf.Matrix4d(0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1)
            else:
                adjustment = Gf.Matrix4d(0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1)
        elif cur_up == "Z":
            if ref_up == "Y":
                adjustment = Gf.Matrix4d(0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1)
            else:
                adjustment = Gf.Matrix4d(0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1)
        elif ref_up == "Y":
            adjustment = Gf.Matrix4d(0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1)
        else:
            adjustment = Gf.Matrix4d(0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1)

        # Can set to any existing attributes but CANNOT CREATE them as the caller is in an Sd.ChangeBlock
        if adjustment:
            op_order_attr = xformable.GetXformOpOrderAttr()
            if op_order_attr:
                op_order = op_order_attr.Get()
                if op_order and ("xformOp:transform" in op_order):
                    transform_attr = light_rig_geo_prim.GetProperty("xformOp:transform")
                    if transform_attr:
                        transform_attr.Set(adjustment)
                        adjustment = None
                        xformable = None

        return xformable, adjustment

    @omni.usd.handle_exception
    async def create_lookdev_stage(self) -> Usd.Stage:
        """
        Create and add the lookdev geo into the stage

        Returns:
            The current stage
        """
        context = omni.usd.get_context(self.__context_name)
        # create a tmp file to trigger the viewport lighting menu template
        with tempfile.NamedTemporaryFile(delete=True, suffix=".usd") as tmp_file:
            path = tmp_file.name
        Sdf.Layer.CreateNew(path)
        # set the axis before to open it with the context, for the light viewport menu to pick the good axis
        _stage = Usd.Stage.Open(path)
        UsdGeom.SetStageUpAxis(_stage, UsdGeom.Tokens.z)
        _stage.Save()
        await context.open_stage_async(path)
        stage = context.get_stage()

        rig_prim_path = "/OmniKit_Viewport_LightRigGeo"
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            # import the template as a layer and lock it
            stage_template_path = self.__settings.get(_LOOKDEV_USD_PATH)
            stage_template_path = str(_OmniUrl(carb.tokens.get_tokens_interface().resolve(stage_template_path)))

            light_rig_geo_prim = stage.OverridePrim(rig_prim_path)
            xformable, adjustment = LookDevCore.add_rig_reference(light_rig_geo_prim, stage_template_path)
            if xformable and adjustment:
                xformable.AddXformOp(UsdGeom.XformOp.TypeTransform).Set(adjustment)
        return stage

    def get_default_material_path(self) -> Optional[Sdf.Path]:
        context = omni.usd.get_context(self.__context_name)
        stage = context.get_stage()
        default_material_path = self.__settings.get(_LOOKDEV_DEFAULT_MATERIAL_PATH)
        prim = stage.GetPrimAtPath(default_material_path)
        return prim.GetPath() if prim.IsValid() else None

    def destroy(self):
        _reset_default_attrs(self)
