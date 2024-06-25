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

from lightspeed.common import constants
from pxr import Sdf, Usd, UsdShade

from ..data_models import LayerType
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
