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

__all__ = ("MATERIAL_FIELD_BUILDERS",)


from ..item_delegates.slider import USDFloatSliderField
from .base import USDBuilderList

MATERIAL_FIELD_BUILDERS = USDBuilderList()

# Material attributes
# These values should override the min/max range from the USD metadata. The min/max values provided are the
# fallback/defaults if no metadata can be found.

MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name("inputs:opacity_constant", USDFloatSliderField(0.0, 1.0))
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:reflection_roughness_constant", USDFloatSliderField(0.0, 1.0)
)
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name("inputs:metallic_constant", USDFloatSliderField(0.0, 1.0))
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:thin_film_thickness_constant", USDFloatSliderField(0.0010000000474974513, 1500.0)
)
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name("inputs:emissive_intensity", USDFloatSliderField(0.0, 65504.0))
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name("inputs:displace_in", USDFloatSliderField(0.0, 2.0))
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name("inputs:displace_out", USDFloatSliderField(0.0, 2.0))
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:subsurface_measurement_distance", USDFloatSliderField(0.0, 16.0)
)
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:subsurface_volumetric_anisotropy", USDFloatSliderField(-0.9900000095367432, 0.9900000095367432)
)
