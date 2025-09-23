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

from enum import Enum
from typing import TYPE_CHECKING

from omni.flux.utils.material_converter.base.attribute_base import AttributeBase
from omni.flux.utils.material_converter.base.converter_base import ConverterBase
from omni.flux.utils.material_converter.base.converter_builder_base import ConverterBuilderBase
from pxr import Sdf, UsdShade

if TYPE_CHECKING:
    from pxr import Gf, Usd


class _NormalMapEncodings(Enum):
    OCTAHEDRAL = 0
    TANGENT_SPACE_OGL = 1
    TANGENT_SPACE_DX = 2


class USDPreviewSurfaceToAperturePBRConverterBuilder(ConverterBuilderBase):
    def build(self, input_material_prim: Usd.Prim, output_mdl_subidentifier: str) -> ConverterBase:
        attributes = [
            # Direct translation
            AttributeBase(
                input_attr_name="inputs:diffuseColor",
                output_attr_name="inputs:diffuse_color_constant",
            ),
            AttributeBase(
                input_attr_name="inputs:diffuseColor",
                output_attr_name="inputs:diffuse_texture",
                translate_fn=self._convert_connection_to_texture,
                translate_alt_fn=self._convert_connection_to_texture_alt,
            ),
            AttributeBase(input_attr_name="inputs:opacity", output_attr_name="inputs:opacity_constant"),
            AttributeBase(
                input_attr_name="inputs:roughness",
                output_attr_name="inputs:reflection_roughness_constant",
            ),
            AttributeBase(
                input_attr_name="inputs:roughness",
                output_attr_name="inputs:reflectionroughness_texture",
                translate_fn=self._convert_connection_to_texture,
                translate_alt_fn=self._convert_connection_to_texture_alt,
            ),
            AttributeBase(input_attr_name="inputs:metallic", output_attr_name="inputs:metallic_constant"),
            AttributeBase(
                input_attr_name="inputs:metallic",
                output_attr_name="inputs:metallic_texture",
                translate_fn=self._convert_connection_to_texture,
                translate_alt_fn=self._convert_connection_to_texture_alt,
            ),
            AttributeBase(
                input_attr_name="inputs:displacement",
                output_attr_name="inputs:height_texture",
                translate_fn=self._convert_connection_to_texture,
                translate_alt_fn=self._convert_connection_to_texture_alt,
            ),
            # Need conversion
            AttributeBase(input_attr_name="inputs:emissiveColor", output_attr_name="inputs:emissive_color_constant"),
            AttributeBase(
                input_attr_name="inputs:emissiveColor",
                output_attr_name="inputs:emissive_mask_texture",
                translate_fn=self._convert_connection_to_texture,
                translate_alt_fn=self._convert_connection_to_texture_alt,
            ),
            AttributeBase(input_attr_name="inputs:encoding", output_attr_name="inputs:encoding", fake_attribute=True),
        ]
        return ConverterBase(
            input_material_prim=input_material_prim,
            output_mdl_subidentifier=output_mdl_subidentifier,
            attributes=attributes,
        )

    def _convert_connection_to_texture(self, _value: Gf.Vec3f, input_attr: Usd.Attribute) -> Sdf.AssetPath:
        """
        Convert the attribute. If the attribute has a connection, and this connection is `UsdUVTexture` with a `file`
        input, we set the texture.

        Args:
            _value: the current value of the attribute
            input_attr: the input attr that need to be translated

        Returns:
            The value to set to the attribute
        """
        connections = input_attr.GetConnections()
        shd_input = UsdShade.Input(input_attr)
        if len(connections) > 0:
            if len(connections) > 1:
                return Sdf.AssetPath()
            connected_source = shd_input.GetConnectedSource()
            if connected_source is None:
                return Sdf.AssetPath()
            # The source must be a valid shader or material prim.
            connected_shader = UsdShade.Shader(connected_source[0].GetPrim())
            if connected_shader.GetShaderId() == "UsdUVTexture":
                file_input = connected_shader.GetInput("file")
                outputs = connected_source[0].GetOutputs()
                if outputs[0].GetBaseName() == "rgb" and file_input:
                    return file_input.Get()
        return Sdf.AssetPath()

    def _convert_connection_to_texture_alt(
        self, _: Sdf.ValueTypeNames, value: Gf.Vec3f, input_attr: Usd.Attribute | None
    ) -> tuple[Sdf.ValueTypeNames, str]:
        return (
            Sdf.ValueTypeNames.Asset,
            self._convert_connection_to_texture(value, input_attr),
        )
