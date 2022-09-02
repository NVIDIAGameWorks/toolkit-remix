"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from lightspeed.common import constants
from pxr import Sdf, Usd, UsdShade

from ..layer_types import LayerType
from .i_layer import ILayer


class AutoUpscaleLayer(ILayer):
    @property
    def layer_type(self) -> LayerType:
        return LayerType.autoupscale

    def set_texture_attributes(self, texture_attribute, prim_paths, output_asset_relative_paths):
        layer = self.get_sdf_layer()
        auto_stage = Usd.Stage.Open(layer.realPath)
        auto_stage.DefinePrim(constants.ROOTNODE)
        auto_stage.DefinePrim(constants.ROOTNODE_LOOKS, constants.SCOPE)

        if len(prim_paths) != len(output_asset_relative_paths):
            raise RuntimeError("List length mismatch.")
        for index, prim_path in enumerate(prim_paths):
            output_asset_relative_path = output_asset_relative_paths[index]
            UsdShade.Material.Define(auto_stage, prim_path)
            shader = UsdShade.Shader.Define(auto_stage, str(prim_path) + "/" + constants.SHADER)
            Usd.ModelAPI(shader).SetKind(constants.MATERIAL)
            shader_prim = shader.GetPrim()
            attr = shader_prim.CreateAttribute(texture_attribute, Sdf.ValueTypeNames.Asset)
            attr.Set(output_asset_relative_path)
            if texture_attribute == constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE:
                attr.SetColorSpace(constants.SRGB)
            else:
                attr.SetColorSpace(constants.RAW)
        auto_stage.GetRootLayer().Save()
