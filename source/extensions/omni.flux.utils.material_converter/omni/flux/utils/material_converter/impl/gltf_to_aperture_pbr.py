"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import carb
import omni.usd
from pxr import Gf, Sdf, Usd, UsdShade, Vt

from ..base.attribute_base import AttributeBase
from ..base.converter_base import ConverterBase
from ..base.converter_builder_base import ConverterBuilderBase
from ..utils import (
    TEXTURE_SOURCE_CHANNEL_CUSTOM_DATA_KEY,
    TEXTURE_SOURCE_FACTOR_CUSTOM_DATA_KEY,
    SupportedShaderOutputs,
)
from .usd_preview_surface_to_aperture_pbr import _NormalMapEncodings

__all__ = ["GltfToAperturePBRConverterBuilder"]

_ALPHA_MODE_MASK = 1
_ALPHA_MODE_BLEND = 2
_ALPHA_TEST_ALWAYS = 0
_ALPHA_TEST_GREATER_OR_EQUAL = 7


class GltfToAperturePBRConverterBuilder(ConverterBuilderBase):
    """Convert the asset converter's glTF material and texture lookup nodes."""

    def __init__(self):
        self._warned_texture_nodes: set[Usd.Prim] = set()

    def select_output(self, shader_prim: Usd.Prim) -> SupportedShaderOutputs:
        """Select the translucent shader only for light transmission."""
        transmission = shader_prim.GetAttribute("inputs:transmission_factor").Get()
        if transmission is not None and transmission > 0:
            return SupportedShaderOutputs.APERTURE_PBR_TRANSLUCENT
        return SupportedShaderOutputs.APERTURE_PBR_OPACITY

    def build(self, input_material_prim: Usd.Prim, output_mdl_subidentifier: str) -> ConverterBase:
        """Build attribute mappings for the selected AperturePBR shader."""
        translucent = output_mdl_subidentifier == SupportedShaderOutputs.APERTURE_PBR_TRANSLUCENT.value
        # glTF multiplies each texture by its factor. AperturePBR_Opacity uses the texture instead of the
        # constant when a texture is connected, so the factor travels with the texture for the pipeline to
        # bake in. AperturePBR_Translucent multiplies emissive_color by the emissive mask itself, so the
        # emission factor stays in emissive_color and is not baked into the texture.
        shader_prim = self._get_shader_prim(input_material_prim)
        alpha_mode = shader_prim.GetAttribute("inputs:alpha_mode").Get()
        emissive_factor = {} if translucent else self._texture_factor_custom_data(shader_prim, "inputs:emissive_factor")
        base_color_factor = self._texture_factor_custom_data(shader_prim, "inputs:base_color_factor")
        attributes = [
            AttributeBase(
                input_attr_name="inputs:normal_texture",
                output_attr_name="inputs:normalmap_texture",
                translate_fn=self._convert_connection_to_texture,
            ),
            AttributeBase(
                input_attr_name="inputs:encoding",
                output_attr_name="inputs:encoding",
                output_attr_type=Sdf.ValueTypeNames.Int,
                output_default_value=_NormalMapEncodings.TANGENT_SPACE_OGL.value,
                fake_attribute=True,
            ),
            AttributeBase(
                input_attr_name="inputs:emissive_texture",
                output_attr_name="inputs:emissive_mask_texture",
                translate_fn=self._convert_connection_to_texture,
                output_custom_data=emissive_factor,
            ),
            AttributeBase(
                input_attr_name="inputs:emissive_factor",
                output_attr_name="inputs:emissive_color" if translucent else "inputs:emissive_color_constant",
            ),
            AttributeBase(input_attr_name="inputs:emissive_strength", output_attr_name="inputs:emissive_intensity"),
            AttributeBase(
                input_attr_name="inputs:emissive_factor",
                output_attr_name="inputs:enable_emission",
                translate_fn=lambda value, _: (Sdf.ValueTypeNames.Bool, any(component > 0 for component in value)),
            ),
        ]
        attributes.extend(
            [
                AttributeBase(
                    input_attr_name="inputs:base_color_texture",
                    output_attr_name="inputs:transmittance_texture" if translucent else "inputs:diffuse_texture",
                    translate_fn=self._convert_connection_to_texture,
                    output_custom_data=base_color_factor,
                ),
                AttributeBase(
                    input_attr_name="inputs:base_color_factor",
                    output_attr_name="inputs:transmittance_color" if translucent else "inputs:diffuse_color_constant",
                    translate_fn=lambda value, _: (Sdf.ValueTypeNames.Color3f, Gf.Vec3f(*value[:3])),
                ),
            ]
        )
        if translucent:
            attributes.extend(
                [
                    AttributeBase(input_attr_name="inputs:ior", output_attr_name="inputs:ior_constant"),
                    AttributeBase(input_attr_name="inputs:thin_walled", output_attr_name="inputs:thin_walled"),
                ]
            )
        else:
            attributes.extend(
                [
                    AttributeBase(
                        input_attr_name="inputs:metallic_roughness_texture",
                        output_attr_name="inputs:reflectionroughness_texture",
                        translate_fn=self._convert_connection_to_texture,
                        output_custom_data={TEXTURE_SOURCE_CHANNEL_CUSTOM_DATA_KEY: "G"}
                        | self._texture_factor_custom_data(shader_prim, "inputs:roughness_factor"),
                    ),
                    AttributeBase(
                        input_attr_name="inputs:metallic_roughness_texture",
                        output_attr_name="inputs:metallic_texture",
                        translate_fn=self._convert_connection_to_texture,
                        output_custom_data={TEXTURE_SOURCE_CHANNEL_CUSTOM_DATA_KEY: "B"}
                        | self._texture_factor_custom_data(shader_prim, "inputs:metallic_factor"),
                    ),
                    AttributeBase(
                        input_attr_name="inputs:roughness_factor",
                        output_attr_name="inputs:reflection_roughness_constant",
                    ),
                    AttributeBase(
                        input_attr_name="inputs:metallic_factor", output_attr_name="inputs:metallic_constant"
                    ),
                    AttributeBase(
                        input_attr_name="inputs:alpha_mode",
                        output_attr_name="inputs:use_legacy_alpha_state",
                        output_attr_type=Sdf.ValueTypeNames.Bool,
                        output_default_value=False,
                        translate_fn=lambda _value, _: (Sdf.ValueTypeNames.Bool, False),
                    ),
                    AttributeBase(
                        input_attr_name="inputs:alpha_mode",
                        output_attr_name="inputs:blend_enabled",
                        output_attr_type=Sdf.ValueTypeNames.Bool,
                        output_default_value=False,
                        translate_fn=lambda value, _: (Sdf.ValueTypeNames.Bool, value == _ALPHA_MODE_BLEND),
                    ),
                    AttributeBase(
                        input_attr_name="inputs:alpha_mode",
                        output_attr_name="inputs:alpha_test_type",
                        output_attr_type=Sdf.ValueTypeNames.Int,
                        output_default_value=_ALPHA_TEST_ALWAYS,
                        translate_fn=lambda value, _: (
                            Sdf.ValueTypeNames.Int,
                            _ALPHA_TEST_GREATER_OR_EQUAL if value == _ALPHA_MODE_MASK else _ALPHA_TEST_ALWAYS,
                        ),
                    ),
                    AttributeBase(
                        input_attr_name="inputs:alpha_cutoff",
                        output_attr_name="inputs:alpha_test_reference_value",
                        output_attr_type=Sdf.ValueTypeNames.Float,
                        output_default_value=0.5 if alpha_mode == _ALPHA_MODE_MASK else 0.0,
                        translate_fn=lambda value, _: (
                            Sdf.ValueTypeNames.Float,
                            value if alpha_mode == _ALPHA_MODE_MASK else 0.0,
                        ),
                    ),
                    AttributeBase(input_attr_name="inputs:base_alpha", output_attr_name="inputs:opacity_constant"),
                ]
            )
        return ConverterBase(
            input_material_prim=input_material_prim,
            output_mdl_subidentifier=output_mdl_subidentifier,
            attributes=attributes,
        )

    @staticmethod
    def _get_shader_prim(prim: Usd.Prim) -> Usd.Prim:
        """Return the surface shader of a material prim, or the prim itself when it is not a material."""
        if prim.IsA(UsdShade.Material):
            return omni.usd.get_shader_from_material(prim, get_prim=True) or prim
        return prim

    @staticmethod
    def _texture_factor_custom_data(shader_prim: Usd.Prim, factor_attr_name: str) -> dict[str, Vt.FloatArray]:
        """Return the factor marker for a texture, or an empty dict when the factor is one."""
        value = shader_prim.GetAttribute(factor_attr_name).Get()
        if value is None:
            return {}
        factor = tuple(float(component) for component in value) if hasattr(value, "__len__") else (float(value),)
        if all(component == 1.0 for component in factor):
            return {}
        return {TEXTURE_SOURCE_FACTOR_CUSTOM_DATA_KEY: Vt.FloatArray(factor)}

    def _convert_connection_to_texture(
        self, _value: object, input_attr: Usd.Attribute
    ) -> tuple[Sdf.ValueTypeName, Sdf.AssetPath]:
        """Read the texture asset from a connected glTF lookup node."""
        source = UsdShade.Input(input_attr).GetConnectedSource()
        if source:
            connected_shader = UsdShade.Shader(source[0].GetPrim())
            prim = connected_shader.GetPrim()
            if prim.GetAttribute("info:mdl:sourceAsset:subIdentifier").Get() in (
                "gltf_texture_lookup",
                "gltf_normal_texture_lookup",
            ):
                transformed = any(
                    prim.GetAttribute(f"inputs:{name}").Get() not in (None, default)
                    for name, default in (
                        ("offset", (0, 0)),
                        ("rotation", 0),
                        ("scale", (1, 1)),
                        ("tex_coord_index", 0),
                    )
                )
                if transformed and prim not in self._warned_texture_nodes:
                    carb.log_warn(
                        f"AperturePBR cannot preserve the UV transform or texture coordinate set on {prim.GetPath()}."
                    )
                    self._warned_texture_nodes.add(prim)
                return Sdf.ValueTypeNames.Asset, connected_shader.GetInput("texture").Get()
        return Sdf.ValueTypeNames.Asset, Sdf.AssetPath()
