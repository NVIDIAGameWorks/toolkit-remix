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

from enum import Enum
from typing import TYPE_CHECKING, Optional, Tuple

from omni.flux.utils.material_converter.base.attribute_base import AttributeBase
from omni.flux.utils.material_converter.base.converter_base import ConverterBase
from omni.flux.utils.material_converter.base.converter_builder_base import ConverterBuilderBase
from pxr import Sdf

if TYPE_CHECKING:
    from pxr import Usd


class _NormalMapEncodings(Enum):
    OCTAHEDRAL = 0
    TANGENT_SPACE_OGL = 1
    TANGENT_SPACE_DX = 2


class OmniPBRToAperturePBRConverterBuilder(ConverterBuilderBase):
    def build(self, input_material_prim: "Usd.Prim", output_mdl_subidentifier: str) -> ConverterBase:
        attributes = [
            # Direct translation
            AttributeBase(
                input_attr_name="inputs:diffuse_color_constant", output_attr_name="inputs:diffuse_color_constant"
            ),
            AttributeBase(input_attr_name="inputs:opacity_constant", output_attr_name="inputs:opacity_constant"),
            AttributeBase(input_attr_name="inputs:diffuse_texture", output_attr_name="inputs:diffuse_texture"),
            AttributeBase(
                input_attr_name="inputs:reflection_roughness_constant",
                output_attr_name="inputs:reflection_roughness_constant",
            ),
            AttributeBase(
                input_attr_name="inputs:reflectionroughness_texture",
                output_attr_name="inputs:reflectionroughness_texture",
            ),
            AttributeBase(input_attr_name="inputs:metallic_constant", output_attr_name="inputs:metallic_constant"),
            AttributeBase(input_attr_name="inputs:metallic_texture", output_attr_name="inputs:metallic_texture"),
            AttributeBase(input_attr_name="inputs:enable_emission", output_attr_name="inputs:enable_emission"),
            AttributeBase(
                input_attr_name="inputs:emissive_mask_texture", output_attr_name="inputs:emissive_mask_texture"
            ),
            AttributeBase(input_attr_name="inputs:emissive_intensity", output_attr_name="inputs:emissive_intensity"),
            AttributeBase(input_attr_name="inputs:normalmap_texture", output_attr_name="inputs:normalmap_texture"),
            AttributeBase(
                input_attr_name="inputs:height_texture", output_attr_name="inputs:height_texture", fake_attribute=True
            ),
            # Need conversion
            AttributeBase(input_attr_name="inputs:emissive_color", output_attr_name="inputs:emissive_color_constant"),
            AttributeBase(
                input_attr_name="inputs:emissive_color_texture", output_attr_name="inputs:emissive_mask_texture"
            ),
            AttributeBase(input_attr_name="inputs:encoding", output_attr_name="inputs:encoding", fake_attribute=True),
            AttributeBase(
                input_attr_name="inputs:flip_tangent_v",
                output_attr_name="inputs:encoding",
                output_default_value=_NormalMapEncodings.TANGENT_SPACE_DX.value,
                translate_fn=self._convert_normal_encoding,
                translate_alt_fn=self._convert_normal_encoding_alt,
            ),
        ]
        return ConverterBase(
            input_material_prim=input_material_prim,
            output_mdl_subidentifier=output_mdl_subidentifier,
            attributes=attributes,
        )

    def _convert_normal_encoding(self, value: bool, input_attr: "Usd.Attribute") -> int:
        return _NormalMapEncodings.TANGENT_SPACE_DX.value if value else _NormalMapEncodings.TANGENT_SPACE_OGL.value

    def _convert_normal_encoding_alt(
        self, _: Sdf.ValueTypeNames, value: bool, input_attr: Optional["Usd.Attribute"]
    ) -> Tuple["Sdf.ValueTypeNames", int]:
        """Alternate translate method to create attributes in the output material"""
        return (
            Sdf.ValueTypeNames.Int,
            self._convert_normal_encoding(value, input_attr),
        )
